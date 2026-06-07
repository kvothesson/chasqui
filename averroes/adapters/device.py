"""Device adapter — physical pendant hardware.

Flow: throat mic → pipeline → speaker (Japanese hears) + earphone (user hears).
"""

from ..core.audio import MicStream, SpeakerStream, MultiOutputStream
from .base import BaseAdapter


class DeviceAdapter(BaseAdapter):
    """Designed for the Averroes pendant.

    Requires:
    - USB throat/contact mic
    - USB speaker (faces outward toward conversation partner)
    - Bone conduction earphone or standard earphone (user's private channel)
    """

    def run(self) -> None:
        self._print_header("Device mode")
        print(f"  Mic     : {self.config.device.mic or 'system default'}")
        print(f"  Speaker : {self.config.device.speaker or 'system default'}")
        print(f"  Earphone: {self.config.device.earphone or 'system default'}")
        print()

        mic = MicStream(device=self.config.device.mic)
        speaker = SpeakerStream(device=self.config.device.speaker)
        earphone = SpeakerStream(device=self.config.device.earphone)
        out = MultiOutputStream(speaker, earphone)

        mic.start()
        speaker.start()
        earphone.start()

        pipeline = self._make_pipeline()

        try:
            print(f"Ready. Speak in {self.config.source_lang.upper()}. (Ctrl+C to stop)\n")
            pipeline.run(mic, out)
        except KeyboardInterrupt:
            print("\nStopping...")
        finally:
            pipeline.stop()
            mic.close()
            out.close()

        self._save_session_if_needed()
