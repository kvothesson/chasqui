"""First run: where the key goes, how it is checked, what the machine has.

No network: urlopen is replaced, so these pin the meaning of each OpenAI
answer rather than OpenAI itself.
"""

import io
import urllib.error

import pytest
import yaml

from chasqui.core import firstrun
from chasqui.core.config import load_config


@pytest.fixture
def user_config(tmp_path, monkeypatch):
    path = tmp_path / ".chasqui" / "config.yaml"
    monkeypatch.setattr(firstrun, "USER_CONFIG_PATH", path)
    return path


def test_save_creates_the_file_and_reads_back(user_config):
    firstrun.save_api_key("  sk-abc  ")
    assert user_config.exists()
    assert firstrun.stored_api_key() == "sk-abc"


def test_save_keeps_the_rest_of_the_config(user_config):
    user_config.parent.mkdir(parents=True)
    user_config.write_text(
        "api:\n  model: gpt-realtime\nsession:\n  source_lang: en\n", encoding="utf-8")
    firstrun.save_api_key("sk-new")
    data = yaml.safe_load(user_config.read_text(encoding="utf-8"))
    assert data["api"] == {"model": "gpt-realtime", "key": "sk-new"}
    assert data["session"]["source_lang"] == "en"


def test_missing_or_broken_file_means_no_key(user_config):
    assert firstrun.stored_api_key() == ""
    user_config.parent.mkdir(parents=True)
    user_config.write_text("[not: a mapping", encoding="utf-8")
    assert firstrun.stored_api_key() == ""


def test_load_config_falls_back_to_the_saved_key(user_config, tmp_path, monkeypatch):
    """A project yaml that points at an unset env var must not hide the key
    the setup window saved — that is the installed app's normal case."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    project = tmp_path / "chasqui.yaml"
    project.write_text("api:\n  key: ${OPENAI_API_KEY}\n", encoding="utf-8")
    firstrun.save_api_key("sk-saved")
    assert load_config(project).api_key == "sk-saved"


def test_explicit_key_wins_over_the_saved_one(user_config, tmp_path):
    firstrun.save_api_key("sk-saved")
    project = tmp_path / "chasqui.yaml"
    project.write_text("api:\n  key: sk-project\n", encoding="utf-8")
    assert load_config(project).api_key == "sk-project"


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _answer(monkeypatch, code=None, exc=None):
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["auth"] = request.get_header("Authorization")
        if exc:
            raise exc
        if code:
            raise urllib.error.HTTPError(request.full_url, code, "x", {}, None)
        return _Response(b'{"id": "m"}')

    monkeypatch.setattr(firstrun.urllib.request, "urlopen", fake_urlopen)
    return seen


def test_good_key_asks_for_the_model_it_will_use(monkeypatch):
    seen = _answer(monkeypatch)
    result = firstrun.check_api_key("sk-good", "gpt-realtime-translate")
    assert result.status == "ok" and result.usable
    assert seen["url"].endswith("/v1/models/gpt-realtime-translate")
    assert seen["auth"] == "Bearer sk-good"


@pytest.mark.parametrize("code, status, usable", [
    (401, "invalid", False),
    (404, "no_model", True),
    (429, "ok", True),
    (503, "offline", False),
])
def test_http_answers(monkeypatch, code, status, usable):
    _answer(monkeypatch, code=code)
    result = firstrun.check_api_key("sk-x", "gpt-realtime")
    assert (result.status, result.usable) == (status, usable)


def test_no_network(monkeypatch):
    _answer(monkeypatch, exc=OSError("down"))
    assert firstrun.check_api_key("sk-x", "m").status == "offline"


@pytest.mark.parametrize("key", ["", "   ", "hello"])
def test_obviously_wrong_keys_never_reach_openai(monkeypatch, key):
    def boom(*a, **k):
        raise AssertionError("should not call OpenAI")

    monkeypatch.setattr(firstrun.urllib.request, "urlopen", boom)
    assert firstrun.check_api_key(key, "m").status == "invalid"


def test_cable_needs_both_ends():
    both = ["Altavoces (Realtek)", "CABLE Input (VB-Audio Virtual Cable)",
            "CABLE Output (VB-Audio Virtual C"]
    assert firstrun.has_virtual_cable(both)
    assert not firstrun.has_virtual_cable(both[:2])
    assert not firstrun.has_virtual_cable(["Altavoces (Realtek)"])


def test_switcher_is_found_inside_the_installed_app(tmp_path, monkeypatch):
    """The installer ships AudioDeviceCmdlets; a frozen chasqui must use it
    instead of asking the user for Install-Module."""
    from chasqui.core import windevice

    assert windevice.bundled_module() is None          # a plain pip install
    module = tmp_path / "AudioDeviceCmdlets"
    module.mkdir()
    (module / "AudioDeviceCmdlets.psd1").write_text("@{}", encoding="utf-8")
    monkeypatch.setattr(windevice.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert windevice.bundled_module() == module / "AudioDeviceCmdlets.psd1"
