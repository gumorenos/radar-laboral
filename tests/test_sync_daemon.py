from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import call, patch

from radar_laboral.sync_daemon import _sync_cycle


class SyncDaemonTests(unittest.TestCase):
    def test_cycle_finalizes_yesterday_before_today_when_missing(self) -> None:
        today = date(2026, 8, 24)
        with patch("radar_laboral.sync_daemon.local_today", return_value=today), patch(
            "radar_laboral.sync_daemon.is_day_complete", return_value=False
        ), patch("radar_laboral.sync_daemon.collect", return_value=[]) as collect_mock:
            _sync_cycle(download_pdfs=False)

        self.assertEqual(
            collect_mock.call_args_list,
            [
                call(download_pdfs=False, day=date(2026, 8, 23)),
                call(download_pdfs=False, day=today),
            ],
        )

    def test_cycle_skips_yesterday_when_already_complete(self) -> None:
        today = date(2026, 8, 24)
        with patch("radar_laboral.sync_daemon.local_today", return_value=today), patch(
            "radar_laboral.sync_daemon.is_day_complete", return_value=True
        ), patch("radar_laboral.sync_daemon.collect", return_value=[]) as collect_mock:
            _sync_cycle(download_pdfs=True)

        collect_mock.assert_called_once_with(download_pdfs=True, day=today)

    def test_today_still_runs_if_yesterday_finalization_fails(self) -> None:
        today = date(2026, 8, 24)
        with patch("radar_laboral.sync_daemon.local_today", return_value=today), patch(
            "radar_laboral.sync_daemon.is_day_complete", return_value=False
        ), patch(
            "radar_laboral.sync_daemon.collect",
            side_effect=[RuntimeError("yesterday failed"), []],
        ) as collect_mock:
            _sync_cycle(download_pdfs=False)

        self.assertEqual(collect_mock.call_count, 2)
        self.assertEqual(collect_mock.call_args_list[-1], call(download_pdfs=False, day=today))


if __name__ == "__main__":
    unittest.main()
