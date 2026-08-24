from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date
from unittest.mock import patch

from radar_laboral.db import enqueue_backfill_request, init_db, list_sync_requests
from radar_laboral.sync_worker import process_one_request


class SyncWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"RADAR_DATA_DIR": self.tmp.name}, clear=False)
        self.env.start()
        init_db()

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    @patch("radar_laboral.sync_worker.backfill")
    def test_metadata_request_processes_only_missing_days(self, backfill_mock) -> None:
        backfill_mock.return_value = [{"id": "a"}, {"id": "b"}]
        request_id, _ = enqueue_backfill_request(
            "2026-07-01", "2026-07-03", download_pdfs=False
        )

        self.assertTrue(process_one_request())
        backfill_mock.assert_called_once_with(
            date(2026, 7, 1),
            date(2026, 7, 3),
            download_pdfs=False,
            skip_complete_days=True,
        )
        row = list_sync_requests(1)[0]
        self.assertEqual(row["id"], request_id)
        self.assertEqual(row["status"], "success")
        self.assertIsNone(row["error"])

    @patch("radar_laboral.sync_worker.backfill")
    def test_pdf_request_revalidates_full_range(self, backfill_mock) -> None:
        backfill_mock.return_value = []
        enqueue_backfill_request(
            "2026-07-01", "2026-07-03", download_pdfs=True
        )

        self.assertTrue(process_one_request())
        backfill_mock.assert_called_once_with(
            date(2026, 7, 1),
            date(2026, 7, 3),
            download_pdfs=True,
            skip_complete_days=False,
        )

    @patch("radar_laboral.sync_worker.backfill")
    def test_failure_is_recorded_without_crashing_worker(self, backfill_mock) -> None:
        backfill_mock.side_effect = RuntimeError("fuente temporalmente caída")
        enqueue_backfill_request(
            "2026-07-01", "2026-07-03", download_pdfs=False
        )

        self.assertTrue(process_one_request())
        row = list_sync_requests(1)[0]
        self.assertEqual(row["status"], "failed")
        self.assertIn("RuntimeError", row["error"])
        self.assertIn("fuente temporalmente", row["error"])

    @patch("radar_laboral.sync_worker.backfill")
    def test_returns_false_when_queue_is_empty(self, backfill_mock) -> None:
        self.assertFalse(process_one_request())
        backfill_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
