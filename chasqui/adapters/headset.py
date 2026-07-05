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

from ..core.audio import MicStream, LoopbackStream, SpeakerStream, resolve_device
from ..core.windevice import get_default_input_name, set_default_input
from .bridge import BridgeAdapter, _CABLE_INPUT_HINTS

# IN capture priority: Stereo Mix (built-in, no second cable) → Hi-Fi Cable → CABLE-B
_HEADSET_LOOPBACK_HINTS = [
    "Stereo Mix",
    "What U Hear",
    "Hi-Fi Cable Output",
    "CABLE-B Output",
]


class HeadsetAdapter(BridgeAdapter):
    """Bidirectional real-time translation — put on headphones and go."""

    header = "Headset mode (bidirectional, any app)"
    app_label = "any voice app"

    def run(self) -> None:
        self._print_header(self.header)

        cable_input = self._find_device(_CABLE_INPUT_HINTS, self.config.device.speaker, require_output=True)
        in_capture  = self._find_device(_HEADSET_LOOPBACK_HINTS, self.config.device.loopback, require_output=False)

        # Resolve the REAL mic explicitly BEFORE switching the Windows default
        # to CABLE Output. MicStream(device=None) follows the default input,
        # which after the switch is CABLE Output — chasqui's own translated
        # voice. Combo headsets got away with it because PortAudio snapshots
        # devices at import; separate mic/headphone setups need this pinned.
        original_mic = get_default_input_name()
        # resolve_device also for the explicit --mic: full Windows names match
        # several host-API entries (MME/DirectSound/WASAPI/WDM-KS) and raw
        # sounddevice lookup dies with "Multiple input devices found".
        mic_device = resolve_device(self.config.device.mic, want_input=True)
        if mic_device is None and original_mic and "cable" not in original_mic.lower():
            mic_device = resolve_device(original_mic, want_input=True)
        mic_label = self.config.device.mic or original_mic or "default mic"
        earphone = resolve_device(self.config.device.earphone, want_input=False)

        print(f"  OUT  {mic_label} → {self.config.source_lang}→{self.config.target_lang} → {cable_input or 'default speaker'}")
        print(f"  IN   {in_capture or '(no loopback found)'} → {self.config.target_lang}→{self.config.source_lang} → {self.config.device.earphone or 'default speaker'}")

        if not cable_input:
            print("\n  [warn] CABLE Input not found — install VB-Audio Cable and rerun.")
        if mic_device is None and original_mic and "cable" in original_mic.lower():
            print("\n  [warn] Windows default mic is a virtual cable — chasqui would")
            print("         capture its own translated voice (feedback loop).")
            print("         Pass your real mic:  chasqui listen --adapter headset --mic \"...\"")
            print("         (see 'chasqui devices' for names)")
        if not in_capture:
            print("\n  [warn] No loopback capture device found.")
            print("         Enable 'Stereo Mix' in Windows Sound > Recording devices,")
            print("         or install Hi-Fi Cable (vb-audio.com).")
            print("         IN translation is DISABLED for this session.")
        print()
        print("  Put on headphones — with open speakers the mic re-captures the")
        print("  translation and it loops. Separate mic + headphones? Pick them:")
        print("    chasqui listen --adapter headset --mic \"...\" --earphone \"...\"")
        print()
        print("  In your app (Meet, Discord, ChatGPT...):")
        print("    microphone → 'CABLE Output'  (set once as Windows default mic)")
        print("  (Ctrl+C to stop)\n")

        # Auto-switch Windows default mic to CABLE Output, restore on exit
        switched = False
        if cable_input and original_mic and "cable" not in original_mic.lower():
            if set_default_input("CABLE Output"):
                switched = True
                print(f"  [auto] Windows default mic → CABLE Output  (was: {original_mic})\n")

        try:
            out_tuple = (
                self._make_pipeline(),
                MicStream(device=mic_device),
                SpeakerStream(device=cable_input),
            )
            in_tuple = None
            if in_capture:
                in_tuple = (
                    self._make_pipeline_reverse(),
                    LoopbackStream(device=resolve_device(in_capture, want_input=True)),
                    SpeakerStream(device=earphone),
                )
            self._run_parallel(out_tuple, in_tuple)
        finally:
            if switched and original_mic:
                if set_default_input(original_mic):
                    print(f"\n  [auto] Restored Windows default mic → {original_mic}")
                else:
                    print(f"\n  [warn] Could not restore default mic (was: {original_mic}).")
                    print("         Restore it manually in Windows Sound > Recording devices.")

        self._save_session_if_needed()
