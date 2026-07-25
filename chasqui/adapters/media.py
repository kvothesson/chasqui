"""Media adapter — translate system audio (YouTube, videos, streams).

Flow: system audio loopback → pipeline → earphone (user hears in their language).

Requires loopback capture:
  Windows: enable 'Stereo Mix' in Sound > Recording > Show disabled devices
  macOS:   install BlackHole and set as output + capture from it
"""

from ..core.audio import (
    LoopbackStream, SpeakerStream, NullStream, find_device_by_hints,
    refresh_devices, resolve_device,
)
from ..core.windevice import get_default_output_name, set_default_output
from .base import BaseAdapter

_CABLE_INPUT_HINT = "CABLE Input (VB-Audio Virtual Cable)"

# Where the system audio comes back in. "CABLE Output" is the recording side of
# the cable we just routed the system output to, so it is the natural first
# choice; Stereo Mix works when the output switch didn't happen.
_MEDIA_CAPTURE_HINTS = [
    "CABLE Output (VB-Audio Virtual",
    "Stereo Mix",
    "What U Hear",
]


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

        # Find the capture device BEFORE switching defaults — names survive the
        # switch, indices don't (see refresh_devices).
        capture = find_device_by_hints(_MEDIA_CAPTURE_HINTS, self.config.device.loopback)

        # Auto-switch Windows output to CABLE Input so system audio is capturable.
        prev_output = get_default_output_name()
        switched = False
        if prev_output and _CABLE_INPUT_HINT.lower() not in prev_output.lower():
            switched = set_default_output(_CABLE_INPUT_HINT)
            if switched:
                print(f"  Audio output → CABLE Input  (was: {prev_output})")
            else:
                print("  Warning: could not auto-switch audio output to CABLE Input.")
                print("  Switch manually: Settings → Sound → Output → CABLE Input\n")

        # Refresh AFTER the switch: Windows renumbers device IDs when the
        # default changes, and indices/names must resolve against the new order.
        refresh_devices()

        loopback = LoopbackStream(device=resolve_device(self.config.device.loopback, want_input=True))

        # Earphone: an explicit choice wins. With none set, fall back to the
        # user's ORIGINAL output — NOT the default, which is the capture cable
        # now. Playing the translation to the default would feed it straight
        # back into the loopback we are reading (translation of the
        # translation), and the user would hear nothing at all. Same rule the
        # headset adapter follows after its own default-device switch.
        earphone_label = self.config.device.earphone
        if earphone_label is None and switched:
            earphone_label = prev_output

        if mode == "subtitle":
            out = NullStream()
        else:
            out = SpeakerStream(device=resolve_device(earphone_label, want_input=False))

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
