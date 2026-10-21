"""Gate check: does the silence gate save money without losing translations?

Plays one side of a call: short phrases separated by long silences (the
other side talking). Runs it twice in real time, gate off and gate on, and
prints what came back and how many minutes each run streamed. What to look
for: the same number of translated turns, complete sentences in both, and
fewer minutes with the gate.

Costs real money (TTS + about two minutes of realtime audio, ~$0.07).

    python examples/gate_check.py
    python examples/gate_check.py --hold 800        # try a shorter tail
"""

import argparse
import threading
import time

from chasqui.core.audio import BytesStream, NullStream
from chasqui.core.config import load_config
from chasqui.core.constants import CHUNK_SIZE
from chasqui.core.pipeline import Pipeline
from chasqui.core.pricing import minutes_from_bytes

PHRASES_ES = [
    "Buen día, ¿me escuchan bien?",
    "Ayer terminé la migración de la base de datos y hoy sigo con los tests.",
    "No tengo bloqueos, pero necesito que alguien revise mi pull request.",
    "Perfecto, gracias. Nos vemos mañana.",
]

GAP_S = 8.0    # the other side talking: what a call direction mostly is
TAIL_S = 8.0


class PacedStream(BytesStream):
    """Hands out audio at real-time speed, like a mic would."""

    def read(self, chunk_size: int = CHUNK_SIZE) -> bytes:
        time.sleep(chunk_size / 48000)
        return super().read(chunk_size)


def synthesize(client) -> bytes:
    silence = b"\x00\x00" * int(24000 * GAP_S)
    audio = bytearray()
    for phrase in PHRASES_ES:
        audio += client.audio.speech.create(
            model="tts-1", voice="alloy", input=phrase, response_format="pcm",
        ).content + silence
    return bytes(audio)


def run_once(cfg, audio: bytes, gate: bool, hold_ms: int):
    turns = []
    pipeline = Pipeline(
        source_lang="es", target_lang=cfg.target_lang, api_key=cfg.api_key,
        model=cfg.model, on_translation=turns.append,
        silence_gate=gate, gate_hold_ms=hold_ms,
    )
    failure = {}

    def _run():
        try:
            pipeline.run(PacedStream(audio + b"\x00\x00" * int(24000 * TAIL_S)), NullStream())
        except Exception as e:
            failure["error"] = e

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=len(audio) / 48000 + TAIL_S + 15)
    pipeline.stop()
    thread.join(timeout=5)
    if failure:
        raise SystemExit(f"Pipeline failed: {failure['error']}")
    return turns, minutes_from_bytes(pipeline.usage.audio_bytes_sent)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--to", dest="target_lang", default="en")
    parser.add_argument("--hold", type=int, default=1500, help="gate hold in ms")
    args = parser.parse_args()

    from openai import OpenAI

    cfg = load_config()
    cfg.validate()
    cfg.target_lang = args.target_lang
    client = OpenAI(api_key=cfg.api_key)

    print(f"Synthesizing {len(PHRASES_ES)} phrases...")
    audio = synthesize(client)
    print(f"{len(audio) / 48000:.0f}s of audio per run, {cfg.model}\n")

    results = {}
    for gate in (False, True):
        label = f"gate on ({args.hold}ms hold)" if gate else "gate off"
        print(f"--- {label}")
        turns, minutes = run_once(cfg, audio, gate, args.hold)
        for t in turns:
            print(f"  {t.source_text!r}\n    -> {t.target_text!r}")
        print(f"  {len(turns)} turns, {minutes:.2f} min streamed\n")
        results[gate] = (len(turns), minutes)

    (n_off, m_off), (n_on, m_on) = results[False], results[True]
    saved = 1 - m_on / m_off if m_off else 0
    print(f"turns: {n_off} without gate, {n_on} with gate")
    print(f"streamed: {m_off:.2f} -> {m_on:.2f} min ({saved:.0%} less)")


if __name__ == "__main__":
    main()
