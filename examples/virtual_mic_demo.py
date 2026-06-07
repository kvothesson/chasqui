"""Virtual mic demo — for use with Google Meet or Zoom.

Prerequisites:
  Windows: install VB-Audio Cable https://vb-audio.com/Cable/
  macOS:   install BlackHole     https://github.com/ExistentialAudio/BlackHole

Then in Google Meet: select 'CABLE Input' (or BlackHole) as your microphone.

Run:
    export OPENAI_API_KEY=sk-...
    python examples/virtual_mic_demo.py
"""

import os
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from averroes.core.config import Config
from averroes.adapters.virtual_mic import VirtualMicAdapter


def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Set OPENAI_API_KEY first.")
        sys.exit(1)

    cfg = Config(
        api_key=api_key,
        source_lang="es",
        target_lang="ja",
        context=(
            "The user is an Argentine tourist in Japan. "
            "They are speaking casually in a meeting or video call. "
            "Translate naturally, preserve politeness level."
        ),
        voice="nova",
    )

    VirtualMicAdapter(cfg).run()


if __name__ == "__main__":
    main()
