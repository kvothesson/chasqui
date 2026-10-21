"""Isolated turns: each transcript translated by its own out-of-band response.

The fix for conversational drift on gpt-realtime — the model answering a short
question instead of interpreting it. These tests pin the protocol: no
automatic responses, one `response.create` per transcript with no history,
and turns paired with their own translation even when speech overlaps.
"""

import asyncio
import json

import pytest

from chasqui.core.audio import BytesStream
from chasqui.core.pipeline import Pipeline


class FakeWS:
    """Yields scripted events; `respond_after_send` events wait for a send."""

    def __init__(self, script):
        self._script = list(script)
        self.sent: list[dict] = []
        self._sent_event = asyncio.Event()

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))
        self._sent_event.set()

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._script:
            raise StopAsyncIteration
        item = self._script.pop(0)
        if item == "WAIT_SEND":
            await asyncio.wait_for(self._sent_event.wait(), timeout=1)
            self._sent_event.clear()
            return await self.__anext__()
        return json.dumps(item)


def _pipeline(events, model="gpt-realtime", isolate=True):
    return Pipeline(
        source_lang="es", target_lang="ja", api_key="sk-test",
        model=model, on_translation=events.append, isolate_turns=isolate,
    )


def _translation(text):
    return [
        {"type": "response.output_audio_transcript.delta", "delta": text},
        {"type": "response.done", "response": {}},
    ]


def test_session_turns_off_automatic_responses():
    detection = _pipeline([])._build_session_update()["session"]["audio"]["input"]["turn_detection"]
    assert detection["create_response"] is False, (
        "with automatic responses on, the model still answers inside the "
        "conversation and the isolated translation plays on top of it"
    )
    assert detection["interrupt_response"] is False


def test_default_session_is_unchanged():
    detection = _pipeline([], isolate=False)._build_session_update()["session"]["audio"]["input"]["turn_detection"]
    assert "create_response" not in detection


def test_translate_model_ignores_isolation():
    # gpt-realtime-translate takes no instructions and no response.create.
    assert _pipeline([], model="gpt-realtime-translate").isolate_turns is False


def test_response_has_no_history_and_quotes_the_words():
    req = _pipeline([])._build_isolated_response("¿Llegaste bien?")
    assert req["type"] == "response.create"
    assert req["response"]["conversation"] == "none"
    [message] = req["response"]["input"]
    assert "«¿Llegaste bien?»" in message["content"][0]["text"]


@pytest.mark.asyncio
async def test_each_transcript_gets_its_own_translation():
    events = []
    ws = FakeWS([
        {"type": "input_audio_buffer.speech_started"},
        {"type": "conversation.item.input_audio_transcription.completed", "transcript": "¿Llegaste bien?"},
        "WAIT_SEND",
        *_translation("無事に着いた？"),
    ])
    await _pipeline(events)._recv_audio(ws, BytesStream())

    assert [s["response"]["input"][0]["content"][0]["text"].split("«")[1] for s in ws.sent] == [
        "¿Llegaste bien?»"
    ]
    assert len(events) == 1
    assert events[0].source_text == "¿Llegaste bien?"
    assert events[0].target_text == "無事に着いた？"


@pytest.mark.asyncio
async def test_overlapping_turns_queue_and_stay_paired():
    events = []
    ws = FakeWS([
        {"type": "conversation.item.input_audio_transcription.completed", "transcript": "uno"},
        "WAIT_SEND",
        # The user speaks again while the first translation is still playing.
        {"type": "input_audio_buffer.speech_started"},
        {"type": "conversation.item.input_audio_transcription.completed", "transcript": "dos"},
        *_translation("一"),
        "WAIT_SEND",
        *_translation("二"),
    ])
    await _pipeline(events)._recv_audio(ws, BytesStream())

    assert len(ws.sent) == 2, "the second turn must wait for the first response.done"
    assert [(e.source_text, e.target_text) for e in events] == [("uno", "一"), ("dos", "二")]


@pytest.mark.asyncio
async def test_noise_transcripts_are_not_translated():
    ws = FakeWS([
        {"type": "conversation.item.input_audio_transcription.completed", "transcript": "  "},
    ])
    await _pipeline([])._recv_audio(ws, BytesStream())
    assert ws.sent == []
