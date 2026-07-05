"""In-memory stream behavior (no audio hardware needed)."""

import sys
import types

from chasqui.core.audio import BytesStream, MultiOutputStream, NullStream, resolve_device


def test_bytes_stream_roundtrip():
    s = BytesStream(b"abcdef")
    assert s.read(4) == b"abcd"
    assert s.read(4) == b"ef"
    assert s.read(4) == b""

    s.write(b"out1")
    s.write(b"out2")
    assert s.output == b"out1out2"


def test_multi_output_fans_out():
    a, b = BytesStream(), BytesStream()
    multi = MultiOutputStream(a, b)
    multi.write(b"data")
    assert a.output == b"data"
    assert b.output == b"data"


def test_null_stream_is_noop():
    s = NullStream()
    s.write(b"data")
    assert s.read() == b""
    s.close()


# ---------------------------------------------------------------------------
# resolve_device — Windows full names vs PortAudio truncated names
# ---------------------------------------------------------------------------

_FAKE_DEVICES = [
    {"name": "Micrófono (2- USB Audio Devic", "max_input_channels": 2, "max_output_channels": 0},
    {"name": "CABLE Output (VB-Audio Virtual", "max_input_channels": 2, "max_output_channels": 0},
    {"name": "Altavoces (Realtek(R) Audio)", "max_input_channels": 0, "max_output_channels": 2},
    {"name": "Auriculares (WH-1000XM4)", "max_input_channels": 0, "max_output_channels": 2},
]


def _with_fake_sounddevice(monkeypatch):
    fake = types.ModuleType("sounddevice")
    fake.query_devices = lambda: _FAKE_DEVICES
    monkeypatch.setitem(sys.modules, "sounddevice", fake)


def test_resolve_device_full_windows_name_matches_truncated(monkeypatch):
    _with_fake_sounddevice(monkeypatch)
    # PowerShell reports the full name; PortAudio has it truncated
    assert resolve_device("Micrófono (2- USB Audio Device)", want_input=True) == 0


def test_resolve_device_respects_kind(monkeypatch):
    _with_fake_sounddevice(monkeypatch)
    # substring "a" alone would match input devices too — kind filters them out
    assert resolve_device("Auriculares (WH-1000XM4)", want_input=False) == 3
    assert resolve_device("Altavoces", want_input=True) == "Altavoces"  # no input match → passthrough


def test_resolve_device_passthrough():
    assert resolve_device(None) is None
    assert resolve_device(3) == 3
    assert resolve_device("7") == 7
