"""What a session costs, from what chasqui already counts.

Two billing shapes, and chasqui's default model uses the friendlier one:

  gpt-realtime-translate   billed by DURATION ($/minute of audio)
  gpt-realtime             billed by TOKENS (audio in/out, text in/out)

That split is why the translate endpoint never sends `response.done` — the
event that carries the `usage` object. There is nothing to report per response
when the meter is a clock. So for the default model the cost is not estimated
from token guesses: it is the audio chasqui actually streamed, which it counts
byte by byte, times a published rate.

Rates go stale. They live here as defaults and are overridable in
chasqui.yaml (`pricing:`) so a price change is a config edit, not a patch.
Prices below are USD, from OpenAI's pricing page as of 2026-07-25.
"""

from dataclasses import dataclass
from typing import Optional

from .constants import SAMPLE_RATE, CHANNELS, SAMPLE_WIDTH

# PCM16 mono 24kHz — 48000 bytes per second of audio.
BYTES_PER_SECOND = SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH


@dataclass(frozen=True)
class ModelRates:
    """Either `per_minute` is set (duration billing) or the token rates are."""
    per_minute: Optional[float] = None
    audio_in_per_1m: Optional[float] = None
    audio_out_per_1m: Optional[float] = None
    text_in_per_1m: Optional[float] = None
    text_out_per_1m: Optional[float] = None

    @property
    def is_duration_billed(self) -> bool:
        return self.per_minute is not None


RATES: dict[str, ModelRates] = {
    "gpt-realtime-translate": ModelRates(per_minute=0.034),
    "gpt-realtime-whisper":   ModelRates(per_minute=0.017),
    "gpt-realtime-mini":      ModelRates(
        audio_in_per_1m=10.0, audio_out_per_1m=20.0,
        text_in_per_1m=0.60, text_out_per_1m=2.40),
    "gpt-realtime":           ModelRates(
        audio_in_per_1m=32.0, audio_out_per_1m=64.0,
        text_in_per_1m=4.0, text_out_per_1m=24.0),
}

# chasqui asks for input transcription on every session (see
# Pipeline._build_translate_session). It is priced separately on the pricing
# page, and whether it stacks on top of the translate minute is NOT settled
# there. Counted by default: a meter that overshoots is annoying, one that
# undershoots is a lie. Verify against your dashboard and set
# `pricing.count_transcription: false` if it turns out to be included.
TRANSCRIPTION_MODEL = "gpt-realtime-whisper"

UNKNOWN_MODEL_NOTE = "no published rate for this model — cost not counted"


def rates_for(model: str) -> Optional[ModelRates]:
    """Rates for a model name, longest prefix first ('...-mini' before '...')."""
    if model in RATES:
        return RATES[model]
    for name in sorted(RATES, key=len, reverse=True):
        if model.startswith(name):
            return RATES[name]
    return None


def minutes_from_bytes(audio_bytes: int) -> float:
    return audio_bytes / BYTES_PER_SECOND / 60


@dataclass
class Usage:
    """What one pipeline accumulated. Bytes for duration billing, tokens for
    the rest; a pipeline fills in whichever its endpoint reports."""
    audio_bytes_sent: int = 0
    audio_bytes_received: int = 0
    audio_input_tokens: int = 0
    audio_output_tokens: int = 0
    text_input_tokens: int = 0
    text_output_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(*(
            getattr(self, f.name) + getattr(other, f.name)
            for f in self.__dataclass_fields__.values()
        ))

    @property
    def minutes_sent(self) -> float:
        return minutes_from_bytes(self.audio_bytes_sent)


@dataclass
class Price:
    """A cost figure plus why it is what it is."""
    usd: float = 0.0
    minutes: float = 0.0
    exact: bool = True      # False when a model has no published rate
    note: str = ""


def estimate(
    model: str,
    usage: Usage,
    count_transcription: bool = True,
    per_minute: Optional[float] = None,
    transcription_per_minute: Optional[float] = None,
) -> Price:
    """Cost of one pipeline's usage. Never raises — an unpriced model reports
    zero and says so, rather than inventing a number."""
    minutes = usage.minutes_sent
    rates = rates_for(model)

    if rates is None:
        return Price(usd=0.0, minutes=minutes, exact=False, note=UNKNOWN_MODEL_NOTE)

    if rates.is_duration_billed or per_minute is not None:
        rate = per_minute if per_minute is not None else rates.per_minute
        usd = minutes * rate
        if count_transcription:
            extra = transcription_per_minute
            if extra is None:
                whisper = RATES[TRANSCRIPTION_MODEL]
                extra = whisper.per_minute
            usd += minutes * extra
        return Price(usd=usd, minutes=minutes)

    usd = (
        usage.audio_input_tokens / 1_000_000 * (rates.audio_in_per_1m or 0.0)
        + usage.audio_output_tokens / 1_000_000 * (rates.audio_out_per_1m or 0.0)
        + usage.text_input_tokens / 1_000_000 * (rates.text_in_per_1m or 0.0)
        + usage.text_output_tokens / 1_000_000 * (rates.text_out_per_1m or 0.0)
    )
    return Price(usd=usd, minutes=minutes)


def format_usd(usd: float) -> str:
    """Cents matter here — a session can cost less than one."""
    if usd and usd < 0.01:
        return "<$0.01"
    return f"${usd:,.2f}"
