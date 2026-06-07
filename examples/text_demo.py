"""Quick demo: translate a few phrases without any hardware.

Run:
    export OPENAI_API_KEY=sk-...
    python examples/text_demo.py
"""

import os
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from averroes.core.config import Config
from averroes.adapters.text import TextAdapter

PHRASES = [
    "Hola, ¿dónde está el baño?",
    "¿Cuánto cuesta esto?",
    "Una mesa para dos personas, por favor.",
    "¿Tienen menú en inglés?",
    "La cuenta, por favor.",
    "Muchas gracias, fue delicioso.",
    "¿Cómo llego a la estación de tren?",
]

def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Set OPENAI_API_KEY first.")
        sys.exit(1)

    cfg = Config(
        api_key=api_key,
        source_lang="es",
        target_lang="ja",
        context="Tourist in Japan. Everyday conversations.",
    )

    adapter = TextAdapter(cfg)

    print("Averroes — Text Demo")
    print("ES → JA translations\n")

    for phrase in PHRASES:
        translation = adapter.translate_once(phrase)
        print(f"  ES: {phrase}")
        print(f"  JA: {translation}")
        print()


if __name__ == "__main__":
    main()
