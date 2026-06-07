"""Audio stream abstractions and concrete implementations.

All streams use PCM 16-bit mono at 24kHz — GPT-4o Realtime native format.
"""

import abc
import queue
import threading
from typing import Optional

import numpy as np

from .constants import SAMPLE_RATE, CHANNELS, SAMPLE_WIDTH, CHUNK_FRAMES, CHUNK_SIZE


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

    def start(self) -> None:
        def _callback(indata, frames, time, status):
            if self._stopped.is_set():
                return
            pcm = (indata[:, 0] * 32767).astype(np.int16)
            try:
                self._queue.put_nowait(pcm.tobytes())
            except queue.Full:
                pass  # drop oldest if consumer is slow

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


class LoopbackStream(AudioStream):
    """Captures system audio output (loopback) for media translation.

    Windows: enable 'Stereo Mix' in Sound > Recording devices.
    macOS:   install BlackHole (https://github.com/ExistentialAudio/BlackHole).
    """

    def __init__(self, device: Optional[str | int] = None):
        import sounddevice as sd
        self._sd = sd
        self.device = device
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=50)
        self._stopped = threading.Event()
        self._stream = None

    def start(self) -> None:
        def _callback(indata, frames, time, status):
            if self._stopped.is_set():
                return
            # mix to mono if stereo
            mono = indata.mean(axis=1) if indata.ndim > 1 else indata[:, 0]
            pcm = (mono * 32767).astype(np.int16)
            try:
                self._queue.put_nowait(pcm.tobytes())
            except queue.Full:
                pass

        self._stream = self._sd.InputStream(
            device=self.device,
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=CHUNK_FRAMES,
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
    """Plays audio through a speaker or virtual audio device."""

    def __init__(self, device: Optional[str | int] = None):
        import sounddevice as sd
        self._sd = sd
        self.device = device
        self._stream = None
        self._lock = threading.Lock()

    def start(self) -> None:
        self._stream = self._sd.RawOutputStream(
            device=self.device,
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=CHUNK_FRAMES,
        )
        self._stream.start()

    def write(self, data: bytes) -> None:
        if self._stream and data:
            with self._lock:
                try:
                    self._stream.write(data)
                except Exception:
                    pass  # device disconnected, ignore

    def close(self) -> None:
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass


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
