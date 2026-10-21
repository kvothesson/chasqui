"""Drift check: does the model translate, or does it answer?

Short questions aimed at "you" ("¿Llegaste bien?", "¿Me das un mate?") are
where realtime models drift — they reply instead of interpreting. This
synthesizes a fixed set of trap phrases with TTS, plays them through ONE
pipeline session in real time (drift builds up with conversation history, so
one session per phrase would hide it), and asks a text model to label each
turn TRANSLATION / REPLY / OTHER.

Costs real money (TTS + about a minute of realtime audio + a few judge calls).

    python examples/drift_check.py                         # model from chasqui.yaml
    python examples/drift_check.py --model gpt-realtime
    python examples/drift_check.py --model gpt-realtime --isolate
"""

import argparse
import threading
import time

from chasqui.core.audio import BytesStream, NullStream
from chasqui.core.config import load_config
from chasqui.core.constants import CHUNK_SIZE, LANG_NAMES
from chasqui.core.pipeline import Pipeline

TRAPS_ES = [
    "¿Llegaste bien?",
    "¿Cómo estás?",
    "¿Me das un mate?",
    "¿Me trae la cuenta, por favor?",
    "¿Qué hora es?",
    "¿Me ayudás con esto?",
    "Contame un chiste.",
    "¿Sabés dónde queda la estación?",
    "Gracias, muy amable.",
    # Control: long and contextual, the kind that already translates fine.
    "Mañana vamos a visitar el templo con mi esposa y después queremos comer ramen.",
]

GAP_S = 3.0    # silence after each phrase: long enough for VAD to close the turn
TAIL_S = 10.0  # after the last phrase, wait for late transcripts


class PacedStream(BytesStream):
    """BytesStream that hands out audio at real-time speed, not all at once.

    Sent in one burst, every phrase would reach the server before the first
    reply, and server VAD would interrupt responses mid-sentence.
    """

    def read(self, chunk_size: int = CHUNK_SIZE) -> bytes:
        time.sleep(chunk_size / 48000)  # PCM16 mono 24 kHz = 48 bytes/ms
        return super().read(chunk_size)


def synthesize(client, phrases: list[str]) -> bytes:
    silence = b"\x00\x00" * int(24000 * GAP_S)
    audio = bytearray()
    for phrase in phrases:
        pcm = client.audio.speech.create(
            model="tts-1", voice="alloy", input=phrase, response_format="pcm",
        ).content
        audio += pcm + silence
    return bytes(audio)


def judge(client, model: str, src_lang: str, tgt_lang: str, source: str, target: str) -> str:
    src = LANG_NAMES.get(src_lang, src_lang)
    tgt = LANG_NAMES.get(tgt_lang, tgt_lang)
    prompt = (
        f"An interpreter heard this {src}: «{source}»\n"
        f"and said this in {tgt}: «{target}»\n\n"
        "Is the output a faithful translation of the input (TRANSLATION), "
        "a reply or reaction to it instead of a translation (REPLY), "
        "or something else (OTHER)? A short or casual rendering still counts "
        "as TRANSLATION if it means the same, e.g. «¿Cómo estás?» → «元気？». "
        "REPLY means it answers or reacts, e.g. «¿Llegaste bien?» → «うん、大丈夫だよ». "
        "Answer with one word."
    )
    answer = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}], temperature=0,
    ).choices[0].message.content.strip().upper()
    for label in ("TRANSLATION", "REPLY", "OTHER"):
        if label in answer:
            return label
    return "OTHER"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--model", help="realtime model (default: chasqui.yaml)")
    parser.add_argument("--isolate", action="store_true",
                        help="translate each turn outside the conversation (gpt-realtime only)")
    parser.add_argument("--to", dest="target_lang", default="ja")
    args = parser.parse_args()

    from openai import OpenAI

    cfg = load_config()
    cfg.validate()
    model = args.model or cfg.model
    client = OpenAI(api_key=cfg.api_key)

    print(f"Synthesizing {len(TRAPS_ES)} phrases...")
    audio = synthesize(client, TRAPS_ES)
    print(f"Playing {len(audio) / 48000:.0f}s of audio through {model}"
          f"{' (isolated turns)' if args.isolate else ''}...")

    turns = []
    pipeline = Pipeline(
        source_lang="es", target_lang=args.target_lang, api_key=cfg.api_key,
        model=model, context=cfg.context, voice=cfg.voice,
        on_translation=turns.append, isolate_turns=args.isolate,
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

    counts = {"TRANSLATION": 0, "REPLY": 0, "OTHER": 0}
    print()
    for turn in turns:
        if not (turn.source_text and turn.target_text):
            label = "OTHER"
        else:
            label = judge(client, cfg.text_model, "es", args.target_lang,
                          turn.source_text, turn.target_text)
        counts[label] += 1
        print(f"  {label:<11} {turn.latency_ms:>6.0f}ms  {turn.source_text!r}")
        print(f"  {'':<11} {'':>8}  {turn.target_text!r}")

    print(f"\n{len(TRAPS_ES)} phrases sent, {len(turns)} turns back: "
          + ", ".join(f"{n} {k.lower()}" for k, n in counts.items()))


if __name__ == "__main__":
    main()
