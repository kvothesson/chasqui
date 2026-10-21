"""The landing's generated files match their source (docs/_build.py)."""
import importlib.util
import json
import re
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"

_spec = importlib.util.spec_from_file_location("landing_build", DOCS / "_build.py")
landing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(landing)


def _source() -> str:
    return (DOCS / "index.html").read_text(encoding="utf-8")


def test_committed_pages_are_what_the_build_writes():
    # If this fails: python docs/_build.py
    for rel, content in landing.build(_source()).items():
        assert (DOCS / rel).read_text(encoding="utf-8") == content, rel


def test_both_languages_have_the_same_questions():
    en, es = landing.faq(_source(), "en"), landing.faq(_source(), "es")
    assert len(en) == len(es) >= 5
    assert all(q and a for q, a in en + es)


def test_json_ld_parses_and_names_the_installer_version():
    # The link is version-free (latest/download); the version is the package's.
    import chasqui
    for lang in ("en", "es"):
        data = json.loads(json.dumps(landing.json_ld(_source(), lang)))
        app = data["@graph"][0]
        assert app["softwareVersion"] == chasqui.__version__
        assert app["downloadUrl"].endswith("/releases/latest/download/chasqui-setup.exe")


def test_spanish_page_points_assets_one_level_up():
    es = landing.build(_source())["es/index.html"]
    assert 'src="img/' not in es and 'href="img/' not in es
    assert '<link rel="canonical" href="https://kvothesson.com/chasqui/es/">' in es


def test_llms_txt_quotes_the_landing_price():
    price = re.search(r'<p class="big">(\$[\d.]+)<', _source()).group(1)
    assert price in (DOCS / "llms.txt").read_text(encoding="utf-8")
