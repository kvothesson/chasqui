"""Audio stream abstractions and concrete implementations.

All streams use PCM 16-bit mono at 24kHz — GPT-4o Realtime native format.
"""

import abc
import queue
import threading
from typing import Optional

import numpy as np

from .constants import SAMPLE_RATE, CHANNELS, SAMPLE_WIDTH, CHUNK_SIZE


def refresh_devices() -> None:
    """Re-initialize PortAudio so device indices match the current Windows order.

    Windows renumbers live waveIn/waveOut IDs the moment the default device
    changes (the new default jumps to the first slot of its type). An index
    resolved before the change silently opens a DIFFERENT device after it —
    e.g. the headset adapter's real mic index pointing at CABLE Output after
    the default-mic switch. Call this after any default-device switch and
    before resolving names to indices. Must not be called with streams open.
    """
    import sounddevice as sd
    try:
        sd._terminate()
        sd._initialize()
    except Exception:
        pass


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


def find_device_by_hints(
    hints: list[str],
    override: Optional[str] = None,
    require_output: bool = False,
) -> Optional[str]:
    """First device whose name contains one of `hints`, or `override` as-is.

    Returns a NAME, not an index: callers usually switch a Windows default
    device afterwards, which renumbers indices (see `refresh_devices`). Resolve
    to an index only once the switching is done.
    """
    if override:
        return override
    try:
        import sounddevice as sd
        for device in sd.query_devices():
            name: str = device["name"]
            if not any(h.lower() in name.lower() for h in hints):
                continue
            channels = "max_output_channels" if require_output else "max_input_channels"
            if device[channels] == 0:
                continue
            return name
    except Exception:
        pass
    return None


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


class TeeInputStream(AudioStream):
    """Reads from a source and hands every chunk to `on_chunk` on the way."""

    def __init__(self, source: AudioStream, on_chunk):
        self._source = source
        self._on_chunk = on_chunk

    def start(self) -> None:
        if hasattr(self._source, "start"):
            self._source.start()

    def read(self, chunk_size: int = CHUNK_SIZE) -> bytes:
        chunk = self._source.read(chunk_size)
        if chunk:
            self._on_chunk(chunk)
        return chunk

    def close(self) -> None:
        self._source.close()


class PassthroughMixStream(AudioStream):
    """Mixes the original voice, quietly, under the translation.

    The other side of the call hears you translated, with your real voice
    riding underneath at `gain` (0.15 is a good start): your tone survives,
    and in a mixed-language call they still catch what you said verbatim.

    Feed the original with `feed_side()` (a TeeInputStream on the mic does
    it). Every `write()` of translated audio takes the same number of bytes
    of buffered original and sums them. gpt-realtime-translate streams its
    output continuously, silence included, so in practice the translation
    is the clock and the original drains at real time. If no translation is
    flowing, original older than `max_lag_ms` goes out on its own rather
    than piling up.
    """

    def __init__(self, destination: AudioStream, gain: float, max_lag_ms: int = 200):
        self._dst = destination
        self.gain = max(0.0, min(1.0, gain))
        self._max_lag_bytes = max_lag_ms * SAMPLE_RATE * SAMPLE_WIDTH // 1000
        self._side = bytearray()
        self._lock = threading.Lock()

    def start(self) -> None:
        if hasattr(self._dst, "start"):
            self._dst.start()

    def feed_side(self, chunk: bytes) -> None:
        scaled = (np.frombuffer(chunk[: len(chunk) // 2 * 2], dtype="<i2") * self.gain)
        scaled = scaled.astype("<i2").tobytes()
        overflow = b""
        with self._lock:
            self._side.extend(scaled)
            excess = len(self._side) - self._max_lag_bytes
            if excess > 0:
                excess -= excess % 2
                overflow = bytes(self._side[:excess])
                del self._side[:excess]
        if overflow:
            self._dst.write(overflow)

    def write(self, data: bytes) -> None:
        with self._lock:
            n = min(len(self._side), len(data)) // 2 * 2
            side = bytes(self._side[:n])
            del self._side[:n]
        if n:
            mixed = (np.frombuffer(data[:n], dtype="<i2").astype(np.int32)
                     + np.frombuffer(side, dtype="<i2"))
            data = np.clip(mixed, -32768, 32767).astype("<i2").tobytes() + data[n:]
        self._dst.write(data)

    def close(self) -> None:
        self._dst.close()
