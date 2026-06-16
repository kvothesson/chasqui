"""Headset adapter — bidirectional translation for any voice app.

Unlike bridge/meet, this adapter:
  - Captures system speaker output via Stereo Mix (no second virtual cable needed)
  - Automatically sets CABLE Output as Windows default mic on start, restores on exit
  - Works with Meet, Discord, ChatGPT, Zoom — anything that uses the system default mic

Setup (one-time):
  1. Install VB-Audio Cable (https://vb-audio.com/Cable/)
  2. Enable "Stereo Mix" in Windows Sound > Recording devices (right-click to show
     disabled devices, then Enable). If missing, your audio driver may not support it —
     install Hi-Fi Cable (vb-audio.com) as fallback.
  3. Run: chasqui listen --adapter headset
     chasqui will auto-set CABLE Output as your default mic and restore it on exit.
"""

import subprocess
import sys
from typing import Optional

from ..core.audio import MicStream, LoopbackStream, SpeakerStream
from .base import BaseAdapter, _safe_print
from .bridge import BridgeAdapter, _CABLE_INPUT_HINTS

# IN capture priority: Stereo Mix (built-in, no second cable) → Hi-Fi Cable → CABLE-B
_HEADSET_LOOPBACK_HINTS = [
    "Stereo Mix",
    "What U Hear",
    "Hi-Fi Cable Output",
    "CABLE-B Output",
]


def _get_default_mic() -> Optional[str]:
    if sys.platform != "win32":
        return None
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-AudioDevice -Recordingdefault | Select-Object -ExpandProperty Name"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def _set_default_mic(name_fragment: str) -> bool:
    if sys.platform != "win32":
        return False
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-AudioDevice -List | "
             f"Where-Object {{$_.Name -like '*{name_fragment}*' -and $_.Type -eq 'Recording'}} | "
             f"Select-Object -First 1 | Set-AudioDevice"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


class HeadsetAdapter(BridgeAdapter):
    """Bidirectional real-time translation — put on headphones and go."""

    header = "Headset mode (bidirectional, any app)"
    app_label = "any voice app"

    def run(self) -> None:
        self._print_header(self.header)

        cable_input = self._find_device(_CABLE_INPUT_HINTS, self.config.device.speaker, require_output=True)
        in_capture  = self._find_device(_HEADSET_LOOPBACK_HINTS, self.config.device.loopback, require_output=False)

        print(f"  OUT  real mic → {self.config.source_lang}→{self.config.target_lang} → {cable_input or 'default speaker'}")
        print(f"  IN   {in_capture or '(no loopback found)'} → {self.config.target_lang}→{self.config.source_lang} → {self.config.device.earphone or 'default speaker'}")

        if not cable_input:
            print("\n  [warn] CABLE Input not found — install VB-Audio Cable and rerun.")
        if not in_capture:
            print("\n  [warn] No loopback capture device found.")
            print("         Enable 'Stereo Mix' in Windows Sound > Recording devices,")
            print("         or install Hi-Fi Cable (vb-audio.com).")
            print("         IN translation is DISABLED for this session.")
        print()
        print("  Put on headphones. In your app (Meet, Discord, ChatGPT...):")
        print("    microphone → 'CABLE Output'  (set once as Windows default mic)")
        print("  (Ctrl+C to stop)\n")

        # Auto-switch Windows default mic to CABLE Output, restore on exit
        original_mic = _get_default_mic()
        switched = False
        if cable_input and original_mic and "cable" not in original_mic.lower():
            if _set_default_mic("CABLE Output"):
                switched = True
                print(f"  [auto] Windows default mic → CABLE Output  (was: {original_mic})\n")

        try:
            out_tuple = (
                self._make_pipeline(),
                MicStream(device=self.config.device.mic),
                SpeakerStream(device=cable_input),
            )
            in_tuple = None
            if in_capture:
                in_tuple = (
                    self._make_pipeline_reverse(),
                    LoopbackStream(device=in_capture),
                    SpeakerStream(device=self.config.device.earphone),
                )
            self._run_parallel(out_tuple, in_tuple)
        finally:
            if switched and original_mic:
                if _set_default_mic(original_mic):
                    print(f"\n  [auto] Restored Windows default mic → {original_mic}")

        self._save_session_if_needed()
