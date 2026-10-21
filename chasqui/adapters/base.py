"""Base adapter class."""

import abc
import threading
from typing import Callable, Optional

from ..core.config import Config
from ..core.constants import LANG_NAMES
from ..core.pipeline import Pipeline, TranslationEvent
from ..core.session import Session


def _safe_print(msg: str) -> None:
    """Print that survives non-UTF8 consoles (CJK output on Windows)."""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode(), flush=True)


class BaseAdapter(abc.ABC):
    """All adapters inherit from this.

    Subclasses implement `run()` to set up their audio sources/sinks
    and call `self._make_pipeline()` to get a configured pipeline.
    """

    def __init__(self, config: Config):
        self.config = config
        self._session = Session(
            source_lang=config.source_lang,
            target_lang=config.target_lang,
            context=config.context,
        )
        # Programmatic stop. The CLI ends a session with Ctrl+C, but a GUI (or
        # any embedder) has to end it from another thread — and it must go
        # through the same path, or the adapters' `finally` blocks never run
        # and Windows is left with chasqui's cables as its default devices.
        self._stop = threading.Event()
        self._pipelines: list[Pipeline] = []
        # Fired after every completed turn: (event, "out" | "in").
        self.on_turn: Optional[Callable[[TranslationEvent, str], None]] = None

    @abc.abstractmethod
    def run(self) -> None:
        """Start the adapter. Blocks until stopped or KeyboardInterrupt."""
        ...

    def stop(self) -> None:
        """End the session from another thread. Non-blocking.

        Does what Ctrl+C does: every pipeline leaves its loop, `run()` returns,
        and each adapter's cleanup (closing streams, restoring Windows default
        devices) runs on the way out. Callers still have to join the thread
        `run()` is on before exiting the process.
        """
        self._stop.set()
        for pipeline in self._pipelines:
            pipeline.stop()

    def _emit_turn(self, event: TranslationEvent, direction: str) -> None:
        if not self.on_turn:
            return
        try:
            self.on_turn(event, direction)
        except Exception as e:
            # A listener's bug must not take the audio session down with it.
            _safe_print(f"  [on_turn error] {e}")

    def _make_pipeline(self, on_translation=None) -> Pipeline:
        def _combined(event: TranslationEvent):
            self._session.add_turn(
                source_text=event.source_text,
                target_text=event.target_text,
                latency_ms=event.latency_ms,
            )
            if self.config.logging.show_transcript:
                self._print_event(event)
            self._emit_turn(event, "out")
            if on_translation:
                on_translation(event)

        return self._register(Pipeline(
            source_lang=self.config.source_lang,
            target_lang=self.config.target_lang,
            api_key=self.config.api_key,
            model=self.config.model,
            context=self.config.context,
            voice=self.config.voice,
            on_translation=_combined,
            vad_threshold=self.config.vad_threshold,
            vad_silence_ms=self.config.vad_silence_ms,
            isolate_turns=self.config.isolate_turns,
        ))

    def _make_pipeline_reverse(self, on_translation=None) -> Pipeline:
        """Pipeline for the IN direction: target_lang → source_lang."""
        def _combined(event: TranslationEvent):
            self._session.add_turn(
                source_text=event.source_text,
                target_text=event.target_text,
                latency_ms=event.latency_ms,
            )
            if self.config.logging.show_transcript:
                src = self.config.target_lang.upper()
                tgt = self.config.source_lang.upper()
                _safe_print(f"\n  [{src}→{tgt}] {event.source_text!r}")
                _safe_print(f"          {event.target_text!r}  {event.latency_ms:.0f}ms")
            self._emit_turn(event, "in")
            if on_translation:
                on_translation(event)

        return self._register(Pipeline(
            source_lang=self.config.target_lang,
            target_lang=self.config.source_lang,
            api_key=self.config.api_key,
            model=self.config.model,
            context=self.config.context,
            voice=self.config.voice,
            on_translation=_combined,
            vad_threshold=self.config.vad_threshold,
            vad_silence_ms=self.config.vad_silence_ms,
            isolate_turns=self.config.isolate_turns,
        ))

    def _register(self, pipeline: Pipeline) -> Pipeline:
        """Track a pipeline so `stop()` can reach it.

        A stop that lands between `stop()` and the pipeline being built would
        otherwise start a session nobody asked for — so a pipeline created
        after the stop is born stopped.
        """
        self._pipelines.append(pipeline)
        if self._stop.is_set():
            pipeline.stop()
        return pipeline

    def _print_event(self, event: TranslationEvent) -> None:
        src = self.config.source_lang.upper()
        tgt = self.config.target_lang.upper()
        _safe_print(f"\n  [{src}] {event.source_text}")
        _safe_print(f"  [{tgt}] {event.target_text}")
        _safe_print(f"        {event.latency_ms:.0f}ms")

    def _print_header(self, adapter_name: str) -> None:
        src = LANG_NAMES.get(self.config.source_lang, self.config.source_lang)
        tgt = LANG_NAMES.get(self.config.target_lang, self.config.target_lang)
        print(f"\nChasqui — {adapter_name}")
        print(f"  {src} → {tgt}")
        print(f"  Voice: {self.config.voice}")
        print()

    def _save_session_if_needed(self) -> None:
        if self.config.logging.save_session and self._session.turns:
            path = self._session.save(self.config.logging.session_dir)
            print(f"\nSession saved: {path}")
        print(f"\nSession summary:\n{self._session.summary()}")
