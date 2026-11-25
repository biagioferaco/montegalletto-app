"""Test del parser sugli avvisi AMT reali (tests/fixtures/posts.json).

Esecuzione: python -m unittest discover -s tests
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scraper"))

from parser import parse_post, resolve_open_ended  # noqa: E402

POSTS = json.loads((ROOT / "tests" / "fixtures" / "posts.json").read_text("utf-8"))


def by_date(prefix):
    return next(p for p in POSTS if p["date"].startswith(prefix))


def spans(post):
    fmt = "%Y-%m-%d %H:%M"
    return [(c.start.strftime(fmt), c.end.strftime(fmt) if c.end else None) for c in parse_post(post).closures]


class ParserTest(unittest.TestCase):
    def check(self, date_prefix, expected):
        self.assertEqual(spans(by_date(date_prefix)), expected)

    def test_interval_with_early_restore(self):
        # dalle 14 del 4/11 alle 20 del 5/11, ma "ripristinato alle ore 17.00" il 5/11
        self.check("2026-11-03", [("2026-11-04 14:00", "2026-11-05 17:00")])

    def test_time_then_full_day(self):
        self.check("2026-01-20", [("2026-01-21 19:00", "2026-01-23 00:00")])

    def test_single_full_day(self):
        self.check("2025-12-11", [("2025-12-12 00:00", "2025-12-13 00:00")])

    def test_two_days_shared_month(self):
        self.check("2025-12-09", [("2025-12-10 00:00", "2025-12-12 00:00")])

    def test_same_day_hours(self):
        self.check("2025-12-04", [("2025-12-05 09:00", "2025-12-05 13:00")])
        self.check("2023-07-05", [("2023-07-07 14:00", "2023-07-07 15:30")])

    def test_day_range_without_month_on_first_day(self):
        self.check("2024-12-11", [("2024-12-12 00:00", "2024-12-17 00:00")])
        self.check("2022-09-02", [("2022-09-05 00:00", "2022-09-10 00:00")])

    def test_day_range_across_months(self):
        self.check("2024-09-27", [("2024-09-30 00:00", "2024-10-05 00:00")])
        self.check("2024-06-28", [("2024-07-01 00:00", "2024-08-08 00:00")])

    def test_list_of_days_last_partial(self):
        self.check("2024-11-22", [("2024-11-25 00:00", "2024-11-27 13:00")])
        self.check("2024-10-18", [("2024-10-21 00:00", "2024-10-24 00:00")])
        self.check("2022-05-13", [("2022-05-16 00:00", "2022-05-18 17:00")])

    def test_per_day_modes(self):
        # lun 10 dalle 13.30, mar 11 tutto il giorno, mer 12 fino alle 13.30
        self.check("2022-01-07", [("2022-01-10 13:30", "2022-01-12 13:30")])

    def test_early_closing(self):
        self.check("2024-08-13", [("2024-08-19 18:30", "2024-08-20 00:00")])
        self.check("2022-01-08", [("2022-01-09 13:30", "2022-01-10 00:00")])

    def test_first_run(self):
        self.check("2024-03-03", [("2024-03-05 00:00", "2024-03-06 13:00")])

    def test_multi_day_with_times(self):
        self.check("2024-04-08", [("2024-04-10 07:00", "2024-04-11 21:00")])
        self.check("2023-07-21", [("2023-07-24 13:15", "2023-07-28 13:15")])

    def test_extension_until_date(self):
        self.check("2024-11-27", [("2024-11-27 16:42", "2024-11-30 00:00")])

    def test_open_ended(self):
        self.check("2023-02-15", [("2023-02-15 14:00", None)])
        self.check("2023-02-06", [("2023-02-07 09:00", None)])
        self.check("2023-07-10T10", [("2023-07-10 10:32", None)])

    def test_restore_posts(self):
        for prefix in ["2026-01-22", "2026-01-06", "2025-06-26", "2024-12-16", "2024-11-29", "2023-07-10T13"]:
            with self.subTest(prefix):
                self.assertEqual(parse_post(by_date(prefix)).kind, "restore")
        self.assertEqual(parse_post(by_date("2024-12-16")).restored_at.strftime("%Y-%m-%d"), "2024-12-17")

    def test_open_ended_closed_by_restore(self):
        posts = [parse_post(by_date("2023-07-10T10")), parse_post(by_date("2023-07-10T13"))]
        c = resolve_open_ended(posts)
        self.assertEqual(c[0].end.strftime("%Y-%m-%d %H:%M"), "2023-07-10 13:43")

    def test_month_rollover(self):
        post = {"date": "2025-12-20T10:00:00", "modified": "2025-12-20T10:00:00", "link": "x", "title": "t",
                "text": "Martedì 13 gennaio l'ascensore Montegalletto resterà chiuso per l'intera giornata."}
        self.assertEqual(spans(post), [("2026-01-13 00:00", "2026-01-14 00:00")])

    def test_unknown_wording_is_flagged(self):
        post = {"date": "2026-11-20T10:00:00", "modified": "2026-11-20T10:00:00", "link": "x", "title": "t",
                "text": "L'ascensore Montegalletto resterà chiuso nel prossimo fine settimana."}
        p = parse_post(post)
        self.assertTrue(p.needs_review)
        self.assertEqual(p.closures, [])


if __name__ == "__main__":
    unittest.main()
