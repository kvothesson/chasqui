"""Writes the landing's head metadata and its Spanish copy at docs/es/.

docs/index.html is the one source: every text is in it twice, data-l="en" and
data-l="es". Search engines want one URL per language, though (Google's
crawler sends no language and never sees a page that switches by browser), so
this script:

- fills the block between the head markers in docs/index.html with the
  English title, description, canonical, hreflang, Open Graph and JSON-LD;
- writes docs/es/index.html: the same page, Spanish fixed, Spanish head.

The FAQPage JSON-LD is read from the visible FAQ, so the two cannot disagree.
GitHub Pages serves docs/ as it is (Jekyll skips names starting with "_").
Run it after every edit to the page:

    python docs/_build.py

tests/test_landing.py fails if the committed files are not what this writes.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parent
SITE = "https://kvothesson.com/chasqui/"
URLS = {"en": SITE, "es": SITE + "es/"}
LOCALES = {"en": "en_US", "es": "es_LA"}

META = {
    "en": {
        "title": "chasqui: real-time voice translation for calls and videos",
        "description": (
            "Real-time voice translator for Windows: two-way calls in any app, "
            "YouTube and streams. Open source, runs on your own OpenAI key, "
            "$0.051 a minute."
        ),
        "alt": (
            "The chasqui window: language pickers, mode, Start, and a live "
            "transcript with each line and its translation"
        ),
        "og_alt": "chasqui, real-time voice translation for Windows, next to its window with a live transcript",
    },
    "es": {
        "title": "chasqui: traducción de voz en tiempo real para llamadas y videos",
        "description": (
            "Traductor de voz en tiempo real para Windows: llamadas de ida y "
            "vuelta en cualquier app, YouTube y streams. Código abierto, con tu "
            "propia API key de OpenAI, US$0.051 por minuto."
        ),
        "alt": (
            "La ventana de chasqui: idiomas, modo, Start y la transcripción en "
            "vivo con cada frase y su traducción"
        ),
        "og_alt": "chasqui, traducción de voz en tiempo real para Windows, junto a su ventana con la transcripción en vivo",
    },
}

HEAD_RE = re.compile(r"(<!-- head:start[^>]*-->\n).*?(<!-- head:end -->)", re.S)
DOWNLOAD_RE = re.compile(r"releases/download/v([\w.]+)/chasqui-setup-[\w.]+\.exe")


def _text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", fragment)).split())


def faq(page: str, lang: str) -> list[tuple[str, str]]:
    block = re.search(rf'<div class="faq" data-l="{lang}">(.*?)\n  </div>', page, re.S)
    if not block:
        raise SystemExit(f"no FAQ block for {lang}")
    pairs = re.findall(r"<h3>(.*?)</h3>\s*<p>(.*?)</p>", block.group(1), re.S)
    return [(_text(q), _text(a)) for q, a in pairs]


def json_ld(page: str, lang: str) -> dict:
    m = META[lang]
    url = URLS[lang]
    download = DOWNLOAD_RE.search(page)
    if not download:
        raise SystemExit("no installer link found in the page")
    app = {
        "@type": "SoftwareApplication",
        "@id": SITE + "#app",
        "name": "chasqui",
        "alternateName": "chasqui-translate",
        "description": m["description"],
        "url": SITE,
        "applicationCategory": "MultimediaApplication",
        "applicationSubCategory": "Real-time speech translation",
        "operatingSystem": "Windows 10, Windows 11",
        "softwareVersion": download.group(1),
        "downloadUrl": "https://github.com/kvothesson/chasqui/" + download.group(0),
        "fileSize": "27 MB",
        "license": "https://opensource.org/licenses/MIT",
        "isAccessibleForFree": True,
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
        "screenshot": SITE + "img/ui-transcript.png",
        "image": SITE + f"img/og-{lang}.png",
        "author": {"@type": "Person", "name": "kvothesson", "url": "https://github.com/kvothesson"},
        "sameAs": [
            "https://github.com/kvothesson/chasqui",
            "https://pypi.org/project/chasqui-translate/",
        ],
    }
    webpage = {
        "@type": "WebPage",
        "@id": url,
        "url": url,
        "name": m["title"],
        "description": m["description"],
        "inLanguage": lang,
        "about": {"@id": SITE + "#app"},
        "primaryImageOfPage": SITE + f"img/og-{lang}.png",
    }
    questions = {
        "@type": "FAQPage",
        "@id": url + "#faq",
        "inLanguage": lang,
        "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faq(page, lang)
        ],
    }
    return {"@context": "https://schema.org", "@graph": [app, webpage, questions]}


def head(page: str, lang: str) -> str:
    m = META[lang]
    a = html.escape
    other = "es" if lang == "en" else "en"
    ld = json.dumps(json_ld(page, lang), ensure_ascii=False, indent=1).replace("</", "<\\/")
    i18n = json.dumps(
        {k: {f: META[k][f] for f in ("title", "description", "alt")} for k in META},
        ensure_ascii=False,
    ).replace("</", "<\\/")
    image = SITE + f"img/og-{lang}.png"
    lines = [
        f"<title>{a(m['title'])}</title>",
        f'<meta name="description" content="{a(m["description"])}">',
        f'<link rel="canonical" href="{URLS[lang]}">',
        f'<link rel="alternate" hreflang="en" href="{URLS["en"]}">',
        f'<link rel="alternate" hreflang="es" href="{URLS["es"]}">',
        f'<link rel="alternate" hreflang="x-default" href="{URLS["en"]}">',
        '<meta property="og:type" content="website">',
        '<meta property="og:site_name" content="chasqui">',
        f'<meta property="og:url" content="{URLS[lang]}">',
        f'<meta property="og:title" content="{a(m["title"])}">',
        f'<meta property="og:description" content="{a(m["description"])}">',
        f'<meta property="og:locale" content="{LOCALES[lang]}">',
        f'<meta property="og:locale:alternate" content="{LOCALES[other]}">',
        f'<meta property="og:image" content="{image}">',
        '<meta property="og:image:width" content="1200">',
        '<meta property="og:image:height" content="630">',
        f'<meta property="og:image:alt" content="{a(m["og_alt"])}">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<script type="application/ld+json">\n{ld}\n</script>',
        f'<script type="application/json" id="i18n">{i18n}</script>',
    ]
    return "\n".join(lines) + "\n"


def _swap(page: str, old: str, new: str, count: int = 1) -> str:
    found = page.count(old)
    if found != count:
        raise SystemExit(f"expected {count}x {old!r} in the page, found {found}")
    return page.replace(old, new)


def build(source: str) -> dict[str, str]:
    """Returns {relative path: content} for both pages, from docs/index.html."""
    if HEAD_RE.search(source) is None:
        raise SystemExit("head markers not found in docs/index.html")
    en = HEAD_RE.sub(lambda mt: mt.group(1) + head(source, "en") + mt.group(2), source, count=1)
    es =HEAD_RE.sub(lambda mt: mt.group(1) + head(source, "es") + mt.group(2), source, count=1)
    es = _swap(es, '<html lang="en" data-lang-auto>', '<html lang="es">')
    es = _swap(es, f'alt="{META["en"]["alt"]}"', f'alt="{META["es"]["alt"]}"')
    es = _swap(es, 'href="favicon.svg"', 'href="../favicon.svg"')
    es = es.replace('="img/', '="../img/')
    return {"index.html": en, "es/index.html": es}


def main() -> int:
    source = (DOCS / "index.html").read_text(encoding="utf-8")
    for rel, content in build(source).items():
        path = DOCS / rel
        path.parent.mkdir(exist_ok=True)
        old = path.read_text(encoding="utf-8") if path.exists() else None
        if old != content:
            path.write_text(content, encoding="utf-8", newline="\n")
            print("wrote", path.relative_to(DOCS.parent))
    return 0


if __name__ == "__main__":
    sys.exit(main())
