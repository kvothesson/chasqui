"""Media adapter wiring — regression test for the mic-instead-of-video bug.

⚠️  READ THIS BEFORE TOUCHING A FAILING TEST  ⚠️

Media mode listens to what the computer is PLAYING. The one way to get that
catastrophically wrong is to open the default input instead, which on every
machine is the user's microphone: chasqui then translates the user, live, while
they wait to understand a video that is never being read. It shipped exactly
that way — the adapter resolved the right capture device into a local and then
handed `LoopbackStream` the raw config value, which is None unless the user set
device.loopback by hand.

As in test_headset_wiring.py: the fix belongs in the ADAPTER, never here.

No audio hardware or network — device calls append to an event log.
"""

import pytest

from chasqui.core.config import Config
from chasqui.adapters import media as md


class FakeStream:
    def __init__(self, device=None):
        self.device = device

    def start(self):
        pass

    def close(self):
        pass


class FakePipeline:
    def __init__(self):
        self.ran_with = None

    def run(self, in_stream, out_stream):
        self.ran_with = (in_stream, out_stream)

    def stop(self):
        pass


class Log:
    def __init__(self):
        self.events = []
        self.loopback = None
        self.speaker = None

    def add(self, *event):
        self.events.append(event)

    def names(self):
        return [e[0] for e in self.events]

    def first(self, name):
        return self.names().index(name)


@pytest.fixture
def log(monkeypatch):
    log = Log()

    def fake_loopback(device=None):
        log.add("LoopbackStream", device)
        log.loopback = FakeStream(device)
        return log.loopback

    def fake_speaker(device=None):
        log.add("SpeakerStream", device)
        log.speaker = FakeStream(device)
        return log.speaker

    def fake_find(hints, override=None, require_output=False):
        log.add("find_device_by_hints", override)
        return override or "CABLE Output (VB-Audio Virtual"

    monkeypatch.setattr(md, "get_default_output_name", lambda: "Auriculares (HyperX Cloud III)")
    monkeypatch.setattr(md, "set_default_output",
                        lambda hint: (log.add("set_default_output", hint), True)[1])
    monkeypatch.setattr(md, "refresh_devices", lambda: log.add("refresh_devices"))
    monkeypatch.setattr(md, "resolve_device",
                        lambda name, want_input=True: (log.add("resolve_device", name), name)[1])
    monkeypatch.setattr(md, "find_device_by_hints", fake_find)
    monkeypatch.setattr(md, "LoopbackStream", fake_loopback)
    monkeypatch.setattr(md, "SpeakerStream", fake_speaker)
    monkeypatch.setattr(md, "NullStream", FakeStream)
    monkeypatch.setattr(md.MediaAdapter, "_make_pipeline", lambda self, **kw: FakePipeline())
    monkeypatch.setattr(md.MediaAdapter, "_save_session_if_needed", lambda self: None)
    return log


def _run(config: Config = None) -> None:
    cfg = config or Config()
    cfg.api_key = "sk-test"
    md.MediaAdapter(cfg).run()


def test_captures_the_found_device_not_the_raw_config(log):
    """The whole bug in one assertion.

    With no device.loopback in chasqui.yaml, passing the config value straight
    through hands LoopbackStream None — and None means "default input", the
    microphone. The user watches a Japanese video and chasqui dutifully
    translates their own breathing.
    """
    _run()
    assert ("LoopbackStream", "CABLE Output (VB-Audio Virtual") in log.events, (
        "The loopback stream must open the device found by "
        "find_device_by_hints, not config.device.loopback. If this fails, "
        "media mode with an unconfigured yaml captures the user's MICROPHONE "
        "instead of their system audio — it translates them, not the video. "
        "Fix the adapter, not the test."
    )
    assert ("LoopbackStream", None) not in log.events, (
        "LoopbackStream(None) opens the default input. There is no case where "
        "media mode wants that."
    )


def test_explicit_loopback_still_wins(log):
    cfg = Config()
    cfg.device.loopback = "Mi Captura Custom"
    _run(cfg)
    assert ("LoopbackStream", "Mi Captura Custom") in log.events, (
        "An explicitly configured device.loopback must be used as-is — it is "
        "the escape hatch for machines where autodetection picks wrong."
    )


def test_capture_is_found_before_the_default_switch(log):
    """Same live-ID renumbering rule the headset adapter follows: Windows
    reorders device IDs when a default changes, so the device is located by
    NAME first, and only resolved to an index after refresh_devices()."""
    _run()
    assert log.first("find_device_by_hints") < log.first("set_default_output"), (
        "The capture device must be found BEFORE the default output switch. "
        "Searching afterwards means searching a reordered device list."
    )
    assert log.first("set_default_output") < log.first("refresh_devices"), (
        "refresh_devices() must run AFTER the switch — that is what makes "
        "PortAudio see the new ordering."
    )
    assert log.first("refresh_devices") < log.first("resolve_device"), (
        "Name→index resolution must happen after refresh_devices(), or the "
        "index points at whatever device used to hold that slot."
    )


def test_earphone_avoids_the_capture_cable(log):
    """Playing the translation to the new default output feeds it back into
    the loopback being read: chasqui translating its own translation."""
    _run()
    assert ("SpeakerStream", "Auriculares (HyperX Cloud III)") in log.events, (
        "With no explicit earphone, the translation must go to the user's "
        "ORIGINAL output, not the default — the default is the capture cable "
        "now, and that is a feedback loop."
    )


def test_output_restored_on_exit(log):
    _run()
    assert ("set_default_output", "Auriculares (HyperX Cloud III)") in log.events, (
        "The default output must be restored on exit, or the user's PC stays "
        "routed into a virtual cable and goes silent after chasqui quits."
    )
