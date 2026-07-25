"""Runs a chasqui session on a worker thread and reports back through a queue.

Nothing here touches a widget. Tk only allows the main thread to draw, and the
adapters only speak by printing, so this module owns both halves of that
mismatch: it captures stdout while a session runs and turns everything the
session produces — log lines, translated turns, lifecycle changes — into events
the caller drains whenever it likes.
"""

import io
import queue
import sys
import threading
from dataclasses import dataclass
from typing import Optional

from ..adapters import build_adapter
from ..core.config import Config
from ..core.pricing import Price, Usage, estimate
from ..core.selftest import CheckResult, run_check

# Log severities. The UI maps these to colors; nothing else depends on them.
INFO, ACCENT, WARN, ERROR = "info", "accent", "warn", "error"


@dataclass
class LogLine:
    """A line the session printed."""
    text: str
    level: str = INFO


@dataclass
class TurnLine:
    """A completed translation. `direction` is "out" (you) or "in" (them)."""
    source_text: str
    target_text: str
    latency_ms: float
    direction: str = "out"


@dataclass
class StateChange:
    """Session lifecycle: starting → running → stopping → stopped, or error."""
    state: str
    detail: str = ""


@dataclass
class CheckDone:
    result: CheckResult


RunnerEvent = LogLine | TurnLine | StateChange | CheckDone


def classify(line: str) -> str:
    """Severity of a printed line, by the markers the adapters already use."""
    low = line.lower()
    if "[warn]" in low or "warning:" in low:
        return WARN
    if "error" in low or "fail" in low:
        return ERROR
    if "[auto]" in low:
        return ACCENT
    return INFO


class _LineWriter(io.TextIOBase):
    """File-like object that emits complete lines and tees to the real stdout.

    The adapters print partial lines (`click.echo(..., nl=False)`, progress
    dots), so writes are buffered until a newline shows up.
    """

    def __init__(self, sink, tee=None):
        self._sink = sink
        self._tee = tee
        self._buffer = ""
        self._lock = threading.Lock()

    def write(self, text: str) -> int:
        if not text:
            return 0
        if self._tee is not None:
            try:
                self._tee.write(text)
                self._tee.flush()
            except Exception:
                # No console attached (pythonw.exe) — the UI log is enough.
                self._tee = None
        with self._lock:
            self._buffer += text
            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                self._sink(line)
        return len(text)

    def flush(self) -> None:
        pass

    def drain(self) -> None:
        """Emit whatever is left without a trailing newline."""
        with self._lock:
            leftover, self._buffer = self._buffer, ""
        if leftover.strip():
            self._sink(leftover)

    def writable(self) -> bool:
        return True


class SessionRunner:
    """Starts, stops and observes one chasqui session at a time."""

    def __init__(self, events: Optional[queue.Queue] = None):
        self.events: queue.Queue = events or queue.Queue()
        self._adapter = None
        self._thread: Optional[threading.Thread] = None
        self._check_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._config: Optional[Config] = None
        # Cost of sessions that already ended in this window. The live one is
        # read off its pipelines and added on top, so the total does not drop
        # back to zero the moment a session stops.
        self._closed_usd = 0.0

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def is_checking(self) -> bool:
        return self._check_thread is not None and self._check_thread.is_alive()

    @property
    def is_busy(self) -> bool:
        return self.is_running or self.is_checking

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------

    def start(self, config: Config) -> None:
        """Start a session. Returns immediately; watch the queue for progress.

        Raises RuntimeError if a session is already running, ValueError if the
        config is incomplete (no API key) — both are the caller's bug to show.
        """
        with self._lock:
            if self.is_running:
                raise RuntimeError("a session is already running")
            config.validate()
            self._config = config
            self._adapter = build_adapter(config)
            self._adapter.on_turn = self._on_turn
            self._thread = threading.Thread(
                target=self._run_session, args=(self._adapter,),
                name="chasqui-session", daemon=True,
            )
            self._emit(StateChange("starting"))
            self._thread.start()

    def stop(self) -> None:
        """Ask the session to end. Non-blocking — "stopped" arrives on the queue.

        Deliberately not instant: the adapters restore the Windows default mic
        and output on their way out, which takes a PowerShell round trip each.
        """
        adapter = self._adapter
        if adapter is None or not self.is_running:
            return
        self._emit(StateChange("stopping"))
        adapter.stop()

    def join(self, timeout: float = 10.0) -> bool:
        """Block until the session thread is done. True if it finished in time."""
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout=timeout)
        return not thread.is_alive()

    # ------------------------------------------------------------------
    # Cost
    # ------------------------------------------------------------------

    def session_price(self) -> Price:
        """What the live session has cost so far. Zero when nothing runs.

        Bidirectional modes run two pipelines, each with its own billed
        stream — summing their usage is what makes headset show its real
        double rate instead of half of it.
        """
        adapter, config = self._adapter, self._config
        if adapter is None or config is None:
            return Price()

        usage = Usage()
        for pipeline in getattr(adapter, "_pipelines", []):
            usage = usage + pipeline.usage

        return estimate(
            config.model, usage,
            count_transcription=config.pricing.count_transcription,
            per_minute=config.pricing.per_minute,
            transcription_per_minute=config.pricing.transcription_per_minute,
        )

    def total_usd(self) -> float:
        """Everything spent since this runner was created."""
        return self._closed_usd + self.session_price().usd

    def _run_session(self, adapter) -> None:
        prev_stdout, prev_stderr = sys.stdout, sys.stderr
        # Tee to the stdout we are replacing, not to sys.__stdout__: cli.py
        # wraps stdout in a UTF-8 writer at import, and the raw one underneath
        # still dies on Japanese.
        writer = _LineWriter(self._on_line, tee=prev_stdout)
        sys.stdout = sys.stderr = writer
        try:
            self._emit(StateChange("running"))
            adapter.run()
            self._emit(StateChange("stopped"))
        except Exception as e:
            self._emit(StateChange("error", detail=str(e)))
        finally:
            writer.drain()
            sys.stdout, sys.stderr = prev_stdout, prev_stderr
            # Bank the cost BEFORE dropping the adapter — the pipelines are
            # the only place the usage counters live.
            self._closed_usd += self.session_price().usd
            self._adapter = None

    # ------------------------------------------------------------------
    # Smoke test
    # ------------------------------------------------------------------

    def start_check(self, config: Config) -> None:
        """Run the pipeline smoke test on a worker thread."""
        with self._lock:
            if self.is_checking:
                raise RuntimeError("a check is already running")
            config.validate()
            self._check_thread = threading.Thread(
                target=self._run_check, args=(config,),
                name="chasqui-check", daemon=True,
            )
            self._check_thread.start()

    def _run_check(self, config: Config) -> None:
        self._emit(StateChange("checking"))
        result = run_check(config, on_progress=lambda msg: self._emit(LogLine(f"  {msg}")))
        self._emit(CheckDone(result))
        self._emit(StateChange("check_done"))

    # ------------------------------------------------------------------
    # Plumbing
    # ------------------------------------------------------------------

    def _on_line(self, line: str) -> None:
        self._emit(LogLine(line, level=classify(line)))

    def _on_turn(self, event, direction: str) -> None:
        self._emit(TurnLine(
            source_text=event.source_text,
            target_text=event.target_text,
            latency_ms=event.latency_ms,
            direction=direction,
        ))

    def _emit(self, event: RunnerEvent) -> None:
        self.events.put(event)

    def drain(self, limit: int = 200) -> list[RunnerEvent]:
        """Pop up to `limit` pending events. Called from the UI's tick."""
        out: list[RunnerEvent] = []
        for _ in range(limit):
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                break
        return out
