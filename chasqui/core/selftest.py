"""Pipeline smoke test — no microphone, no speakers, no audio hardware.

Synthesizes a short phrase with TTS, pushes it through the realtime pipeline
and reports what came back. Shared by `chasqui check` and the UI's Check
button, so both answer the same question the same way: is the API key valid,
is the model reachable, and does a round trip actually translate?
"""

import threading
from dataclasses import dataclass
from typing import Callable, Optional

from .audio import BytesStream, NullStream
from .config import Config
from .pipeline import Pipeline

# One greeting per supported source language — short, so the round trip is quick.
TEST_PHRASES: dict[str, str] = {
    "es": "hola, ¿cómo estás?",
    "en": "hello, how are you?",
    "ja": "こんにちは、お元気ですか？",
    "fr": "bonjour, comment allez-vous?",
    "pt": "olá, como você está?",
    "zh": "你好，你好吗？",
    "de": "hallo, wie geht es dir?",
    "it": "ciao, come stai?",
    "ko": "안녕하세요, 잘 지내세요?",
}

DEFAULT_TIMEOUT_S = 30.0


@dataclass
class CheckResult:
    """Outcome of a smoke test. `ok` is the only thing callers must look at."""
    ok: bool
    phrase: str = ""
    source_text: str = ""
    target_text: str = ""
    latency_ms: float = 0.0
    audio_ms: int = 0
    error: str = ""


def test_phrase_for(lang: str, lang_name: str = "") -> str:
    return TEST_PHRASES.get(lang, f"hello in {lang_name or lang}")


def run_check(
    config: Config,
    phrase: str = "",
    on_progress: Optional[Callable[[str], None]] = None,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> CheckResult:
    """Run the smoke test. Blocking; never raises — failures come back in the result."""
    def _progress(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    phrase = phrase or test_phrase_for(config.source_lang)

    _progress("Synthesizing test audio...")
    try:
        from openai import OpenAI
        client = OpenAI(api_key=config.api_key)
        response = client.audio.speech.create(
            model="tts-1",
            voice="alloy",
            input=phrase,
            response_format="pcm",
        )
        pcm_data = response.content
    except Exception as e:
        return CheckResult(ok=False, phrase=phrase, error=f"TTS failed: {e}")

    # PCM16 mono 24kHz → 48 bytes per millisecond.
    audio_ms = len(pcm_data) // 48
    _progress(f"Test audio ready ({audio_ms} ms)")

    _progress("Running pipeline...")
    result: dict = {}
    got_translation = threading.Event()
    failure: dict = {}

    def _on_translation(event):
        if event.target_text and not got_translation.is_set():
            result["event"] = event
            got_translation.set()

    pipeline = Pipeline(
        source_lang=config.source_lang,
        target_lang=config.target_lang,
        api_key=config.api_key,
        model=config.model,
        on_translation=_on_translation,
        isolate_turns=config.isolate_turns,
    )

    def _run():
        try:
            pipeline.run(BytesStream(pcm_data), NullStream())
        except Exception as e:
            # Auth errors and bad model names surface here, not in the wait
            # below — without this the caller would just see "timeout".
            failure["error"] = str(e)
            got_translation.set()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    finished = got_translation.wait(timeout=timeout)
    pipeline.stop()
    thread.join(timeout=5)

    if failure:
        return CheckResult(ok=False, phrase=phrase, audio_ms=audio_ms, error=failure["error"])

    if not finished or "event" not in result:
        return CheckResult(
            ok=False, phrase=phrase, audio_ms=audio_ms,
            error=f"no translation received within {timeout:.0f}s",
        )

    event = result["event"]
    return CheckResult(
        ok=True,
        phrase=phrase,
        source_text=event.source_text,
        target_text=event.target_text,
        latency_ms=event.latency_ms,
        audio_ms=audio_ms,
    )
