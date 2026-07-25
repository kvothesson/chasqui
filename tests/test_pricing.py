"""Cost meter.

A number on screen that claims to be money gets believed. These tests pin the
arithmetic and, more importantly, the two ways it could quietly lie: charging
one direction when two are running, and inventing a price for a model whose
rate nobody published.

No network: rates are a table, usage is counted bytes.
"""

import pytest

from chasqui.core.pricing import (
    BYTES_PER_SECOND,
    RATES,
    Usage,
    estimate,
    format_usd,
    minutes_from_bytes,
    rates_for,
)


def _minutes(n: float) -> Usage:
    return Usage(audio_bytes_sent=int(BYTES_PER_SECOND * 60 * n))


def test_a_minute_of_audio_is_a_minute():
    assert minutes_from_bytes(BYTES_PER_SECOND * 60) == pytest.approx(1.0), (
        "PCM16 mono at 24kHz is 48000 bytes per second. If this fails the "
        "meter is off by whatever factor the audio format changed by, and "
        "every cost shown is wrong by the same factor."
    )


def test_translate_model_is_billed_by_the_minute():
    price = estimate("gpt-realtime-translate", _minutes(10), count_transcription=False)
    assert price.usd == pytest.approx(0.34), (
        "10 minutes at $0.034/min is $0.34. The translate endpoint bills by "
        "duration, not tokens — which is why it never sends response.done and "
        "why the byte counters exist."
    )
    assert price.exact


def test_transcription_is_counted_by_default():
    """chasqui always configures input transcription, and it is priced
    separately. Counted unless proven included: overshooting annoys,
    undershooting misleads."""
    with_it = estimate("gpt-realtime-translate", _minutes(10))
    without = estimate("gpt-realtime-translate", _minutes(10), count_transcription=False)
    assert with_it.usd > without.usd
    assert with_it.usd == pytest.approx(0.51), "10 min × ($0.034 + $0.017)"


def test_two_directions_cost_twice():
    """Headset runs two pipelines, each its own billed stream. Summing their
    usage is the whole reason a bidirectional session shows its real rate."""
    one_way = estimate("gpt-realtime-translate", _minutes(5))
    both = estimate("gpt-realtime-translate", _minutes(5) + _minutes(5))
    assert both.usd == pytest.approx(one_way.usd * 2), (
        "Usage from both pipelines must add up. If this fails, a headset "
        "session reports half of what it actually costs."
    )


def test_config_rate_overrides_the_table():
    """Prices change. That has to be a config edit, not a patch."""
    price = estimate(
        "gpt-realtime-translate", _minutes(10),
        count_transcription=False, per_minute=0.10)
    assert price.usd == pytest.approx(1.0)


def test_token_billed_model_uses_reported_tokens():
    usage = Usage(audio_input_tokens=1_000_000, audio_output_tokens=500_000)
    price = estimate("gpt-realtime", usage)
    assert price.usd == pytest.approx(32.0 + 32.0), (
        "$32 per 1M audio in, $64 per 1M audio out. gpt-realtime bills by "
        "tokens and reports them on response.done."
    )


def test_unknown_model_reports_zero_and_says_why():
    price = estimate("some-future-model", _minutes(10))
    assert price.usd == 0.0 and not price.exact and price.note, (
        "A model with no published rate must not be silently priced with "
        "another model's numbers. Report zero and say so — a confidently "
        "wrong bill is worse than a missing one."
    )


def test_rates_lookup_prefers_the_longer_name():
    assert rates_for("gpt-realtime-mini") is RATES["gpt-realtime-mini"], (
        "'gpt-realtime-mini' starts with 'gpt-realtime'. Matching the shorter "
        "name first prices the mini model at 3x its real rate."
    )
    assert rates_for("gpt-realtime-translate-2.1") is RATES["gpt-realtime-translate"], (
        "Versioned model names must fall back to their family's rate."
    )


def test_sub_cent_costs_are_not_rounded_to_zero():
    assert format_usd(0.004) == "<$0.01", (
        "A short session costs less than a cent. Showing '$0.00' reads as "
        "free, which is the one thing it is not."
    )
    assert format_usd(0.0) == "$0.00"
    assert format_usd(12.5) == "$12.50"
