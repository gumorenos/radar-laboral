from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date
from unittest.mock import patch

from radar_laboral.coverage import coverage_summary, is_day_complete, mark_coverage_day
from radar_laboral.db import init_db


class CoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"RADAR_DATA_DIR": self.tmp.name}, clear=False)
        self.env.start()
        init_db()

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def test_summary_detects_real_gaps_and_compacts_ranges(self) -> None:
        today = date(2026, 8, 24)
        mark_coverage_day(
            date(2026, 8, 20), record_count=20, relevant_count=1, is_complete=True
        )
        mark_coverage_day(date(2026, 8, 22), record_count=0, is_complete=True)
        mark_coverage_day(
            date(2026, 8, 23), record_count=37, review_count=2, is_complete=True
        )

        summary = coverage_summary(today, target_days=4)

        self.assertEqual(summary["window_start"], "2026-08-20")
        self.assertEqual(summary["window_end"], "2026-08-23")
        self.assertEqual(summary["verified_days"], 3)
        self.assertEqual(summary["missing_days"], 1)
        self.assertEqual(summary["coverage_percent"], 75.0)
        self.assertEqual(summary["first_missing"], "2026-08-21")
        self.assertEqual(
            summary["missing_ranges"],
            [{"start": "2026-08-21", "end": "2026-08-21", "days": 1}],
        )

    def test_successful_empty_day_counts_as_complete(self) -> None:
        day = date(2026, 8, 22)
        mark_coverage_day(day, record_count=0, is_complete=True)
        self.assertTrue(is_day_complete(day))

    def test_current_day_check_is_visible_but_not_historical_coverage(self) -> None:
        today = date(2026, 8, 24)
        mark_coverage_day(today, record_count=12, relevant_count=1, is_complete=False)

        summary = coverage_summary(today, target_days=2)

        self.assertEqual(summary["verified_days"], 0)
        self.assertEqual(summary["missing_days"], 2)
        self.assertTrue(summary["today_checked"])
        self.assertEqual(summary["today_check"]["record_count"], 12)
        self.assertFalse(summary["today_check"]["is_complete"])
        self.assertFalse(is_day_complete(today))

    def test_later_historical_check_upgrades_incomplete_day(self) -> None:
        day = date(2026, 8, 23)
        mark_coverage_day(day, record_count=10, is_complete=False)
        self.assertFalse(is_day_complete(day))

        mark_coverage_day(day, record_count=15, relevant_count=2, is_complete=True)
        self.assertTrue(is_day_complete(day))

        summary = coverage_summary(date(2026, 8, 24), target_days=1)
        self.assertEqual(summary["verified_days"], 1)
        self.assertEqual(summary["missing_days"], 0)
        self.assertIsNone(summary["first_missing"])


if __name__ == "__main__":
    unittest.main()
