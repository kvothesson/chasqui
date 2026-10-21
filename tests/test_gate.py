"""Silence gate and passthrough mix: pure byte logic, no audio hardware."""

import asyncio
import json

import numpy as np

from chasqui.core.audio import BytesStream, PassthroughMixStream, TeeInputStream
from chasqui.core.config import Config
from chasqui.core.gate import BYTES_PER_MS, SilenceGate, rms_dbfs
from chasqui.core.pipeline import Pipeline

CHUNK_MS = 100


def tone(ms: int = CHUNK_MS, amplitude: int = 3000) -> bytes:
    n = ms * BYTES_PER_MS // 2
    t = np.arange(n) / 24000
    return (amplitude * np.sin(2 * np.pi * 220 * t)).astype("<i2").tobytes()


def silence(ms: int = CHUNK_MS) -> bytes:
    return bytes(ms * BYTES_PER_MS)


def hiss(ms: int = CHUNK_MS, amplitude: int = 20) -> bytes:
    rng = np.random.default_rng(0)
    return rng.integers(-amplitude, amplitude, ms * BYTES_PER_MS // 2).astype("<i2").tobytes()


def run(gate: SilenceGate, chunks: list[bytes]) -> list[bytes]:
    out = []
    for c in chunks:
        out.extend(gate.feed(c))
    return out


# --- levels -----------------------------------------------------------------

def test_rms_of_digital_silence_is_minus_infinity():
    assert rms_dbfs(silence()) == float("-inf")


def test_rms_orders_hiss_below_threshold_and_voice_above():
    assert rms_dbfs(hiss()) < -50 < rms_dbfs(tone())


# --- gate -------------------------------------------------------------------

def test_leading_silence_is_never_sent():
    gate = SilenceGate(preroll_ms=0)
    assert run(gate, [silence()] * 20) == []
    assert gate.bytes_skipped == 20 * CHUNK_MS * BYTES_PER_MS


def test_speech_opens_the_gate_with_preroll_first():
    gate = SilenceGate(preroll_ms=300)
    quiet = [hiss() for _ in range(10)]
    out = run(gate, quiet + [tone()])
    # the last 300ms of quiet, then the speech
    assert out == quiet[-3:] + [tone()]


def test_pauses_shorter_than_hold_are_sent():
    gate = SilenceGate(hold_ms=3000, preroll_ms=0)
    chunks = [tone()] + [silence()] * 10 + [tone()]   # 1s pause
    assert run(gate, chunks) == chunks


def test_gate_closes_after_hold_and_stops_sending():
    gate = SilenceGate(hold_ms=500, preroll_ms=0)
    out = run(gate, [tone()] + [silence()] * 20)
    assert len(out) == 1 + 5          # the speech plus 500ms of tail
    assert not gate.is_open


def test_a_noisy_room_just_keeps_it_open():
    gate = SilenceGate(threshold_dbfs=-50)
    loud_room = [hiss(amplitude=400) for _ in range(30)]
    assert rms_dbfs(loud_room[0]) > -50
    assert run(gate, loud_room) == loud_room


# --- pipeline wiring --------------------------------------------------------

class _FakeWs:
    def __init__(self):
        self.sent = []

    async def send(self, msg):
        self.sent.append(json.loads(msg))


def _send_all(pipeline: Pipeline, data: bytes) -> _FakeWs:
    ws = _FakeWs()
    stream = BytesStream(data)

    async def go():
        task = asyncio.create_task(pipeline._send_audio(ws, stream))
        await asyncio.sleep(0.3)
        pipeline.stop()
        await task

    asyncio.run(go())
    return ws


def test_pipeline_without_gate_bills_everything():
    p = Pipeline("es", "en", api_key="x")
    _send_all(p, tone() + silence(3000))
    assert p.usage.audio_bytes_sent == len(tone() + silence(3000))


def test_pipeline_with_gate_bills_only_what_it_sent():
    p = Pipeline("es", "en", api_key="x", silence_gate=True, gate_hold_ms=500)
    ws = _send_all(p, tone() + silence(3000))
    assert p.usage.audio_bytes_sent == len(tone()) + 500 * BYTES_PER_MS
    assert len(ws.sent) == 6


def test_config_reads_gate_and_passthrough():
    cfg = Config._from_dict({"silence_gate": True, "silence_gate_dbfs": -45,
                             "silence_gate_hold_ms": 900, "passthrough": 0.2})
    assert (cfg.silence_gate, cfg.silence_gate_dbfs, cfg.silence_gate_hold_ms,
            cfg.passthrough) == (True, -45, 900, 0.2)
    assert Config().silence_gate is False and Config().passthrough == 0.0


# --- passthrough ------------------------------------------------------------

def test_passthrough_mixes_original_under_translation():
    dst = BytesStream()
    mix = PassthroughMixStream(dst, gain=0.5)
    original = np.full(2400, 1000, dtype="<i2").tobytes()
    translated = np.full(2400, 200, dtype="<i2").tobytes()

    mic = TeeInputStream(BytesStream(original), mix.feed_side)
    mic.read(len(original))
    mix.write(translated)

    assert set(np.frombuffer(dst.output, dtype="<i2")) == {700}


def test_passthrough_clips_instead_of_wrapping():
    dst = BytesStream()
    mix = PassthroughMixStream(dst, gain=1.0)
    mix.feed_side(np.full(100, 30000, dtype="<i2").tobytes())
    mix.write(np.full(100, 30000, dtype="<i2").tobytes())
    assert set(np.frombuffer(dst.output, dtype="<i2")) == {32767}


def test_passthrough_does_not_pile_up_without_translation():
    dst = BytesStream()
    mix = PassthroughMixStream(dst, gain=0.5, max_lag_ms=200)
    for _ in range(10):
        mix.feed_side(tone())          # 1s of original, no translation
    assert len(dst.output) == 800 * BYTES_PER_MS


def test_adapters_only_wrap_when_passthrough_is_on(monkeypatch):
    from chasqui.adapters.text import TextAdapter

    # TextAdapter builds an OpenAI client, which refuses to exist without a key (CI has none).
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    mic, app = BytesStream(), BytesStream()
    off = TextAdapter(Config())
    assert off._with_passthrough(mic, app) == (mic, app)

    on = TextAdapter(Config(passthrough=0.15))
    tee, mix = on._with_passthrough(mic, app)
    assert isinstance(tee, TeeInputStream) and isinstance(mix, PassthroughMixStream)
    assert mix.gain == 0.15
