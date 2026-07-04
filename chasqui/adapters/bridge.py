"""Bridge adapter — bidirectional simultaneous translation for any voice app
(ChatGPT, Discord, Zoom, Meet…).

Two pipelines run in parallel, each over its OWN virtual cable:

  OUT  real mic  →  ES→JA pipeline  →  CABLE Input    (app mic = CABLE Output)
  IN   app speaker = second cable   →  JA→ES pipeline →  earphones

The IN direction needs a SECOND virtual cable, separate from the OUT one.
The first cable ("CABLE Output") carries *your own translated voice* into the
app — capturing it would translate chasqui back to itself in an echo loop.

Setup:
  1. Install VB-Audio Cable (https://vb-audio.com/Cable/) — used for OUT.
  2. Install a second virtual cable for IN: Hi-Fi Cable (free) or
     VB-Cable A+B (both at vb-audio.com). Note: "VB-Audio Point" devices
     are VB-Cable itself under another name — NOT a second cable.
  3. In the app:  microphone = "CABLE Output",  speaker = the second cable.
  4. Run: chasqui listen --adapter bridge
"""

import threading
from typing import Optional

from ..core.audio import MicStream, LoopbackStream, SpeakerStream, resolve_device
from .base import BaseAdapter, _safe_print

_CABLE_INPUT_HINTS = ["CABLE Input (VB-Audio Virtual"]  # playback device → chasqui sends translated audio here

# Recording-side hints for the SECOND cable (IN direction). Deliberately
# excludes plain "CABLE Output" — that is the OUT cable carrying our own
# translated voice; capturing it creates a feedback translation loop.
# "VB-Audio Point" is also excluded: it is VB-Cable's internal WDM-KS name
# for the SAME cable, not a separate one (verified by tone loop test).
_IN_CAPTURE_HINTS = [
    "CABLE-B Output",
    "Hi-Fi Cable Output",
    # Last resort — no second cable installed: capture the system default
    # output directly. Only works if the app plays to the default output.
    "Stereo Mix",
    "What U Hear",
]

# Playback-side hints for the second cable — what the user selects as the
# app's speaker. Only used to print accurate instructions.
_IN_PLAYBACK_HINTS = [
    "CABLE-B Input",
    "Hi-Fi Cable Input",
]


class BridgeAdapter(BaseAdapter):
    """Bidirectional real-time translation for any voice app."""

    header = "Bridge mode (bidirectional)"
    app_label = "your app (ChatGPT, Discord, Zoom...)"

    def run(self) -> None:
        self._print_header(self.header)

        cable_input = self._find_device(_CABLE_INPUT_HINTS, self.config.device.speaker, require_output=True)
        in_capture  = self._find_device(_IN_CAPTURE_HINTS,  self.config.device.loopback, require_output=False)
        in_playback = self._find_device(_IN_PLAYBACK_HINTS, None, require_output=True)

        print(f"  OUT  real mic → {self.config.source_lang}→{self.config.target_lang} → {cable_input or 'default speaker'}")
        print(f"  IN   {in_capture or '(no second cable found)'} → {self.config.target_lang}→{self.config.source_lang} → {self.config.device.earphone or 'default speaker'}")
        if not cable_input:
            print("\n  [warn] CABLE Input not found — install VB-Audio Cable and rerun.")
        if not in_capture:
            print("\n  [warn] No capture device found for the IN direction.")
            print("         Enable 'Stereo Mix' in Windows Sound > Recording devices,")
            print("         install a second cable (VB-Cable A+B or Hi-Fi Cable,")
            print("         vb-audio.com), or set device.loopback in chasqui.yaml.")
            print("         IN translation is DISABLED for this session.")
        print()
        print(f"  In {self.app_label}:")
        print("    microphone → 'CABLE Output'")
        if in_capture:
            if any(h.lower() in in_capture.lower() for h in ("stereo mix", "what u hear")):
                print("    speaker    → leave as your default output (Stereo Mix captures it)")
            else:
                print(f"    speaker    → '{in_playback or in_capture}'")
        print("  (Ctrl+C to stop)\n")

        # OUT pipeline: my mic → translated → CABLE Input (they hear me in their language)
        out_tuple = (
            self._make_pipeline(),
            MicStream(device=resolve_device(self.config.device.mic, want_input=True)),
            SpeakerStream(device=cable_input),
        )
        in_tuple = None
        if in_capture:
            in_tuple = (
                self._make_pipeline_reverse(),
                LoopbackStream(device=in_capture),
                SpeakerStream(device=resolve_device(self.config.device.earphone, want_input=False)),
            )

        self._run_parallel(out_tuple, in_tuple)
        self._save_session_if_needed()

    def _run_parallel(self, out_tuple, in_tuple=None) -> None:
        """Start OUT (and optionally IN) pipelines in parallel threads and block until done.

        out_tuple: (pipeline, in_stream, out_stream)
        in_tuple:  (pipeline, in_stream, out_stream) or None
        """
        pipeline_out, mic_in, cable_out = out_tuple

        mic_in.start()
        cable_out.start()

        if in_tuple:
            pipeline_in, loopback_in, earphone_out = in_tuple
            loopback_in.start()
            earphone_out.start()

        stop_event = threading.Event()

        def _run_direction(label: str, pipeline, in_stream, out_stream):
            _safe_print(f"  [{label}] Connecting to API...")
            try:
                pipeline.run(in_stream, out_stream)
            except Exception as e:
                if not stop_event.is_set():
                    _safe_print(f"\n  [{label} error] {e}")
            finally:
                stop_event.set()

        t_out = threading.Thread(
            target=_run_direction, args=("OUT", pipeline_out, mic_in, cable_out), daemon=True)
        t_out.start()
        t_in = None
        if in_tuple:
            t_in = threading.Thread(
                target=_run_direction, args=("IN", pipeline_in, loopback_in, earphone_out), daemon=True)
            t_in.start()

        try:
            while not stop_event.is_set():
                stop_event.wait(timeout=0.5)
        except KeyboardInterrupt:
            _safe_print("\nStopping...")
        finally:
            stop_event.set()
            pipeline_out.stop()
            mic_in.close()
            cable_out.close()
            if in_tuple:
                pipeline_in.stop()
                loopback_in.close()
                earphone_out.close()

        t_out.join(timeout=3)
        if t_in:
            t_in.join(timeout=3)

    @staticmethod
    def _find_device(hints: list[str], override: Optional[str], require_output: bool = False) -> Optional[str]:
        """Find a device by name hints. require_output=True filters for playback devices."""
        if override:
            return override
        try:
            import sounddevice as sd
            for device in sd.query_devices():
                name: str = device["name"]
                if not any(h.lower() in name.lower() for h in hints):
                    continue
                if require_output and device["max_output_channels"] == 0:
                    continue
                if not require_output and device["max_input_channels"] == 0:
                    continue
                return name
        except Exception:
            pass
        return None
