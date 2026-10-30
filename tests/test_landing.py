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


def test_every_guide_exists_in_both_languages_and_points_at_its_pair():
    pages = landing.build(_source())
    for key, slugs in landing.GUIDES.items():
        en = pages[f"{slugs['en']}/index.html"]
        es = pages[f"es/{slugs['es']}/index.html"]
        for page in (en, es):
            assert f'hreflang="en" href="{landing.guide_url(key, "en")}"' in page
            assert f'hreflang="es" href="{landing.guide_url(key, "es")}"' in page
        assert f'rel="canonical" href="{landing.guide_url(key, "en")}"' in en
        assert f'rel="canonical" href="{landing.guide_url(key, "es")}"' in es


def test_guides_leave_no_placeholder_and_only_link_to_real_guides():
    pages = landing.build(_source())
    for key, slugs in landing.GUIDES.items():
        for rel in (f"{slugs['en']}/index.html", f"es/{slugs['es']}/index.html"):
            main = re.search(r"<main.*</main>", pages[rel], re.S).group(0)
            assert not re.search(r"\{\w+\}", main), rel
            parent = "es/" if rel.startswith("es/") else ""
            for slug in re.findall(r'href="\.\./([\w-]+)/"', main):
                assert f"{parent}{slug}/index.html" in pages, (rel, slug)


def test_landing_links_every_guide():
    for key in landing.GUIDES:
        for lang in ("en", "es"):
            assert f'href="{landing.guide_url(key, lang)}"' in _source()


def test_guides_quote_the_landing_prices():
    price = re.search(r'<p class="big">(\$[\d.]+)<', _source()).group(1)
    for lang in ("en", "es"):
        assert price in landing.guide_source("media", lang)[1]
        assert "0.102" in landing.guide_source("calls", lang)[1]
