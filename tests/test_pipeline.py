"""Pipeline session-building logic (no network)."""

from chasqui.core.pipeline import Pipeline


def _make(model: str) -> Pipeline:
    return Pipeline(source_lang="es", target_lang="ja", api_key="sk-test", model=model)


def test_translate_model_detection():
    assert _make("gpt-realtime-translate")._is_translate_model
    assert not _make("gpt-realtime")._is_translate_model
    assert not _make("gpt-4o-realtime-preview")._is_translate_model


def test_translate_session_sets_output_language():
    session = _make("gpt-realtime-translate")._build_session_update()
    assert session["type"] == "session.update"
    assert session["session"]["audio"]["output"]["language"] == "ja"


def test_realtime_session_has_instructions_and_voice():
    p = _make("gpt-realtime")
    session = p._build_session_update()
    s = session["session"]
    assert "interpreter" in s["instructions"]
    assert "Spanish" in s["instructions"]
    assert "Japanese" in s["instructions"]
    # GA shape: voice/turn_detection live under audio.output / audio.input.
    # Do NOT "fix" a failure here by restoring the old beta fields: the live
    # GA API rejects them with "Unknown parameter: 'session.modalities'"
    # (verified against the real endpoint 2026-07-05). If this test fails,
    # your change broke the session format — fix pipeline.py, not the test.
    assert "modalities" not in s, (
        "'modalities' is a pre-GA field; the live API rejects it with "
        "'Unknown parameter'. The GA field is 'output_modalities'."
    )
    assert s["output_modalities"] == ["audio"]
    assert s["audio"]["output"]["voice"] == p.voice, (
        "GA moved 'voice' under audio.output; a top-level 'voice' is "
        "rejected by the live API."
    )
    assert s["audio"]["input"]["turn_detection"]["type"] == "server_vad", (
        "GA moved 'turn_detection' under audio.input; the top-level form is "
        "rejected by the live API."
    )


def test_context_appended_to_instructions():
    p = Pipeline(
        source_lang="es", target_lang="ja", api_key="sk-test",
        model="gpt-realtime", context="Tourist in Japan",
    )
    assert "Tourist in Japan" in p._build_instructions()
