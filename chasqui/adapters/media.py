"""Media adapter — translate system audio (YouTube, videos, streams).

Flow: system audio loopback → pipeline → earphone (user hears in their language).

Requires loopback capture:
  Windows: enable 'Stereo Mix' in Sound > Recording > Show disabled devices
  macOS:   install BlackHole and set as output + capture from it
"""

from ..core.audio import LoopbackStream, SpeakerStream, NullStream
from ..core.windevice import get_default_output_name, set_default_output
from .base import BaseAdapter

_CABLE_INPUT_HINT = "CABLE Input (VB-Audio Virtual Cable)"


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
        print(f"  Mode: {mode}\n")

        # Auto-switch Windows output to CABLE Input so system audio is capturable.
        prev_output = get_default_output_name()
        switched = False
        if prev_output and _CABLE_INPUT_HINT.lower() not in prev_output.lower():
            switched = set_default_output(_CABLE_INPUT_HINT)
            if switched:
                print(f"  Audio output → CABLE Input  (was: {prev_output})")
            else:
                print(f"  Warning: could not auto-switch audio output to CABLE Input.")
                print(f"  Switch manually: Settings → Sound → Output → CABLE Input\n")

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
            if switched and prev_output:
                set_default_output(prev_output)
                print(f"  Audio output restored → {prev_output}")

        self._save_session_if_needed()
