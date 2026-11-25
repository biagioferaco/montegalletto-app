"""Estrae le chiusure dell'ascensore di Montegalletto dagli avvisi AMT.

Gli avvisi sono testo libero in italiano: il parser riconosce le formule che AMT
usa di solito (vedi tests/fixtures/posts.json). Quando non riesce a ricavare
date certe, segnala l'avviso come "da verificare" invece di inventare un orario.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Rome")

MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}
WD = r"(?:lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica)"
MON = "(" + "|".join(MONTHS) + ")"
DATE = rf"(?:{WD} )?(\d{{1,2}}) {MON}"
TIME = r"(\d{1,2})(?:\.(\d{2}))?"
DI = r"(?:di |del )?"

REOPEN_RE = re.compile(
    r"riprend|riprender|tornerà|torna in servizio|ritorna|tornato|ripristinat|riapertura"
    r"|nuovamente in servizio|è in servizio|ripreso servizio|operativo"
)
CLOSURE_WORDS_RE = re.compile(
    r"sospes|sospend|sospender|chius|chiuder|fuori servizio|fermo|intera giornata|inizio a fine servizio"
)
OPEN_ENDED_RE = re.compile(r"seguiranno aggiornamenti|fino al termine delle attività")


@dataclass
class Closure:
    start: datetime
    end: datetime | None  # None = fino a nuova comunicazione
    link: str = ""

    def to_json(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat() if self.end else None,
            "link": self.link,
        }


@dataclass
class ParsedPost:
    title: str
    link: str
    published: datetime
    modified: datetime
    text: str
    kind: str  # "closure" | "restore" | "info"
    closures: list[Closure] = field(default_factory=list)
    restored_at: datetime | None = None
    needs_review: bool = False


# --------------------------------------------------------------------------- helpers

def normalize(text: str) -> str:
    t = text.lower()
    t = t.replace("’", "'").replace("‘", "'").replace(" ", " ")
    for plain, acc in [("lunedi", "lunedì"), ("martedi", "martedì"), ("mercoledi", "mercoledì"),
                       ("giovedi", "giovedì"), ("venerdi", "venerdì")]:
        t = re.sub(rf"\b{plain}\b", acc, t)
    t = re.sub(r"(\d)°", r"\1", t)                       # 1° luglio
    t = re.sub(r"(\d)(" + "|".join(MONTHS) + r")", r"\1 \2", t)  # 11dicembre
    t = re.sub(r"(\d{1,2}):(\d{2})", r"\1.\2", t)         # 13:00 -> 13.00
    t = re.sub(r"\s+", " ", t).strip()
    return _fill_months(t)


def _fill_months(t: str) -> str:
    """'lunedì 21, martedì 22 e mercoledì 23 ottobre' -> ogni giorno con il suo mese."""
    pat = re.compile(rf"\b((?:{WD}|dal|da|al|a) )(\d{{1,2}})(?!\d)(?! {MON})(?!\.\d)")

    def repl(m: re.Match) -> str:
        after = t[m.end():m.end() + 60]
        nxt = re.search(MON, after)
        if not nxt:
            return m.group(0)
        return f"{m.group(1)}{m.group(2)} {nxt.group(1)}"

    return pat.sub(repl, t)


def _mkdate(day: str, month: str, ref: date) -> date:
    m = MONTHS[month]
    d = date(ref.year, m, int(day))
    if d < ref - timedelta(days=60):   # avviso di dicembre che parla di gennaio
        d = date(ref.year + 1, m, int(day))
    return d


def _at(d: date, hh: str | None, mm: str | None) -> datetime:
    return datetime.combine(d, time(int(hh), int(mm or 0)), TZ)


def _day_start(d: date) -> datetime:
    return datetime.combine(d, time(0, 0), TZ)


def _day_end(d: date) -> datetime:
    return _day_start(d + timedelta(days=1))


def _parse_wp_date(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=TZ)


def _sentences(t: str) -> list[str]:
    return [s for s in re.split(r"(?<!\d)\.\s+|\.$", t) if s.strip()]


# --------------------------------------------------------------------------- parsing

def parse_post(post: dict) -> ParsedPost:
    published = _parse_wp_date(post["date"])
    modified = _parse_wp_date(post["modified"])
    ref = published.date()
    full = normalize(post["text"])
    sentences = _sentences(full)

    closure_text = " . ".join(s for s in sentences if not REOPEN_RE.search(s) and not s.startswith("aggiornamento"))
    reopen_text = " . ".join(s for s in sentences if REOPEN_RE.search(s))

    p = ParsedPost(
        title=post["title"], link=post["link"], published=published, modified=modified,
        text=post["text"], kind="info",
    )

    intervals: list[tuple[datetime, datetime | None]] = []
    # per giorno: "full" oppure (start, end) parziale; il parziale vince sul giorno intero
    per_day: dict[date, tuple[datetime, datetime]] = {}
    partial_days: set[date] = set()

    work = closure_text

    def consume(m: re.Match) -> None:
        nonlocal work
        work = work[:m.start()] + " " * (m.end() - m.start()) + work[m.end():]

    rules_interval = [
        # dalle ore 19.00 di mercoledì 21 gennaio e per l'intera giornata di giovedì 22 gennaio
        (rf"dall[ae] (?:ore )?{TIME} {DI}{DATE} e per l'intera giornata {DI}{DATE}",
         lambda g: (_at(_mkdate(g[2], g[3], ref), g[0], g[1]), _day_end(_mkdate(g[4], g[5], ref)))),
        # dalle ore 14.00 di mercoledì 4 novembre alle ore 20.00 di giovedì 5 novembre
        (rf"dall[ae] (?:ore )?{TIME} {DI}{DATE}.{{0,40}}?(?:alle|fino alle) (?:ore )?{TIME} {DI}{DATE}",
         lambda g: (_at(_mkdate(g[2], g[3], ref), g[0], g[1]), _at(_mkdate(g[6], g[7], ref), g[4], g[5]))),
        # dalla prima corsa di martedì 5 marzo alle ore 13.00 di mercoledì 6 marzo
        (rf"dalla prima corsa {DI}{DATE} (?:alle|fino alle) (?:ore )?{TIME} {DI}{DATE}",
         lambda g: (_day_start(_mkdate(g[0], g[1], ref)), _at(_mkdate(g[4], g[5], ref), g[2], g[3]))),
        # a partire dalle ore 14.00 di mercoledì 15 febbraio (... seguiranno aggiornamenti)
        (rf"a partire dall[ae] (?:ore )?{TIME} {DI}{DATE}",
         lambda g: (_at(_mkdate(g[2], g[3], ref), g[0], g[1]), None)),
    ]
    for rx, build in rules_interval:
        for m in re.finditer(rx, work):
            intervals.append(build(m.groups()))
            consume(m)

    # da lunedì 30 settembre a venerdì 4 ottobre / dal 5 al 9 settembre -> giorni interi
    for m in re.finditer(rf"\bda(?:l)? {DATE} (?:a|al|fino a|fino al) {DATE}", work):
        d1, d2 = _mkdate(m.group(1), m.group(2), ref), _mkdate(m.group(3), m.group(4), ref)
        d = d1
        while d <= d2:
            per_day.setdefault(d, (_day_start(d), _day_end(d)))
            d += timedelta(days=1)
        consume(m)

    # continueranno fino a venerdì 29 novembre
    for m in re.finditer(rf"fino a {DATE}", work):
        intervals.append((published, _day_end(_mkdate(m.group(1), m.group(2), ref))))
        consume(m)

    # singole date con eventuale fascia oraria subito dopo
    for sentence in work.split(" . "):
        if not CLOSURE_WORDS_RE.search(sentence) and not re.search(r"dall[ae] (?:ore )?\d", sentence):
            continue
        dates = list(re.finditer(DATE, sentence))
        for i, m in enumerate(dates):
            d = _mkdate(m.group(1), m.group(2), ref)
            stop = dates[i + 1].start() if i + 1 < len(dates) else len(sentence)
            window = sentence[m.end():stop]
            span = _window_span(window, d, sentence)
            if span is None:
                continue
            if span == "full":
                if d not in partial_days:
                    per_day[d] = (_day_start(d), _day_end(d))
            else:
                if span[1] is None:
                    intervals.append(span)
                else:
                    per_day[d] = span
                    partial_days.add(d)

    intervals.extend(per_day.values())

    # sospeso per problemi tecnici, seguiranno aggiornamenti (senza date)
    if not intervals and re.search(r"sospes|sospend", closure_text) and OPEN_ENDED_RE.search(closure_text):
        intervals.append((published, None))

    if intervals:
        p.kind = "closure"
        p.closures = sorted((Closure(s, e, p.link) for s, e in intervals), key=lambda c: c.start)
        _merge_adjacent(p)
        # "Aggiornamento del 5 novembre: servizio ripristinato alle ore 17.00, in anticipo"
        if re.search(r"ripristinat|tornat\w* in servizio", full) and re.search(r"aggiornamento|in anticipo", full):
            t = re.search(rf"ripristinat\w* alle (?:ore )?{TIME}", full)
            restored = _at(modified.date(), t.group(1), t.group(2)) if t else modified
            p.restored_at = restored
            kept = []
            for c in p.closures:
                if c.start >= restored:
                    continue
                if c.end is None or c.end > restored:
                    c.end = restored
                kept.append(c)
            p.closures = kept
    elif REOPEN_RE.search(full):
        p.kind = "restore"
        m = re.search(DATE, reopen_text)
        p.restored_at = published
        if m:
            d = _mkdate(m.group(1), m.group(2), ref)
            if d > published.date():
                p.restored_at = _day_start(d)
    elif CLOSURE_WORDS_RE.search(full):
        p.kind = "closure"
        p.needs_review = True

    return p


def _window_span(window: str, d: date, sentence: str):
    w = window[:260]
    m = re.search(rf"dall[ae] (?:ore )?{TIME} (?:fino )?alle (?:ore )?{TIME}", w)
    if m:
        return (_at(d, m.group(1), m.group(2)), _at(d, m.group(3), m.group(4)))
    m = re.search(rf"dall[ae] (?:ore )?{TIME} fino al termine", w)
    if m:
        return (_at(d, m.group(1), m.group(2)), None)
    m = re.search(rf"dall[ae] (?:ore )?{TIME}", w)
    if m:
        return (_at(d, m.group(1), m.group(2)), _day_end(d))
    m = re.search(rf"fino alle (?:ore )?{TIME}", w)
    if m:
        return (_day_start(d), _at(d, m.group(1), m.group(2)))
    m = re.search(rf"(?:sospender\w* il servizio|chiuder\w*|chiusura\w*) alle (?:ore )?{TIME}", w)
    if m:
        return (_at(d, m.group(1), m.group(2)), _day_end(d))
    if CLOSURE_WORDS_RE.search(sentence):
        return "full"
    return None


def _merge_adjacent(p: ParsedPost) -> None:
    merged: list[Closure] = []
    for c in p.closures:
        if merged and merged[-1].end is not None and c.start <= merged[-1].end:
            last = merged[-1]
            last.end = None if c.end is None else max(last.end, c.end)
        else:
            merged.append(c)
    p.closures = merged


def resolve_open_ended(posts: list[ParsedPost]) -> list[Closure]:
    """Chiude le sospensioni 'fino a nuova comunicazione' con il primo ripristino successivo."""
    posts = sorted(posts, key=lambda x: x.published)
    restores = sorted(x.restored_at for x in posts if x.restored_at)
    out: list[Closure] = []
    for x in posts:
        for c in x.closures:
            if c.end is None:
                later = [r for r in restores if r > c.start]
                if later:
                    c.end = later[0]
            out.append(c)
    return out
