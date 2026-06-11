"""Config loading and override behavior."""

import os

import pytest

from chasqui.core.config import Config, _resolve_env


def test_defaults():
    cfg = Config()
    assert cfg.adapter == "text"
    assert cfg.source_lang == "es"
    assert cfg.target_lang == "ja"


def test_from_yaml(tmp_path):
    yaml_file = tmp_path / "chasqui.yaml"
    yaml_file.write_text(
        """
api:
  model: gpt-realtime-translate
session:
  source_lang: en
  target_lang: ja
adapter: device
device:
  mic: "USB Mic"
  speaker: "USB Speaker"
""",
        encoding="utf-8",
    )
    cfg = Config.from_yaml(yaml_file)
    assert cfg.model == "gpt-realtime-translate"
    assert cfg.source_lang == "en"
    assert cfg.adapter == "device"
    assert cfg.device.mic == "USB Mic"


def test_resolve_env(monkeypatch):
    monkeypatch.setenv("MY_KEY", "sk-test")
    assert _resolve_env("${MY_KEY}") == "sk-test"
    assert _resolve_env("literal") == "literal"
    assert _resolve_env("${MISSING_VAR_XYZ}") == ""


def test_validate_requires_api_key():
    cfg = Config()
    cfg.api_key = ""
    with pytest.raises(ValueError):
        cfg.validate()
