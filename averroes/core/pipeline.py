"""Core translation pipeline using GPT-4o Realtime API over WebSocket."""

import asyncio
import base64
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import websockets

from .audio import AudioStream
from .constants import LANG_NAMES, REALTIME_URL


@dataclass
class TranslationEvent:
    source_text: str = ""
    target_text: str = ""
    latency_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def __str__(self) -> str:
        return (
            f"[{self.latency_ms:.0f}ms] "
            f"{self.source_text!r} → {self.target_text!r}"
        )


class Pipeline:
    """Real-time translation pipeline.

    Connects an AudioStream input to an AudioStream output,
    translating speech via GPT-4o Realtime (WebSocket).

    Usage::

        pipeline = Pipeline(source_lang="es", target_lang="ja", api_key="sk-...")
        pipeline.run(mic_stream, speaker_stream)   # blocks until stop() or Ctrl+C
    """

    def __init__(
        self,
        source_lang: str,
        target_lang: str,
        api_key: str,
        model: str = "gpt-4o-realtime-preview",
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, input_stream: AudioStream, output_stream: AudioStream) -> None:
        """Blocking. Translates from input_stream to output_stream."""
        asyncio.run(self._run_async(input_stream, output_stream))

    def stop(self) -> None:
        """Signal the pipeline to stop."""
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run_async(
        self, input_stream: AudioStream, output_stream: AudioStream
    ) -> None:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        url = f"{REALTIME_URL}?model={self.model}"

        async with websockets.connect(
            url,
            additional_headers=headers,
            ping_interval=20,
            ping_timeout=10,
        ) as ws:
            # Wait for the session to be ready
            await self._wait_for_session(ws)

            # Configure translation behaviour
            await ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "modalities": ["audio", "text"],
                    "instructions": self._build_instructions(),
                    "voice": self.voice,
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "input_audio_transcription": {"model": "whisper-1"},
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": self.vad_threshold,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": self.vad_silence_ms,
                    },
                },
            }))

            send_task = asyncio.create_task(self._send_audio(ws, input_stream))
            recv_task = asyncio.create_task(self._recv_audio(ws, output_stream))

            try:
                await asyncio.gather(send_task, recv_task)
            except (asyncio.CancelledError, KeyboardInterrupt):
                pass
            finally:
                send_task.cancel()
                recv_task.cancel()

    async def _wait_for_session(self, ws) -> None:
        async for raw in ws:
            event = json.loads(raw)
            if event.get("type") == "session.created":
                return
            if event.get("type") == "error":
                raise RuntimeError(f"Session error: {event}")

    async def _send_audio(self, ws, input_stream: AudioStream) -> None:
        loop = asyncio.get_event_loop()
        while not self._stop_event.is_set():
            chunk = await loop.run_in_executor(None, input_stream.read)
            if not chunk:
                await asyncio.sleep(0.01)
                continue
            await ws.send(json.dumps({
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(chunk).decode(),
            }))

    async def _recv_audio(self, ws, output_stream: AudioStream) -> None:
        t_start: Optional[float] = None
        source_transcript = ""
        target_transcript = ""

        async for raw in ws:
            if self._stop_event.is_set():
                break

            event = json.loads(raw)
            t = event.get("type", "")

            if t == "input_audio_buffer.speech_started":
                t_start = time.time()
                source_transcript = ""
                target_transcript = ""

            elif t == "conversation.item.input_audio_transcription.completed":
                source_transcript = event.get("transcript", "")

            elif t == "response.audio.delta":
                output_stream.write(base64.b64decode(event["delta"]))

            elif t == "response.audio_transcript.delta":
                target_transcript += event.get("delta", "")

            elif t == "response.done":
                if t_start is not None and self.on_translation:
                    self.on_translation(TranslationEvent(
                        source_text=source_transcript,
                        target_text=target_transcript,
                        latency_ms=(time.time() - t_start) * 1000,
                    ))

            elif t == "error":
                msg = event.get("error", {}).get("message", str(event))
                raise RuntimeError(f"Realtime API error: {msg}")

    def _build_instructions(self) -> str:
        src = LANG_NAMES.get(self.source_lang, self.source_lang)
        tgt = LANG_NAMES.get(self.target_lang, self.target_lang)

        instructions = (
            f"You are a real-time simultaneous interpreter.\n"
            f"The user speaks {src}. Translate everything they say into natural, "
            f"conversational {tgt}.\n\n"
            f"Rules:\n"
            f"- Output ONLY the translation. No meta-commentary, no explanations.\n"
            f"- Match the register and tone exactly (casual stays casual, polite stays polite).\n"
            f"- Translate as fast as possible — latency matters more than perfection.\n"
            f"- Preserve proper nouns (names, places) as-is.\n"
            f"- If input is unclear, translate what you can and continue."
        )

        if self.context:
            instructions += f"\n\nConversation context:\n{self.context}"

        return instructions
