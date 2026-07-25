"""UI session runner — the bridge between a blocking, printing adapter and a
single-threaded GUI.

Everything the window shows comes through this queue: adapters only speak by
printing, and Tk only draws from the main thread. No tkinter is imported here,
so these run headless in CI.
"""

import queue
import threading

import pytest

from chasqui.core.config import Config
from chasqui.core.pipeline import TranslationEvent
from chasqui.ui import runner as R


class _Adapter:
    """Stand-in for a real adapter: prints, emits a turn, blocks until stopped."""

    def __init__(self, config):
        self.config = config
        self.on_turn = None
        self._stop = threading.Event()
        self.stopped = False

    def run(self):
        print("Chasqui — Headset mode")
        print("  [warn] CABLE Input not found")
        if self.on_turn:
            self.on_turn(TranslationEvent(source_text="hola", target_text="こんにちは",
                                          latency_ms=420.0), "out")
        self._stop.wait(timeout=5)

    def stop(self):
        self.stopped = True
        self._stop.set()


@pytest.fixture
def session(monkeypatch):
    adapters = []

    def _build(config):
        adapter = _Adapter(config)
        adapters.append(adapter)
        return adapter

    monkeypatch.setattr(R, "build_adapter", _build)
    run = R.SessionRunner()
    yield run, adapters
    run.stop()
    run.join(timeout=5)


def _config() -> Config:
    cfg = Config()
    cfg.api_key = "sk-test"
    return cfg


def _wait_for(run, kind, timeout=5.0):
    """Collect events until one of `kind` shows up. Returns everything seen."""
    seen = []
    deadline = threading.Event()
    threading.Timer(timeout, deadline.set).start()
    while not deadline.is_set():
        try:
            event = run.events.get(timeout=0.1)
        except queue.Empty:
            continue
        seen.append(event)
        if isinstance(event, kind):
            return seen
    raise AssertionError(f"no {kind.__name__} within {timeout}s; saw {seen}")


# ---------------------------------------------------------------------------


def test_printed_output_becomes_log_lines(session):
    run, _ = session
    run.start(_config())
    seen = _wait_for(run, R.LogLine)

    texts = [e.text for e in seen if isinstance(e, R.LogLine)]
    assert any("Headset mode" in t for t in texts), (
        "The adapters' banner and warnings only exist as prints. If this "
        "fails, the UI shows an empty log while the terminal has the "
        "setup instructions the user needs — capture stdout in _run_session."
    )


def test_warnings_keep_their_severity(session):
    run, _ = session
    run.start(_config())
    seen = _wait_for(run, R.TurnLine)   # printed before the turn, so both are in

    levels = {e.text.strip(): e.level for e in seen if isinstance(e, R.LogLine)}
    warn = [text for text, level in levels.items() if level == R.WARN]
    assert any("CABLE Input not found" in t for t in warn), (
        "'[warn]' lines must arrive tagged as warnings so the window can "
        "color them. Missing setup warnings buried in grey text is exactly "
        "how a user ends up on a silent call."
    )


def test_turns_arrive_as_structured_events(session):
    run, _ = session
    run.start(_config())
    seen = _wait_for(run, R.TurnLine)

    turn = next(e for e in seen if isinstance(e, R.TurnLine))
    assert (turn.source_text, turn.target_text, turn.direction) == ("hola", "こんにちは", "out"), (
        "Transcripts must reach the UI through on_turn, not by parsing the "
        "printed log. Parsing prints breaks the moment a translation "
        "contains a newline or a bracket."
    )


def test_stop_unwinds_the_session(session):
    run, adapters = session
    run.start(_config())
    _wait_for(run, R.TurnLine)

    run.stop()
    assert run.join(timeout=5), "the session thread must exit after stop()"
    assert adapters[0].stopped
    assert not run.is_running


def test_stdout_is_restored_after_the_session(session):
    """A leaked stdout redirect would swallow every later print in the process."""
    import sys
    run, _ = session
    original = sys.stdout

    run.start(_config())
    _wait_for(run, R.TurnLine)
    run.stop()
    run.join(timeout=5)

    assert sys.stdout is original, (
        "sys.stdout must be restored when the session ends. If this fails, "
        "the CLI running in the same process goes mute after the first UI "
        "session — restore it in _run_session's finally."
    )


def test_start_rejects_a_second_session(session):
    run, _ = session
    run.start(_config())
    with pytest.raises(RuntimeError):
        run.start(_config())


def test_start_without_api_key_raises_before_any_thread(session):
    run, adapters = session
    cfg = Config()
    cfg.api_key = ""
    with pytest.raises(ValueError):
        run.start(cfg)
    assert not adapters, (
        "Config must be validated before an adapter exists. If this fails, "
        "the UI switches to 'Running' and then dies on a missing key."
    )


def test_adapter_crash_surfaces_as_an_error_state(monkeypatch):
    class _Boom:
        on_turn = None

        def run(self):
            raise RuntimeError("no cable")

        def stop(self):
            pass

    monkeypatch.setattr(R, "build_adapter", lambda config: _Boom())
    run = R.SessionRunner()
    run.start(_config())
    seen = _wait_for(run, R.StateChange)

    states = [e for e in seen if isinstance(e, R.StateChange)]
    while not any(s.state == "error" for s in states):
        states.append(run.events.get(timeout=2))
    error = next(s for s in states if s.state == "error")
    assert "no cable" in error.detail, (
        "A crashing adapter must reach the window as an error with its "
        "message. Otherwise the UI sits on 'Running' forever with a dead "
        "session behind it."
    )


# ---------------------------------------------------------------------------
# Line buffering
# ---------------------------------------------------------------------------


def test_partial_writes_are_joined_into_one_line():
    lines = []
    writer = R._LineWriter(lines.append)
    writer.write("  [1/3] Synthesizing... ")   # click.echo(nl=False)
    assert lines == [], "a line without a newline is not finished yet"
    writer.write("ok\n")
    assert lines == ["  [1/3] Synthesizing... ok"], (
        "Adapters and the check command print partial lines. Emitting each "
        "write separately shreds progress lines across the UI log."
    )


def test_drain_flushes_a_trailing_partial_line():
    lines = []
    writer = R._LineWriter(lines.append)
    writer.write("last word, no newline")
    writer.drain()
    assert lines == ["last word, no newline"]


# ---------------------------------------------------------------------------
# Language pickers
# ---------------------------------------------------------------------------


def test_every_mode_says_what_its_language_boxes_mean():
    """The two boxes are always (source, target), but that pair means something
    different per mode. Leaving a mode on the generic wording is how a user
    sets the pair backwards and hears the language they already speak."""
    from chasqui.adapters import UI_ADAPTER_NAMES
    from chasqui.ui.app import LANG_ROLES

    missing = [name for name in UI_ADAPTER_NAMES if name not in LANG_ROLES]
    assert not missing, (
        f"Modes without language-picker captions: {missing}. Add them to "
        "LANG_ROLES in ui/app.py — every mode has to state which box is the "
        "user's language and which is the other side's."
    )


def test_the_users_language_is_always_the_left_box():
    """Whatever the mode, the left picker is the user's own language.

    Media is the mode that tempts you to break this: there the audio being
    translated is the source, so the honest-looking layout puts the user on the
    right. Do that and switching modes silently reverses what the boxes mean —
    the user has to swap their two languages by hand to get the same result,
    and the first time they forget, chasqui translates a Japanese video into
    Japanese.
    """
    from chasqui.adapters import UI_ADAPTER_NAMES
    from chasqui.ui.app import LANG_ROLES

    for mode in UI_ADAPTER_NAMES:
        left, right = LANG_ROLES[mode]
        assert left.lower().startswith("i "), (
            f"Mode {mode!r} captions its LEFT box {left!r}. That box is the "
            "user's language in every mode — if this one really is the other "
            "side's, add the mode to LEFT_IS_TARGET so the pair is reversed on "
            "the way to Config instead of on screen."
        )
        assert not right.lower().startswith("i "), (
            f"Mode {mode!r} captions its RIGHT box {right!r}, claiming both "
            "boxes are the user's. One of them is the other side."
        )


def test_media_reverses_the_pair_on_the_way_to_config():
    """Keeping the user on the left means media's pair is flipped underneath."""
    from chasqui.ui.app import orient

    assert orient("es", "ja", "media") == ("ja", "es"), (
        "In media the left box is what the USER hears (target_lang) and the "
        "right is the audio being translated (source_lang). Without the flip, "
        "chasqui translates the user's own language into the video's."
    )
    assert orient("es", "ja", "headset") == ("es", "ja"), (
        "Every other mode maps left→source, right→target unchanged."
    )


def test_orient_is_its_own_inverse():
    """Boxes → config → boxes has to round-trip, or a saved session reloads
    with the two languages silently swapped."""
    from chasqui.adapters import UI_ADAPTER_NAMES
    from chasqui.ui.app import orient

    for mode in UI_ADAPTER_NAMES:
        assert orient(*orient("es", "ja", mode), mode) == ("es", "ja"), (
            f"orient() does not round-trip for {mode!r}."
        )


def test_only_bidirectional_modes_get_the_two_way_arrow():
    """The arrow is the only thing on screen that distinguishes a conversation
    from a broadcast. Pointing it both ways in a one-way mode promises a return
    channel that does not exist."""
    from chasqui.adapters import UI_ADAPTER_NAMES
    from chasqui.ui.app import BIDIRECTIONAL

    unknown = BIDIRECTIONAL - set(UI_ADAPTER_NAMES)
    assert not unknown, f"BIDIRECTIONAL names no such mode: {unknown}"
    assert "headset" in BIDIRECTIONAL, (
        "headset translates both ways — it is the flagship bidirectional mode."
    )
    assert "media" not in BIDIRECTIONAL and "virtual-mic" not in BIDIRECTIONAL, (
        "media and virtual-mic run a single pipeline. Marking them "
        "bidirectional tells the user to expect a reply channel that no "
        "adapter is running."
    )


def test_language_labels_round_trip():
    from chasqui.ui.app import _lang_code, _lang_label

    for code in ("es", "ja", "it"):
        assert _lang_code(_lang_label(code)) == code


def test_classify_levels():
    assert R.classify("  [warn] CABLE Input not found") == R.WARN
    assert R.classify("  [OUT error] connection refused") == R.ERROR
    assert R.classify("  [auto] Windows default mic → CABLE Output") == R.ACCENT
    assert R.classify("  Ready. Speak in ES.") == R.INFO
