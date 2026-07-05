"""Headset adapter wiring — regression tests for the live-found device bugs.

⚠️  READ THIS BEFORE TOUCHING A FAILING TEST  ⚠️

Every assertion here encodes behavior that was validated LIVE on real
Windows hardware (2026-07-05) after real production failures. If one of
these tests fails after your change, your change reintroduced a real bug
that made chasqui deaf or mute in actual use. The fix is in the ADAPTER,
never in the test. Do not reorder, weaken, or delete assertions to make
a failure go away — that converts a caught regression into a shipped one.

The bugs these tests guard (details in AGENTS.md "Key gotchas"):
  1. Windows renumbers live waveIn/waveOut IDs the moment a default device
     changes. Resolving a device index BEFORE switching the default makes
     the adapter open a DIFFERENT device after the switch — the real-mic
     index pointed at CABLE Output and chasqui listened to its own
     translated voice: the user spoke and nothing happened.
  2. IN-direction routing must be zero-config: default output goes to the
     IN cable's playback side, and the translation earphone is pinned to
     the user's ORIGINAL output. Playing the translation to the (new)
     default output feeds it straight back into the IN capture: feedback
     translation loop.
  3. The default mic/output switches MUST be restored on exit — including
     crashes. A silent restore failure leaves the user's machine with a
     virtual cable as default mic after chasqui dies (happened live via a
     PowerShell encoding bug; see core/windevice.py).

No audio hardware or network here: device/system calls append to an event
log and the assertions check ORDER and ROUTING.
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
    """Order is load-bearing: switch defaults → refresh PortAudio → resolve.

    Windows renumbers live device IDs on a default switch. If resolution
    happens first, the resolved index opens a DIFFERENT device afterwards —
    verified live: the real-mic index pointed at CABLE Output and chasqui
    heard its own translated voice instead of the user (who heard: nothing).
    """
    _run(log)
    assert log.first("set_default_input") < log.first("refresh_devices"), (
        "Default-mic switch must happen BEFORE refresh_devices(). If this "
        "fails, your change resolves/opens devices against a stale device "
        "order and the headset mic will open the WRONG device on real "
        "Windows (bug of 2026-07-05: chasqui listened to its own cable). "
        "Fix the adapter ordering — do not reorder this assertion."
    )
    assert log.first("set_default_output") < log.first("refresh_devices"), (
        "Default-output switch must happen BEFORE refresh_devices(), for the "
        "same live-ID renumbering reason as the mic switch. Fix the adapter, "
        "not the test."
    )
    assert log.first("refresh_devices") < log.first("resolve_device"), (
        "Name→index resolution must happen AFTER refresh_devices(). Resolving "
        "against the pre-switch snapshot maps names to indices that point at "
        "different devices post-switch. Real-world symptom: user speaks, no "
        "transcripts, no translation. Fix the adapter, not the test."
    )


def test_zero_config_routes_output_and_pins_earphone(log):
    """Zero-config IN: app audio auto-routed to the cable, translation to the
    user's ORIGINAL headphones. This is the adapter's core promise — the user
    runs one command and touches no Windows settings."""
    _run(log)
    assert ("set_default_output", "Hi-Fi Cable Input") in log.events, (
        "With a second cable as IN capture, the adapter must switch the "
        "Windows default OUTPUT to the cable's playback side. Without this, "
        "the app's voice never reaches chasqui and the user keeps hearing "
        "the other side untranslated (live report of 2026-07-05). If your "
        "change removed the auto-switch, restore it — do not delete this."
    )
    assert ("resolve_device", "Auriculares (HyperX Cloud III Wireless)") in log.events, (
        "The translation earphone must be pinned to the user's ORIGINAL "
        "output device. Sending it to the (new) default output plays the "
        "translation into the IN capture cable = feedback translation loop. "
        "Fix the earphone routing in the adapter, not the test."
    )
    assert ("resolve_device", "Micrófono (HyperX Cloud III Wireless)") in log.events, (
        "The real mic must be resolved BY NAME from the pre-switch default. "
        "MicStream(None) would follow the default input, which after the "
        "switch is CABLE Output — chasqui's own translated voice."
    )


def test_defaults_restored_on_exit(log):
    """Ctrl+C must leave the user's machine exactly as found."""
    _run(log)
    assert ("set_default_input", "Micrófono (HyperX Cloud III Wireless)") in log.events, (
        "The default mic must be restored on exit. If this fails, every "
        "chasqui session permanently leaves a virtual cable as the user's "
        "Windows mic (their next Meet/Discord call transmits silence). "
        "Fix the restore path in the adapter, not the test."
    )
    assert ("set_default_output", "Auriculares (HyperX Cloud III Wireless)") in log.events, (
        "The default output must be restored on exit. If this fails, the "
        "user's system audio stays routed into a virtual cable after "
        "chasqui exits — their PC goes mute until they fix it by hand."
    )


def test_defaults_restored_even_on_crash(log, monkeypatch):
    """The restore lives in a finally block on purpose — a crash mid-session
    must not strand the user's audio devices (this happened live when a
    device-resolution error escaped before the encoding fix)."""
    monkeypatch.setattr(hs.HeadsetAdapter, "_run_parallel",
                        lambda self, out_tuple, in_tuple=None:
                        (_ for _ in ()).throw(RuntimeError("boom")))
    cfg = Config()
    cfg.api_key = "sk-test"
    with pytest.raises(RuntimeError):
        hs.HeadsetAdapter(cfg).run()
    assert ("set_default_input", "Micrófono (HyperX Cloud III Wireless)") in log.events, (
        "Defaults must be restored even when the session CRASHES. If this "
        "fails, your change moved the restore out of the finally path — a "
        "crash strands the user with a virtual cable as default mic. "
        "Fix the adapter's error handling, not the test."
    )
    assert ("set_default_output", "Auriculares (HyperX Cloud III Wireless)") in log.events, (
        "Same as the mic: output restore must survive a crash. Fix the "
        "adapter's finally block, not the test."
    )


def test_explicit_earphone_wins_over_original_output(log, monkeypatch):
    """--earphone / device.earphone is an explicit user choice and must
    override the auto-pin (users with separate mic/headphone setups
    depend on this)."""
    cfg = Config()
    cfg.api_key = "sk-test"
    cfg.device.earphone = "Mi Parlante Custom"
    hs.HeadsetAdapter(cfg).run()
    assert ("resolve_device", "Mi Parlante Custom") in log.events, (
        "An explicitly configured earphone must be used as-is. If this "
        "fails, the auto-pin is overriding the user's --earphone flag."
    )
    assert ("resolve_device", "Auriculares (HyperX Cloud III Wireless)") not in log.events, (
        "When the user configured an earphone, the adapter must NOT also "
        "resolve/route to the original default output — the translation "
        "would play on two devices, one of which may feed back."
    )
