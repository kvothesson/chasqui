"""Headset adapter — bidirectional translation for any voice app.

Unlike bridge/meet, this adapter is zero-config on Windows:
  - Auto-sets CABLE Output as Windows default mic on start (the app's mic
    picks up your translated voice), restores on exit
  - Auto-routes system audio for the IN direction: with Stereo Mix it
    captures the default output directly; with the Hi-Fi Cable fallback it
    switches the Windows default OUTPUT to Hi-Fi Cable Input (the app's
    voice lands on the cable) and plays the translation to your original
    headphones, restoring everything on exit
  - Works with Meet, Discord, ChatGPT, Zoom — anything using default devices

Setup (one-time):
  1. Install VB-Audio Cable (https://vb-audio.com/Cable/)
  2. Enable "Stereo Mix" in Windows Sound > Recording devices, or install
     Hi-Fi Cable (vb-audio.com) as fallback.
  3. Run: chasqui listen --adapter headset
"""

from ..core.audio import MicStream, LoopbackStream, SpeakerStream, refresh_devices, resolve_device
from ..core.windevice import (
    get_default_input_name, set_default_input,
    get_default_output_name, set_default_output,
)
from .bridge import BridgeAdapter, _CABLE_INPUT_HINTS

# IN capture priority: Stereo Mix (built-in, no second cable) → Hi-Fi Cable → CABLE-B
_HEADSET_LOOPBACK_HINTS = [
    "Stereo Mix",
    "What U Hear",
    "Hi-Fi Cable Output",
    "CABLE-B Output",
]

# Recording side of the IN cable → the playback side the app must feed.
# Short hints on purpose: they go into windevice's PowerShell -like match.
_IN_CABLE_PLAYBACK = {
    "Hi-Fi Cable Output": "Hi-Fi Cable Input",
    "CABLE-B Output": "CABLE-B Input",
}


class HeadsetAdapter(BridgeAdapter):
    """Bidirectional real-time translation — put on headphones and go."""

    header = "Headset mode (bidirectional, any app)"
    app_label = "any voice app"

    def run(self) -> None:
        self._print_header(self.header)

        # _find_device returns NAMES, which survive the default-device
        # switches below; name→index resolution waits until after them.
        cable_input = self._find_device(_CABLE_INPUT_HINTS, self.config.device.speaker, require_output=True)
        in_capture  = self._find_device(_HEADSET_LOOPBACK_HINTS, self.config.device.loopback, require_output=False)

        original_mic = get_default_input_name()
        original_output = get_default_output_name()
        mic_label = self.config.device.mic or original_mic or "default mic"

        stereo_mix = bool(in_capture) and any(
            h.lower() in in_capture.lower() for h in ("stereo mix", "what u hear"))
        in_playback_hint = None
        if in_capture and not stereo_mix:
            for cap_hint, play_hint in _IN_CABLE_PLAYBACK.items():
                if cap_hint.lower() in in_capture.lower():
                    in_playback_hint = play_hint
                    break

        # Switch the Windows defaults FIRST, then refresh PortAudio and
        # resolve indices. Windows renumbers live waveIn/waveOut IDs on a
        # default switch (the new default jumps to the first slot), so an
        # index resolved before it opens the wrong device after — the
        # real-mic index ended up pointing at CABLE Output and chasqui
        # listened to its own translated voice.
        switched_mic = False
        if cable_input and original_mic and "cable" not in original_mic.lower():
            if set_default_input("CABLE Output"):
                switched_mic = True

        # IN via a second cable: route ALL system audio (the app's voice) to
        # the cable's playback side, and play the translation to the user's
        # ORIGINAL output. With Stereo Mix nothing to switch — it captures
        # the default output as-is.
        switched_output = False
        if in_playback_hint and original_output and "cable" not in original_output.lower():
            if set_default_output(in_playback_hint):
                switched_output = True

        refresh_devices()

        # resolve_device also matters for the explicit --mic: full Windows
        # names match several host-API entries (MME/DirectSound/WASAPI/WDM-KS)
        # and raw sounddevice lookup dies with "Multiple input devices found".
        mic_device = resolve_device(self.config.device.mic, want_input=True)
        if mic_device is None and original_mic and "cable" not in original_mic.lower():
            mic_device = resolve_device(original_mic, want_input=True)

        # Earphone: explicit config wins; when we hijacked the default output,
        # fall back to the user's original output (NOT the default — that is
        # the cable now, and playing there loops the translation back in).
        earphone_label = self.config.device.earphone
        if earphone_label is None and switched_output:
            earphone_label = original_output
        earphone = resolve_device(earphone_label, want_input=False)

        print(f"  OUT  {mic_label} → {self.config.source_lang}→{self.config.target_lang} → {cable_input or 'default speaker'}")
        print(f"  IN   {in_capture or '(no loopback found)'} → {self.config.target_lang}→{self.config.source_lang} → {earphone_label or 'default speaker'}")

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
        if in_playback_hint and not switched_output:
            print(f"\n  [warn] Could not auto-route system audio to '{in_playback_hint}'.")
            print(f"         Set your app's speaker to '{in_playback_hint}' manually,")
            print("         or the IN direction will stay silent.")
        print()
        print("  Put on headphones — with open speakers the mic re-captures the")
        print("  translation and it loops. Separate mic + headphones? Pick them:")
        print("    chasqui listen --adapter headset --mic \"...\" --earphone \"...\"")
        print()
        print(f"  In {self.app_label} (Meet, Discord, ChatGPT...): leave mic and speaker")
        print("  on the system default — chasqui routes both automatically.")
        print("  (Ctrl+C to stop)\n")

        if switched_mic:
            print(f"  [auto] Windows default mic → CABLE Output  (was: {original_mic})")
        if switched_output:
            print(f"  [auto] Windows default output → {in_playback_hint}  (was: {original_output})")
        if switched_mic or switched_output:
            print("         Open/restart your app's voice session AFTER this point —")
            print("         apps grab their devices when the session starts.\n")

        try:
            out_tuple = (
                self._make_pipeline(),
                *self._with_passthrough(
                    MicStream(device=mic_device), SpeakerStream(device=cable_input)),
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
            if switched_mic and original_mic:
                if set_default_input(original_mic):
                    print(f"\n  [auto] Restored Windows default mic → {original_mic}")
                else:
                    print(f"\n  [warn] Could not restore default mic (was: {original_mic}).")
                    print("         Restore it manually in Windows Sound > Recording devices.")
            if switched_output and original_output:
                if set_default_output(original_output):
                    print(f"  [auto] Restored Windows default output → {original_output}")
                else:
                    print(f"  [warn] Could not restore default output (was: {original_output}).")
                    print("         Restore it manually in Windows Sound > Output.")

        self._save_session_if_needed()
