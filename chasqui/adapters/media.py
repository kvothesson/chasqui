"""Media adapter — translate system audio (YouTube, videos, streams).

Flow: system audio loopback → pipeline → earphone (user hears in their language).

Requires loopback capture:
  Windows: enable 'Stereo Mix' in Sound > Recording > Show disabled devices
  macOS:   install BlackHole and set as output + capture from it
"""

from ..core.audio import LoopbackStream, SpeakerStream, NullStream
from .base import BaseAdapter


class MediaAdapter(BaseAdapter):
    """Dub or subtitle any audio playing on your system in real time."""

    def run(self, mode: str = "dub") -> None:
        """
        mode:
          'dub'      — translate audio to earphone (replaces original)
          'subtitle' — show translated text only, no audio output
          'both'     — text + audio
        """
        self._print_header("Media mode")
        print(f"  Mode: {mode}")
        print("  Play a video — translation goes to your earphone.\n")

        loopback = LoopbackStream(device=self.config.device.loopback)

        if mode == "subtitle":
            out = NullStream()
        else:
            out = SpeakerStream(device=self.config.device.earphone)

        loopback.start()
        if hasattr(out, "start"):
            out.start()

        pipeline = self._make_pipeline()

        try:
            print("Listening to system audio... (Ctrl+C to stop)\n")
            pipeline.run(loopback, out)
        except KeyboardInterrupt:
            print("\nStopping...")
        finally:
            pipeline.stop()
            loopback.close()
            out.close()

        self._save_session_if_needed()
