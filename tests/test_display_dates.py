from __future__ import annotations

import os
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from radar_laboral.app import (
    _display_coverage,
    _display_mapping,
    _format_date_display,
    _format_datetime_display,
)


class DisplayDateTests(unittest.TestCase):
    def test_iso_dates_render_day_month_year(self) -> None:
        self.assertEqual(_format_date_display("2026-09-01"), "01/09/2026")
        self.assertEqual(_format_date_display(date(2025, 9, 27)), "27/09/2025")

    def test_utc_timestamps_render_in_lima_time(self) -> None:
        with patch.dict(os.environ, {"RADAR_TIMEZONE": "America/Lima"}, clear=False):
            self.assertEqual(
                _format_datetime_display("2026-09-01T19:20:04+00:00"),
                "01/09/2026 14:20",
            )
            self.assertEqual(
                _format_datetime_display(datetime(2026, 9, 1, 19, 20, tzinfo=timezone.utc)),
                "01/09/2026 14:20",
            )

    def test_unknown_values_are_not_destroyed(self) -> None:
        self.assertEqual(_format_date_display("fecha pendiente"), "fecha pendiente")
        self.assertEqual(_format_datetime_display("sin hora"), "sin hora")
        self.assertIsNone(_format_date_display(None))

    def test_mapping_formats_only_requested_display_fields(self) -> None:
        raw = {
            "start_date": "2025-09-27",
            "requested_at": "2026-09-01T19:20:04+00:00",
            "status": "failed",
        }
        with patch.dict(os.environ, {"RADAR_TIMEZONE": "America/Lima"}, clear=False):
            display = _display_mapping(
                raw,
                date_fields=("start_date",),
                datetime_fields=("requested_at",),
            )
        self.assertEqual(display["start_date"], "27/09/2025")
        self.assertEqual(display["requested_at"], "01/09/2026 14:20")
        self.assertEqual(display["status"], "failed")
        self.assertEqual(raw["start_date"], "2025-09-27")

    def test_coverage_formats_dates_without_changing_counts(self) -> None:
        raw = {
            "window_start": "2025-08-30",
            "window_end": "2026-08-29",
            "first_missing": "2025-09-27",
            "last_missing": "2026-08-22",
            "verified_days": 37,
            "missing_ranges": [
                {"start": "2025-09-27", "end": "2026-07-21", "days": 298}
            ],
        }
        display = _display_coverage(raw)
        self.assertEqual(display["window_start"], "30/08/2025")
        self.assertEqual(display["window_end"], "29/08/2026")
        self.assertEqual(display["first_missing"], "27/09/2025")
        self.assertEqual(display["missing_ranges"][0]["end"], "21/07/2026")
        self.assertEqual(display["verified_days"], 37)
        self.assertEqual(raw["window_start"], "2025-08-30")


if __name__ == "__main__":
    unittest.main()
