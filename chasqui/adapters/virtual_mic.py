"""Virtual mic adapter — Google Meet, Zoom, Teams.

Flow:
  real mic → pipeline → virtual mic device (Meet hears Japanese)
                     → earphone (user hears Japanese responses in Spanish)

Requires a virtual audio cable:
  Windows: VB-Audio Virtual Cable  https://vb-audio.com/Cable/
  macOS:   BlackHole               https://github.com/ExistentialAudio/BlackHole
"""

import sys
from typing import Optional

from ..core.audio import MicStream, SpeakerStream, MultiOutputStream
from .base import BaseAdapter

# Substrings to detect virtual audio devices by platform
_VIRTUAL_HINTS: dict[str, list[str]] = {
    "win32":  ["CABLE Input"],
    "darwin": ["BlackHole", "Loopback", "Soundflower"],
    "linux":  ["pulse", "monitor"],
}


class VirtualMicAdapter(BaseAdapter):
    """Translate your mic into a virtual mic that any app can use as input."""

    def run(self) -> None:
        self._print_header("Virtual Mic mode")

        virtual_device = self._find_virtual_device()
        if virtual_device:
            print(f"  Virtual mic : {virtual_device}")
        else:
            print("  Virtual mic : not found — output goes to default speaker")
            print("  Install VB-Audio Cable (Windows) or BlackHole (macOS)")
        print()

        real_mic, virtual_out = self._with_passthrough(
            MicStream(device=self.config.device.mic), SpeakerStream(device=virtual_device))
        earphone_out = SpeakerStream(device=self.config.device.earphone)
        out = MultiOutputStream(virtual_out, earphone_out)

        real_mic.start()
        virtual_out.start()
        earphone_out.start()

        pipeline = self._make_pipeline()

        try:
            print("Listening... In Google Meet, select the virtual mic as your input.")
            print("(Ctrl+C to stop)\n")
            pipeline.run(real_mic, out)
        except KeyboardInterrupt:
            print("\nStopping...")
        finally:
            pipeline.stop()
            real_mic.close()
            out.close()

        self._save_session_if_needed()

    def _find_virtual_device(self) -> Optional[str]:
        """Auto-detect virtual audio device, or fall back to config."""
        if self.config.device.speaker:
            return self.config.device.speaker

        try:
            import sounddevice as sd
            hints = _VIRTUAL_HINTS.get(sys.platform, [])
            for device in sd.query_devices():
                name: str = device["name"]
                if any(hint.lower() in name.lower() for hint in hints):
                    if device["max_output_channels"] > 0:
                        return name
        except Exception:
            pass

        return None
