"""Text adapter — keyboard in, terminal out.

Uses standard Chat Completions (not Realtime) for simplicity.
Best for: testing, silent mode, piping (echo "hola" | chasqui translate).
"""

import sys

from openai import OpenAI

from ..core.config import Config
from ..core.constants import LANG_NAMES
from .base import BaseAdapter


class TextAdapter(BaseAdapter):
    """Interactive text translation or single-shot via pipe."""

    def __init__(self, config: Config):
        super().__init__(config)
        self._client = OpenAI(api_key=config.api_key)

    def run(self) -> None:
        self._print_header("Text mode")
        src = self.config.source_lang.upper()
        tgt = self.config.target_lang.upper()
        print("Type a message and press Enter. Ctrl+C or Ctrl+D to exit.\n")

        while True:
            try:
                text = input(f"[{src}] > ").strip()
            except (KeyboardInterrupt, EOFError):
                print()
                break

            if not text:
                continue

            translation = self._translate(text)
            print(f"[{tgt}] {translation}\n")
            self._session.add_turn(source_text=text, target_text=translation)

        self._save_session_if_needed()

    def translate_once(self, text: str) -> str:
        """Single translation — for piping or programmatic use."""
        return self._translate(text)

    def _translate(self, text: str) -> str:
        src_name = LANG_NAMES.get(self.config.source_lang, self.config.source_lang)
        tgt_name = LANG_NAMES.get(self.config.target_lang, self.config.target_lang)

        system = (
            f"You are a translator. Translate from {src_name} to {tgt_name}. "
            f"Output ONLY the translation — no explanations, no alternatives."
        )
        if self.config.context:
            system += f"\nContext: {self.config.context}"

        resp = self._client.chat.completions.create(
            model=self.config.text_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
            temperature=0.1,
        )
        return resp.choices[0].message.content.strip()
