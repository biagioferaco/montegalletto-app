"""Legge gli avvisi AMT sull'ascensore di Montegalletto e scrive docs/status.json.

Uso:
    python scraper/build_status.py                     # scarica dal sito AMT
    python scraper/build_status.py --fixture FILE      # usa un file di avvisi salvato (test)

Solo libreria standard: nessuna dipendenza da installare.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from parser import TZ, parse_post, resolve_open_ended  # noqa: E402

API_URL = (
    "https://www.amt.genova.it/amt/wp-json/wp/v2/posts"
    "?search=montegalletto&per_page=30&_fields=id,date,modified,link,title,content"
)
OUT = Path(__file__).resolve().parent.parent / "docs" / "status.json"

HOURS = {
    "feriale": {"open": "07:10", "close": "19:50"},
    "festivo": {"open": "07:15", "close": "20:55"},
    "frequency_min": 7,
    "source": "https://www.amt.genova.it/amt/trasporto-multimodale/ascensori/",
}


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag, attrs) -> None:
        if tag in ("p", "br", "li", "div"):
            self.parts.append(" ")


def html_to_text(s: str) -> str:
    p = _Text()
    p.feed(s)
    return re.sub(r"\s+", " ", html.unescape("".join(p.parts))).strip()


def fetch_posts() -> list[dict]:
    req = urllib.request.Request(API_URL, headers={"User-Agent": "montegalletto-status/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = json.load(r)
    return [
        {
            "date": p["date"],
            "modified": p["modified"],
            "link": p["link"],
            "title": html_to_text(p["title"]["rendered"]),
            "text": html_to_text(p["content"]["rendered"]),
        }
        for p in raw
    ]


def build(posts: list[dict], now: datetime) -> dict:
    posts = [p for p in posts if "montegalletto" in p["title"].lower()]
    parsed = sorted((parse_post(p) for p in posts), key=lambda x: x.published, reverse=True)
    closures = resolve_open_ended(parsed)
    horizon = now - timedelta(days=1)
    relevant = sorted(
        (c for c in closures if c.end is None or c.end > horizon),
        key=lambda c: c.start,
    )
    review = [
        {"title": x.title, "link": x.link}
        for x in parsed
        if x.needs_review and x.published > now - timedelta(days=30)
    ]

    def news(x) -> dict:
        excerpt = x.text if len(x.text) <= 600 else x.text[:600].rsplit(" ", 1)[0] + "…"
        return {
            "title": x.title,
            "link": x.link,
            "published": x.published.isoformat(),
            "modified": x.modified.isoformat(),
            "text": excerpt,
        }

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "hours": HOURS,
        "closures": [c.to_json() for c in relevant],
        "needs_review": review,
        "news": [news(x) for x in parsed[:5]],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", help="file JSON di avvisi già normalizzati")
    ap.add_argument("--now", help="data/ora ISO da usare come 'adesso' (test)")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    posts = json.loads(Path(args.fixture).read_text("utf-8")) if args.fixture else fetch_posts()
    if not posts:
        print("Nessun avviso ricevuto da AMT: status.json non aggiornato", file=sys.stderr)
        return 1
    now = datetime.fromisoformat(args.now).replace(tzinfo=TZ) if args.now else datetime.now(TZ)
    status = build(posts, now)

    out = Path(args.out)
    out.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"Scritto {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
