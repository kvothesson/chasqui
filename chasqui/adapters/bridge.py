"""Bridge adapter — bidirectional simultaneous translation for any voice app (ChatGPT, Discord, Zoom, Meet…).

Two pipelines run in parallel:

  OUT  real mic  →  ES→JA pipeline  →  CABLE Input   (the app sees this as your mic)
  IN   CABLE Output (loopback)  →  JA→ES pipeline  →  earphones

Setup:
  1. Install VB-Audio Cable: https://vb-audio.com/Cable/
  2. In the app, select "CABLE Output" as your microphone input.
  3. Run: chasqui listen --adapter bridge
"""

import sys
import threading
from typing import Optional

from ..core.audio import MicStream, LoopbackStream, SpeakerStream
from .base import BaseAdapter

_CABLE_INPUT_HINTS  = ["CABLE Input"]   # playback device → chasqui sends translated audio here
_CABLE_OUTPUT_HINTS = ["CABLE Output"]  # recording device → chasqui captures app audio from here


class BridgeAdapter(BaseAdapter):
    """Bidirectional real-time translation for any voice app."""

    def run(self) -> None:
        self._print_header("Bridge mode (bidirectional)")

        cable_input  = self._find_device(_CABLE_INPUT_HINTS,  self.config.device.speaker, require_output=True)
        cable_output = self._find_device(_CABLE_OUTPUT_HINTS, None, require_output=False)

        print(f"  OUT  real mic → {self.config.source_lang}→{self.config.target_lang} → {cable_input or 'default speaker'}")
        print(f"  IN   {cable_output or 'default loopback'} → {self.config.target_lang}→{self.config.source_lang} → {self.config.device.earphone or 'default speaker'}")
        if not cable_input:
            print("\n  [warn] CABLE Input not found — install VB-Audio Cable and rerun.")
        print()
        print("  In your app (ChatGPT, Discord, Zoom...), set microphone to 'CABLE Output'.")
        print("  (Ctrl+C to stop)\n")

        # OUT pipeline: my mic → translated → CABLE Input (they hear me in their language)
        mic_in      = MicStream(device=self.config.device.mic)
        cable_out   = SpeakerStream(device=cable_input)
        pipeline_out = self._make_pipeline()

        # IN pipeline: their audio (CABLE Output loopback) → translated → my earphones
        loopback_in  = LoopbackStream(device=cable_output)
        earphone_out = SpeakerStream(device=self.config.device.earphone)
        pipeline_in  = self._make_pipeline_reverse()

        # Start all streams
        mic_in.start()
        cable_out.start()
        loopback_in.start()
        earphone_out.start()

        stop_event = threading.Event()

        def _safe_print(msg: str) -> None:
            try:
                print(msg, flush=True)
            except UnicodeEncodeError:
                print(msg.encode("ascii", errors="replace").decode(), flush=True)

        def _run_out():
            _safe_print("  [OUT] Connecting to API...")
            try:
                pipeline_out.run(mic_in, cable_out)
            except Exception as e:
                if not stop_event.is_set():
                    _safe_print(f"\n  [OUT error] {e}")
            finally:
                stop_event.set()

        def _run_in():
            _safe_print("  [IN]  Connecting to API...")
            try:
                pipeline_in.run(loopback_in, earphone_out)
            except Exception as e:
                if not stop_event.is_set():
                    _safe_print(f"\n  [IN error] {e}")
            finally:
                stop_event.set()

        t_out = threading.Thread(target=_run_out, daemon=True)
        t_in  = threading.Thread(target=_run_in,  daemon=True)
        t_out.start()
        t_in.start()

        try:
            while not stop_event.is_set():
                stop_event.wait(timeout=0.5)
        except KeyboardInterrupt:
            _safe_print("\nStopping...")
        finally:
            stop_event.set()
            pipeline_out.stop()
            pipeline_in.stop()
            mic_in.close()
            cable_out.close()
            loopback_in.close()
            earphone_out.close()

        t_out.join(timeout=3)
        t_in.join(timeout=3)
        self._save_session_if_needed()

    def _make_pipeline_reverse(self):
        """Pipeline for the IN direction: target_lang → source_lang."""
        from ..core.pipeline import Pipeline, TranslationEvent

        def _on_event(event: TranslationEvent):
            self._session.add_turn(
                source_text=event.source_text,
                target_text=event.target_text,
                latency_ms=event.latency_ms,
            )
            if self.config.logging.show_transcript:
                src = self.config.target_lang.upper()
                tgt = self.config.source_lang.upper()
                print(f"\n  [{src}→{tgt}] {event.source_text!r}")
                print(f"          {event.target_text!r}  {event.latency_ms:.0f}ms")

        return Pipeline(
            source_lang=self.config.target_lang,
            target_lang=self.config.source_lang,
            api_key=self.config.api_key,
            model=self.config.model,
            context=self.config.context,
            voice=self.config.voice,
            on_translation=_on_event,
            vad_threshold=self.config.vad_threshold,
            vad_silence_ms=self.config.vad_silence_ms,
        )

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
