"""Silence gate: don't stream audio nobody is speaking in.

gpt-realtime-translate bills by the minute of audio *sent* (core/pricing.py),
and a mic or a call capture is silent most of the time — in a two-way call
each direction is quiet while the other side talks. Without a gate chasqui
pays for every second of that silence.

The gate is deliberately blunt: an RMS level per chunk, no model. Three
things keep it from eating speech:

  - a low threshold (-50 dBFS by default: well under a quiet voice, above a
    muted or idle line), so a noisy room just leaves the gate open — no
    savings, but nothing lost;
  - HOLD: after the last loud chunk it stays open this long, so pauses
    between words, and the tail the model needs to finish a sentence, still
    go out. Measured with examples/gate_check.py: gpt-realtime-translate
    only lets go of the END of a translation while audio keeps arriving.
    With 1.5-2s of hold the last words of each sentence came out at the
    start of the next one (in a call: only when you speak again); 3s gave
    complete, aligned turns and still streamed ~half the minutes;
  - PRE-ROLL: while closed it keeps the last few hundred ms, and sends them
    first when speech resumes, so the opening consonant isn't clipped.

Pure bytes in, bytes out — no audio hardware, testable on its own.
"""

import math
from collections import deque

import numpy as np

from .constants import SAMPLE_RATE, CHANNELS, SAMPLE_WIDTH

BYTES_PER_MS = SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH // 1000   # 48

DEFAULT_THRESHOLD_DBFS = -50.0
DEFAULT_HOLD_MS = 3000
DEFAULT_PREROLL_MS = 300


def rms_dbfs(chunk: bytes) -> float:
    """Level of a PCM16 chunk in dBFS. Digital silence is -inf."""
    samples = np.frombuffer(chunk[: len(chunk) // 2 * 2], dtype="<i2")
    if samples.size == 0:
        return float("-inf")
    mean_square = float(np.mean(samples.astype(np.float64) ** 2))
    if mean_square == 0:
        return float("-inf")
    return 10 * math.log10(mean_square / (32768.0 ** 2))


class SilenceGate:
    def __init__(
        self,
        threshold_dbfs: float = DEFAULT_THRESHOLD_DBFS,
        hold_ms: int = DEFAULT_HOLD_MS,
        preroll_ms: int = DEFAULT_PREROLL_MS,
    ):
        self.threshold_dbfs = threshold_dbfs
        self.hold_ms = hold_ms
        self.preroll_bytes = preroll_ms * BYTES_PER_MS
        self._preroll: deque[bytes] = deque()
        self._preroll_size = 0
        self._open = False
        self._quiet_ms = 0.0
        self.bytes_skipped = 0      # what the gate kept off the meter

    @property
    def is_open(self) -> bool:
        return self._open

    def feed(self, chunk: bytes) -> list[bytes]:
        """Take one chunk, return the chunks to send now (maybe none)."""
        if not chunk:
            return []
        loud = rms_dbfs(chunk) >= self.threshold_dbfs

        if loud:
            self._quiet_ms = 0.0
            if self._open:
                return [chunk]
            self._open = True
            out = list(self._preroll) + [chunk]
            self._preroll.clear()
            self._preroll_size = 0
            return out

        if self._open:
            self._quiet_ms += len(chunk) / BYTES_PER_MS
            if self._quiet_ms >= self.hold_ms:
                self._open = False
            return [chunk]

        # Closed and quiet: keep it as pre-roll; whatever falls off the back
        # of the pre-roll is audio that never gets sent.
        self._preroll.append(chunk)
        self._preroll_size += len(chunk)
        while self._preroll and self._preroll_size - len(self._preroll[0]) >= self.preroll_bytes:
            dropped = self._preroll.popleft()
            self._preroll_size -= len(dropped)
            self.bytes_skipped += len(dropped)
        return []
