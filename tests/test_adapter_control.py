"""Programmatic stop — what the UI's Stop button and window-close rely on.

The CLI ends a session with Ctrl+C. The UI has no such thing: it calls
`adapter.stop()` from the Tk thread and the session has to unwind through the
SAME path, because that path is what restores the user's Windows default mic
and output. A stop that doesn't reach the pipelines leaves the machine with a
virtual cable as its microphone after chasqui exits.

No audio hardware or network here: pipelines and streams are fakes.
"""

import threading

import pytest

from chasqui.adapters import ADAPTER_NAMES, ADAPTER_PATHS, build_adapter, get_adapter_class
from chasqui.adapters.base import BaseAdapter
from chasqui.adapters.bridge import BridgeAdapter
from chasqui.core.config import Config
from chasqui.core.pipeline import TranslationEvent


class _Adapter(BaseAdapter):
    def run(self) -> None:  # pragma: no cover - never started in these tests
        pass


def _config() -> Config:
    cfg = Config()
    cfg.api_key = "sk-test"
    return cfg


# ---------------------------------------------------------------------------
# stop() reaches the pipelines
# ---------------------------------------------------------------------------


def test_stop_stops_every_pipeline():
    adapter = _Adapter(_config())
    out = adapter._make_pipeline()
    back = adapter._make_pipeline_reverse()

    adapter.stop()

    assert out._stop_event.is_set() and back._stop_event.is_set(), (
        "stop() must stop every pipeline the adapter built, in both "
        "directions. If this fails, the UI's Stop button leaves the realtime "
        "sockets streaming and burning tokens after the user stopped. Make "
        "_make_pipeline/_make_pipeline_reverse register with _register()."
    )


def test_pipeline_built_after_stop_is_born_stopped():
    """Stop can land in the window between stop() and a pipeline existing."""
    adapter = _Adapter(_config())
    adapter.stop()

    late = adapter._make_pipeline()

    assert late._stop_event.is_set(), (
        "A pipeline created after stop() must not start a session nobody "
        "asked for. If this fails, hitting Stop while an adapter is still "
        "wiring itself up opens a realtime connection that no one will "
        "close. Fix _register(), not the test."
    )


def test_run_parallel_returns_on_external_stop():
    """The Stop button must break `_run_parallel`'s wait loop.

    `_run_parallel` blocks until its stop event fires. If it uses a private
    event instead of the adapter's, an external stop() kills the pipelines but
    the loop keeps spinning — the session never reaches its `finally`, so the
    Windows default mic/output are never restored.
    """
    class _Pipeline:
        def __init__(self):
            self.done = threading.Event()

        def run(self, _in, _out):
            self.done.wait(timeout=5)

        def stop(self):
            self.done.set()

    class _Stream:
        def start(self):
            pass

        def close(self):
            pass

    adapter = BridgeAdapter(_config())
    pipeline = _Pipeline()
    adapter._pipelines.append(pipeline)

    threading.Timer(0.2, adapter.stop).start()

    finished = threading.Event()

    def _go():
        adapter._run_parallel((pipeline, _Stream(), _Stream()))
        finished.set()

    thread = threading.Thread(target=_go, daemon=True)
    thread.start()
    thread.join(timeout=5)

    assert finished.is_set(), (
        "_run_parallel must wait on the ADAPTER's stop event (self._stop), "
        "not a fresh one. If this fails, the UI's Stop button hangs the "
        "session thread and the adapter's finally block never runs: the "
        "user's Windows default mic stays pointed at a virtual cable after "
        "chasqui closes. Fix bridge._run_parallel, not the test."
    )


# ---------------------------------------------------------------------------
# on_turn hook — how the UI gets transcripts without scraping stdout
# ---------------------------------------------------------------------------


def test_on_turn_fires_with_direction():
    adapter = _Adapter(_config())
    seen = []
    adapter.on_turn = lambda event, direction: seen.append((direction, event.target_text))

    out = adapter._make_pipeline()
    back = adapter._make_pipeline_reverse()
    out.on_translation(TranslationEvent(source_text="hola", target_text="こんにちは"))
    back.on_translation(TranslationEvent(source_text="こんにちは", target_text="hola"))

    assert seen == [("out", "こんにちは"), ("in", "hola")], (
        "Both pipelines must report completed turns through on_turn, tagged "
        "with their direction. The UI colors your side and theirs from this "
        "tag; without it the transcript is an undistinguishable wall of text."
    )


def test_on_turn_error_does_not_kill_the_session():
    adapter = _Adapter(_config())
    adapter.on_turn = lambda event, direction: 1 / 0

    pipeline = adapter._make_pipeline()
    pipeline.on_translation(TranslationEvent(source_text="hola", target_text="こんにちは"))

    assert adapter._session.turns, (
        "A listener that raises must not take the audio session down. If "
        "this fails, one UI bug ends a live conversation mid-sentence."
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_every_registered_adapter_imports():
    """The registry is the CLI's --adapter choices and the UI's mode list."""
    for name in ADAPTER_NAMES:
        assert issubclass(get_adapter_class(name), BaseAdapter), (
            f"Adapter {name!r} in ADAPTER_PATHS must resolve to a BaseAdapter "
            "subclass. A typo here is a broken menu entry in the UI and a "
            "crash on `chasqui listen --adapter " + name + "`."
        )


def test_unknown_adapter_lists_the_valid_ones():
    cfg = _config()
    cfg.adapter = "nope"
    with pytest.raises(KeyError) as excinfo:
        build_adapter(cfg)
    assert "headset" in str(excinfo.value), (
        "An unknown adapter name must come back with the list of valid ones — "
        "that message is what the CLI prints to the user."
    )


def test_registry_covers_the_adapters_package():
    assert set(ADAPTER_PATHS) == set(ADAPTER_NAMES)
