"""Audio stream abstractions and concrete implementations.

All streams use PCM 16-bit mono at 24kHz — GPT-4o Realtime native format.
"""

import abc
import queue
import threading
from typing import Optional

import numpy as np

from .constants import SAMPLE_RATE, CHANNELS, SAMPLE_WIDTH, CHUNK_FRAMES, CHUNK_SIZE


def resolve_device(name: Optional[str | int], want_input: bool = True) -> Optional[str | int]:
    """Resolve a device name to a sounddevice index.

    Windows APIs report full device names ("Micrófono (2- USB Audio Device)")
    while PortAudio truncates them (~31 chars on MME), so exact or substring
    matching can fail in either direction. Match case-insensitive by prefix
    both ways against devices of the right kind; fall back to the original
    value so sounddevice's own matching still gets a chance.
    """
    if name is None or isinstance(name, int):
        return name
    text = str(name).strip()
    if text.isdigit():
        return int(text)
    try:
        import sounddevice as sd
        target = text.lower()
        for i, dev in enumerate(sd.query_devices()):
            channels = dev["max_input_channels"] if want_input else dev["max_output_channels"]
            if channels == 0:
                continue
            dev_name = dev["name"].strip().lower()
            if not dev_name:
                continue
            if dev_name.startswith(target) or target.startswith(dev_name) or target in dev_name:
                return i
    except Exception:
        pass
    return name


class AudioStream(abc.ABC):
    """Abstract base for any audio source or destination."""

    SAMPLE_RATE = SAMPLE_RATE
    CHANNELS = CHANNELS
    SAMPLE_WIDTH = SAMPLE_WIDTH

    def read(self, chunk_size: int = CHUNK_SIZE) -> bytes:
        """Read a chunk of PCM audio. Returns empty bytes when exhausted."""
        return b""

    def write(self, data: bytes) -> None:
        """Write a chunk of PCM audio."""
        pass

    def close(self) -> None:
        """Release resources."""
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ---------------------------------------------------------------------------
# Input streams
# ---------------------------------------------------------------------------


class MicStream(AudioStream):
    """Captures audio from a microphone (or throat mic) via sounddevice."""

    def __init__(self, device: Optional[str | int] = None, chunk_ms: int = 100):
        import sounddevice as sd
        self._sd = sd
        self.device = device
        self._chunk_frames = SAMPLE_RATE * chunk_ms // 1000
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=50)
        self._stopped = threading.Event()
        self._stream = None

    def _to_mono(self, indata: np.ndarray) -> np.ndarray:
        return indata[:, 0]

    def start(self) -> None:
        def _callback(indata, frames, time, status):
            if self._stopped.is_set():
                return
            pcm = (self._to_mono(indata) * 32767).astype(np.int16)
            try:
                self._queue.put_nowait(pcm.tobytes())
            except queue.Full:
                pass  # drop if consumer is slow

        self._stream = self._sd.InputStream(
            device=self.device,
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=self._chunk_frames,
            callback=_callback,
        )
        self._stream.start()

    def read(self, chunk_size: int = CHUNK_SIZE) -> bytes:
        if self._stopped.is_set():
            return b""
        try:
            return self._queue.get(timeout=1.0)
        except queue.Empty:
            return b""

    def close(self) -> None:
        self._stopped.set()
        if self._stream:
            self._stream.stop()
            self._stream.close()


class LoopbackStream(MicStream):
    """Captures system audio output (loopback) for media translation.

    Windows: enable 'Stereo Mix' in Sound > Recording devices.
    macOS:   install BlackHole (https://github.com/ExistentialAudio/BlackHole).
    """

    def _to_mono(self, indata: np.ndarray) -> np.ndarray:
        # loopback devices may deliver stereo — mix down
        return indata.mean(axis=1) if indata.ndim > 1 else indata[:, 0]


class BytesStream(AudioStream):
    """In-memory stream. Useful for testing."""

    def __init__(self, data: bytes = b""):
        self._buf = bytearray(data)
        self._pos = 0
        self._out = bytearray()

    def read(self, chunk_size: int = CHUNK_SIZE) -> bytes:
        chunk = bytes(self._buf[self._pos : self._pos + chunk_size])
        self._pos += chunk_size
        return chunk

    def write(self, data: bytes) -> None:
        self._out.extend(data)

    @property
    def output(self) -> bytes:
        return bytes(self._out)


# ---------------------------------------------------------------------------
# Output streams
# ---------------------------------------------------------------------------


class SpeakerStream(AudioStream):
    """Plays audio through a speaker or virtual audio device.

    Uses a background thread + queue to decouple playback from the async pipeline.
    """

    def __init__(self, device: Optional[str | int] = None):
        self.device = device
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=100)
        self._stopped = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._player, daemon=True)
        self._thread.start()

    def _player(self) -> None:
        import sounddevice as sd
        try:
            with sd.RawOutputStream(
                device=self.device,
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
            ) as stream:
                while not self._stopped.is_set():
                    try:
                        data = self._queue.get(timeout=0.05)
                        stream.write(data)
                    except queue.Empty:
                        continue
        except Exception as e:
            print(f"  [SpeakerStream error] {e}", flush=True)

    def write(self, data: bytes) -> None:
        if data and not self._stopped.is_set():
            try:
                self._queue.put_nowait(data)
            except queue.Full:
                pass  # drop if player can't keep up

    def close(self) -> None:
        self._stopped.set()
        if self._thread:
            self._thread.join(timeout=2.0)


class NullStream(AudioStream):
    """Discards all audio. Useful for text-only mode or testing."""
    pass


# ---------------------------------------------------------------------------
# Combinators
# ---------------------------------------------------------------------------


class MultiOutputStream(AudioStream):
    """Fans out writes to multiple output streams simultaneously."""

    def __init__(self, *streams: AudioStream):
        self._streams = streams

    def write(self, data: bytes) -> None:
        for stream in self._streams:
            stream.write(data)

    def close(self) -> None:
        for stream in self._streams:
            stream.close()
