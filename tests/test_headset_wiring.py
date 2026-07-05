"""Headset adapter wiring — regression tests for the live-found device bugs.

No audio hardware or network: every device/system call is replaced by a mock
that appends to an event log, and the assertions are about ORDER and ROUTING.

Covers (found live 2026-07-05):
  1. The default-mic switch must happen BEFORE PortAudio refresh, and the
     refresh BEFORE any name→index resolution. Windows renumbers live device
     IDs on a default switch, so resolve-then-switch opens the wrong device —
     the real-mic index pointed at CABLE Output and chasqui heard itself.
  2. Zero-config IN routing: with a second cable as IN capture, the default
     OUTPUT is switched to the cable's playback side and the earphone is
     pinned to the user's ORIGINAL output (never the new default — feedback).
  3. Both defaults are restored on exit, even when the run raises.
"""

import pytest

from chasqui.core.config import Config
from chasqui.adapters import headset as hs


class Log:
    def __init__(self):
        self.events = []

    def add(self, *event):
        self.events.append(event)

    def names(self):
        return [e[0] for e in self.events]

    def first(self, name):
        return self.names().index(name)


@pytest.fixture
def log(monkeypatch):
    log = Log()

    monkeypatch.setattr(hs, "get_default_input_name",
                        lambda: "Micrófono (HyperX Cloud III Wireless)")
    monkeypatch.setattr(hs, "get_default_output_name",
                        lambda: "Auriculares (HyperX Cloud III Wireless)")
    monkeypatch.setattr(hs, "set_default_input",
                        lambda hint: (log.add("set_default_input", hint), True)[1])
    monkeypatch.setattr(hs, "set_default_output",
                        lambda hint: (log.add("set_default_output", hint), True)[1])
    monkeypatch.setattr(hs, "refresh_devices", lambda: log.add("refresh_devices"))
    monkeypatch.setattr(hs, "resolve_device",
                        lambda name, want_input=True: (log.add("resolve_device", name), name)[1])

    monkeypatch.setattr(hs, "MicStream",
                        lambda device=None: log.add("MicStream", device))
    monkeypatch.setattr(hs, "LoopbackStream",
                        lambda device=None: log.add("LoopbackStream", device))
    monkeypatch.setattr(hs, "SpeakerStream",
                        lambda device=None: log.add("SpeakerStream", device))

    def fake_find_device(hints, override, require_output=False):
        if override:
            return override
        if any("CABLE Input" in h for h in hints):
            return "CABLE Input (VB-Audio Virtual C"
        if any("Stereo Mix" in h for h in hints):   # headset IN capture hints
            return "Hi-Fi Cable Output (VB-Audio Hi"
        return None

    monkeypatch.setattr(hs.HeadsetAdapter, "_find_device",
                        staticmethod(fake_find_device))
    monkeypatch.setattr(hs.HeadsetAdapter, "_make_pipeline", lambda self, **kw: None)
    monkeypatch.setattr(hs.HeadsetAdapter, "_make_pipeline_reverse", lambda self, **kw: None)
    monkeypatch.setattr(hs.HeadsetAdapter, "_run_parallel",
                        lambda self, out_tuple, in_tuple=None: log.add("run_parallel"))
    monkeypatch.setattr(hs.HeadsetAdapter, "_save_session_if_needed", lambda self: None)
    return log


def _run(log):
    cfg = Config()
    cfg.api_key = "sk-test"
    hs.HeadsetAdapter(cfg).run()
    return log


def test_switch_then_refresh_then_resolve(log):
    """Regression: resolving indices before the default switch opens the wrong
    device after Windows renumbers IDs (chasqui listened to its own cable)."""
    _run(log)
    assert log.first("set_default_input") < log.first("refresh_devices")
    assert log.first("set_default_output") < log.first("refresh_devices")
    assert log.first("refresh_devices") < log.first("resolve_device")


def test_zero_config_routes_output_and_pins_earphone(log):
    """With Hi-Fi Cable as IN capture: default output goes to the cable's
    playback side and the earphone is pinned to the ORIGINAL output."""
    _run(log)
    assert ("set_default_output", "Hi-Fi Cable Input") in log.events
    assert ("resolve_device", "Auriculares (HyperX Cloud III Wireless)") in log.events
    # the mic keeps following the original default mic, resolved by name
    assert ("resolve_device", "Micrófono (HyperX Cloud III Wireless)") in log.events


def test_defaults_restored_on_exit(log):
    _run(log)
    restores = [e for e in log.events
                if e[0].startswith("set_default") and "HyperX" in e[1]]
    assert ("set_default_input", "Micrófono (HyperX Cloud III Wireless)") in restores
    assert ("set_default_output", "Auriculares (HyperX Cloud III Wireless)") in restores


def test_defaults_restored_even_on_crash(log, monkeypatch):
    monkeypatch.setattr(hs.HeadsetAdapter, "_run_parallel",
                        lambda self, out_tuple, in_tuple=None:
                        (_ for _ in ()).throw(RuntimeError("boom")))
    cfg = Config()
    cfg.api_key = "sk-test"
    with pytest.raises(RuntimeError):
        hs.HeadsetAdapter(cfg).run()
    assert ("set_default_input", "Micrófono (HyperX Cloud III Wireless)") in log.events
    assert ("set_default_output", "Auriculares (HyperX Cloud III Wireless)") in log.events


def test_explicit_earphone_wins_over_original_output(log, monkeypatch):
    cfg = Config()
    cfg.api_key = "sk-test"
    cfg.device.earphone = "Mi Parlante Custom"
    hs.HeadsetAdapter(cfg).run()
    assert ("resolve_device", "Mi Parlante Custom") in log.events
    assert ("resolve_device", "Auriculares (HyperX Cloud III Wireless)") not in log.events
