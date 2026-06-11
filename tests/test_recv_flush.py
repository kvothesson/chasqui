"""Transcript flush behavior against a simulated translate-endpoint stream.

The translate endpoint streams deltas continuously and never emits "done"
events — the pipeline must flush transcripts on inactivity instead.
"""

import asyncio
import base64
import json

import pytest

from chasqui.core.audio import BytesStream
from chasqui.core.pipeline import Pipeline


class FakeWS:
    """Async-iterable that yields events, then stays silent."""

    def __init__(self, events, silence_s: float):
        self._events = [json.dumps(e) for e in events]
        self._silence_s = silence_s

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._events:
            return self._events.pop(0)
        await asyncio.sleep(self._silence_s)
        raise StopAsyncIteration


def _translate_events():
    audio = base64.b64encode(b"\x00\x01" * 100).decode()
    return [
        {"type": "session.input_transcript.delta", "delta": "hola "},
        {"type": "session.input_transcript.delta", "delta": "mundo"},
        {"type": "session.output_audio.delta", "delta": audio},
        {"type": "session.output_transcript.delta", "delta": "こんにちは"},
        {"type": "session.output_transcript.delta", "delta": "世界"},
        # no "done" event — this endpoint never sends one
    ]


@pytest.mark.asyncio
async def test_flush_fires_on_inactivity(monkeypatch):
    events = []
    p = Pipeline(
        source_lang="es", target_lang="ja", api_key="sk-test",
        model="gpt-realtime-translate", on_translation=events.append,
    )
    monkeypatch.setattr(Pipeline, "TRANSCRIPT_FLUSH_S", 0.1)

    out = BytesStream()
    # silence longer than flush threshold so the watchdog fires before stream ends
    await p._recv_audio(FakeWS(_translate_events(), silence_s=1.0), out)

    assert len(events) == 1
    assert events[0].source_text == "hola mundo"
    assert events[0].target_text == "こんにちは世界"
    assert out.output  # translated audio was written


@pytest.mark.asyncio
async def test_done_event_still_flushes():
    events = []
    p = Pipeline(
        source_lang="es", target_lang="ja", api_key="sk-test",
        model="gpt-realtime", on_translation=events.append,
    )
    evs = _translate_events() + [{"type": "response.done"}]
    await p._recv_audio(FakeWS(evs, silence_s=0.01), BytesStream())
    assert len(events) == 1
