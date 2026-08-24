from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from radar_laboral.collectors.el_peruano_search import collect
from radar_laboral.coverage import coverage_summary, is_day_complete


class DailyCoverageCollectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"RADAR_DATA_DIR": self.tmp.name}, clear=False)
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def test_past_empty_day_is_complete_after_successful_collect(self) -> None:
        target = date(2026, 8, 23)
        with patch(
            "radar_laboral.collectors.el_peruano_search.fetch_day", return_value=[]
        ), patch(
            "radar_laboral.collectors.el_peruano_search.local_today",
            return_value=date(2026, 8, 24),
        ):
            records = collect(download_pdfs=False, day=target)

        self.assertEqual(records, [])
        self.assertTrue(is_day_complete(target))

    def test_current_day_is_checked_but_not_complete(self) -> None:
        today = date(2026, 8, 24)
        with patch(
            "radar_laboral.collectors.el_peruano_search.fetch_day", return_value=[]
        ), patch(
            "radar_laboral.collectors.el_peruano_search.local_today", return_value=today
        ):
            collect(download_pdfs=False, day=today)

        self.assertFalse(is_day_complete(today))
        summary = coverage_summary(today, target_days=1)
        self.assertTrue(summary["today_checked"])
        self.assertEqual(summary["today_check"]["record_count"], 0)

    def test_failed_collect_does_not_create_coverage(self) -> None:
        target = date(2026, 8, 23)
        with patch(
            "radar_laboral.collectors.el_peruano_search.fetch_day",
            side_effect=RuntimeError("broken source"),
        ), patch(
            "radar_laboral.collectors.el_peruano_search.local_today",
            return_value=date(2026, 8, 24),
        ):
            with self.assertRaises(RuntimeError):
                collect(download_pdfs=False, day=target)

        db_path = Path(self.tmp.name) / "radar_laboral.db"
        with sqlite3.connect(db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type = 'table' AND name = 'source_coverage_days'"
            ).fetchone()[0]
            if count:
                rows = conn.execute("SELECT COUNT(*) FROM source_coverage_days").fetchone()[0]
            else:
                rows = 0
        self.assertEqual(rows, 0)


if __name__ == "__main__":
    unittest.main()
