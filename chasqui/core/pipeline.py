"""Core translation pipeline — supports gpt-realtime-translate (GA) and gpt-realtime."""

import asyncio
import base64
import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import websockets

from .audio import AudioStream
from .constants import LANG_NAMES, REALTIME_URL, REALTIME_TRANSLATE_URL

# Language codes → full names used by gpt-realtime-translate
TRANSLATE_LANG_NAMES = {
    "es": "spanish", "ja": "japanese", "en": "english",
    "fr": "french",  "pt": "portuguese", "zh": "chinese",
    "de": "german",  "it": "italian",    "ko": "korean",
    "ar": "arabic",  "ru": "russian",    "hi": "hindi",
}


@dataclass
class TranslationEvent:
    source_text: str = ""
    target_text: str = ""
    latency_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def __str__(self) -> str:
        return f"[{self.latency_ms:.0f}ms] {self.source_text!r} → {self.target_text!r}"


class Pipeline:
    """Real-time translation pipeline over WebSocket.

    Automatically selects the correct session format and event names
    based on the model:
      - gpt-realtime-translate  →  translation session (cheap, fast, purpose-built)
      - gpt-realtime / others   →  standard realtime session with instructions

    Usage::

        pipeline = Pipeline(source_lang="es", target_lang="ja", api_key="sk-...")
        pipeline.run(mic_stream, speaker_stream)   # blocks until stop() or Ctrl+C
    """

    def __init__(
        self,
        source_lang: str,
        target_lang: str,
        api_key: str,
        model: str = "gpt-realtime-translate",
        context: str = "",
        voice: str = "alloy",
        on_translation: Optional[Callable[[TranslationEvent], None]] = None,
        vad_threshold: float = 0.5,
        vad_silence_ms: int = 600,
    ):
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.api_key = api_key
        self.model = model
        self.context = context
        self.voice = voice
        self.on_translation = on_translation
        self.vad_threshold = vad_threshold
        self.vad_silence_ms = vad_silence_ms
        self._stop_event = threading.Event()
        self._is_translate_model = "translate" in model
        # CHASQUI_DEBUG=1 prints every server event type and audio send stats
        self._debug = os.environ.get("CHASQUI_DEBUG", "") not in ("", "0")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, input_stream: AudioStream, output_stream: AudioStream) -> None:
        """Blocking. Translates from input_stream to output_stream."""
        asyncio.run(self._run_async(input_stream, output_stream))

    def stop(self) -> None:
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    MAX_RECONNECT_ATTEMPTS = 5

    async def _run_async(self, input_stream: AudioStream, output_stream: AudioStream) -> None:
        """Connect and translate; reconnect with backoff if the socket drops."""
        attempt = 0
        while not self._stop_event.is_set():
            try:
                await self._connect_and_translate(input_stream, output_stream)
                return  # clean exit (stop() was called)
            except (websockets.ConnectionClosed, OSError) as e:
                if self._stop_event.is_set():
                    return
                attempt += 1
                if attempt > self.MAX_RECONNECT_ATTEMPTS:
                    raise RuntimeError(
                        f"Connection lost and {self.MAX_RECONNECT_ATTEMPTS} reconnect attempts failed: {e}"
                    ) from e
                delay = min(2 ** attempt, 10)
                print(f"  [chasqui] connection dropped ({e}); reconnecting in {delay}s...", flush=True)
                await asyncio.sleep(delay)

    async def _connect_and_translate(
        self, input_stream: AudioStream, output_stream: AudioStream
    ) -> None:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        base_url = REALTIME_TRANSLATE_URL if self._is_translate_model else REALTIME_URL
        url = f"{base_url}?model={self.model}"

        async with websockets.connect(
            url,
            additional_headers=headers,
            ping_interval=20,
            ping_timeout=10,
        ) as ws:
            await self._wait_for_session(ws)
            await ws.send(json.dumps(self._build_session_update()))

            send_task = asyncio.create_task(self._send_audio(ws, input_stream))
            recv_task = asyncio.create_task(self._recv_audio(ws, output_stream))

            # First task to finish (stop(), socket close, or error) ends the session;
            # the sibling is cancelled so stop() can't leave recv hanging forever.
            done, pending = await asyncio.wait(
                {send_task, recv_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            for task in done:
                exc = task.exception()
                if exc is not None and not isinstance(exc, asyncio.CancelledError):
                    raise exc

    async def _wait_for_session(self, ws) -> None:
        async for raw in ws:
            event = json.loads(raw)
            t = event.get("type", "")
            if t in ("session.created", "translation_session.created"):
                return
            if t == "error":
                raise RuntimeError(f"Session error: {event}")

    # ------------------------------------------------------------------
    # Session configuration (model-aware)
    # ------------------------------------------------------------------

    def _build_session_update(self) -> dict:
        if self._is_translate_model:
            return self._build_translate_session()
        return self._build_realtime_session()

    def _build_translate_session(self) -> dict:
        """Session format for gpt-realtime-translate.

        Specialized model: no instructions, no voice selection.
        Session type is always "realtime" — translation is handled by the model.
        Target language set via audio.output.language.
        """
        return {
            "type": "session.update",
            "session": {
                "audio": {
                    "input": {
                        "transcription": {"model": "gpt-realtime-whisper"},
                        "noise_reduction": {"type": "near_field"},
                    },
                    "output": {
                        "language": self.target_lang,
                    },
                },
            },
        }

    def _build_realtime_session(self) -> dict:
        """Session format for gpt-realtime (general model)."""
        return {
            "type": "session.update",
            "session": {
                "type": "realtime",
                "modalities": ["audio", "text"],
                "instructions": self._build_instructions(),
                "voice": self.voice,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {"model": "gpt-realtime-whisper"},
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": self.vad_threshold,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": self.vad_silence_ms,
                },
            },
        }

    def _build_instructions(self) -> str:
        src = LANG_NAMES.get(self.source_lang, self.source_lang)
        tgt = LANG_NAMES.get(self.target_lang, self.target_lang)
        instructions = (
            f"You are a real-time simultaneous interpreter.\n"
            f"The user speaks {src}. Translate everything they say into natural, "
            f"conversational {tgt}.\n\n"
            f"Rules:\n"
            f"- Output ONLY the translation. No commentary or explanations.\n"
            f"- Match register and tone exactly.\n"
            f"- Translate as fast as possible — latency matters more than perfection.\n"
            f"- Preserve proper nouns (names, places) as-is."
        )
        if self.context:
            instructions += f"\n\nConversation context:\n{self.context}"
        return instructions

    # ------------------------------------------------------------------
    # Audio I/O
    # ------------------------------------------------------------------

    async def _send_audio(self, ws, input_stream: AudioStream) -> None:
        # translate endpoint prefixes all events with "session."
        event_type = (
            "session.input_audio_buffer.append"
            if self._is_translate_model
            else "input_audio_buffer.append"
        )
        loop = asyncio.get_event_loop()
        sent = 0
        while not self._stop_event.is_set():
            chunk = await loop.run_in_executor(None, input_stream.read)
            if not chunk:
                await asyncio.sleep(0.01)
                continue
            await ws.send(json.dumps({
                "type": event_type,
                "audio": base64.b64encode(chunk).decode(),
            }))
            sent += 1
            if self._debug and sent % 50 == 0:  # every ~5s of audio
                print(f"  [debug] sent {sent} audio chunks", flush=True)

    # Seconds of event silence after which accumulated transcripts are flushed.
    # The translate endpoint streams continuously and never emits "done" events,
    # so utterance boundaries are inferred from inactivity.
    TRANSCRIPT_FLUSH_S = 1.2

    async def _recv_audio(self, ws, output_stream: AudioStream) -> None:
        state = {
            "t_start": None,          # time of first audio delta of the utterance
            "source": "",
            "target": "",
            "last_delta_at": None,    # time of last delta received
        }

        def _flush():
            if self._debug:
                print(f"  [debug] flush: src={state['source']!r} tgt={state['target']!r} cb={self.on_translation is not None}", flush=True)
            if state["target"] and self.on_translation:
                t_start = state["t_start"]
                self.on_translation(TranslationEvent(
                    source_text=state["source"].strip(),
                    target_text=state["target"].strip(),
                    latency_ms=((time.time() - t_start) * 1000) if t_start else 0.0,
                ))
            state.update(t_start=None, source="", target="", last_delta_at=None)

        async def _watchdog():
            # The translate endpoint never sends "done" events, so utterance
            # boundaries are inferred from event-stream inactivity.
            while not self._stop_event.is_set():
                await asyncio.sleep(0.3)
                last = state["last_delta_at"]
                if last and time.time() - last > self.TRANSCRIPT_FLUSH_S:
                    _flush()

        watchdog = asyncio.create_task(_watchdog())
        try:
            await self._consume_events(ws, output_stream, state, _flush)
        finally:
            watchdog.cancel()

    async def _consume_events(self, ws, output_stream: AudioStream, state: dict, _flush) -> None:
        async for raw in ws:
            if self._stop_event.is_set():
                break

            event = json.loads(raw)
            t = event.get("type", "")

            if self._debug:
                if "audio.delta" in t:
                    self._dbg_audio = getattr(self, "_dbg_audio", 0) + 1
                    if self._dbg_audio % 10 == 1:
                        print(f"  [debug] audio delta #{self._dbg_audio} ({t})", flush=True)
                else:
                    print(f"  [debug] event: {t}", flush=True)

            # Speech start — new utterance boundary (gpt-realtime only)
            if t in ("input_audio_buffer.speech_started", "session.speech_started"):
                _flush()
                state["t_start"] = time.time()

            # Source transcript (what the user said)
            elif t in (
                "conversation.item.input_audio_transcription.completed",
                "session.input_transcript.done",
            ):
                state["source"] = event.get("transcript", "") or event.get("delta", "")
                state["last_delta_at"] = time.time()

            elif t == "session.input_transcript.delta":
                if state["t_start"] is None:
                    state["t_start"] = time.time()
                state["source"] += event.get("delta", "")
                state["last_delta_at"] = time.time()

            # Translated audio — stream to output.
            # NOTE: the translate endpoint streams audio continuously (silence
            # included), so audio deltas must NOT feed last_delta_at — only
            # transcript deltas mark real speech activity.
            elif t in (
                "response.audio.delta",
                "response.output_audio.delta",
                "session.output_audio.delta",
            ):
                output_stream.write(base64.b64decode(event["delta"]))

            # Translated text transcript (incremental)
            elif t in (
                "response.audio_transcript.delta",
                "response.output_audio_transcript.delta",
                "session.output_transcript.delta",
            ):
                state["target"] += event.get("delta", "")
                state["last_delta_at"] = time.time()

            # Response complete — fire callback (gpt-realtime; the translate
            # endpoint never sends these, see watchdog flush above)
            elif t in (
                "response.done",
                "session.output_audio.done",
                "session.output_transcript.done",
            ):
                _flush()

            elif t == "error":
                msg = event.get("error", {}).get("message", str(event))
                raise RuntimeError(f"Realtime API error: {msg}")
