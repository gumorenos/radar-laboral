from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from radar_laboral.db import (
    claim_next_sync_request,
    enqueue_backfill_request,
    finish_sync_request,
    init_db,
    list_sync_requests,
    recover_running_sync_requests,
)


class SyncRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"RADAR_DATA_DIR": self.tmp.name}, clear=False)
        self.env.start()
        init_db()

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def test_enqueue_deduplicates_identical_active_request(self) -> None:
        first_id, first_created = enqueue_backfill_request(
            "2026-07-01", "2026-08-24", download_pdfs=False
        )
        second_id, second_created = enqueue_backfill_request(
            "2026-07-01", "2026-08-24", download_pdfs=False
        )

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first_id, second_id)
        self.assertEqual(len(list_sync_requests()), 1)

    def test_pdf_choice_is_part_of_request_identity(self) -> None:
        metadata_id, _ = enqueue_backfill_request(
            "2026-07-01", "2026-07-31", download_pdfs=False
        )
        pdf_id, created = enqueue_backfill_request(
            "2026-07-01", "2026-07-31", download_pdfs=True
        )
        self.assertTrue(created)
        self.assertNotEqual(metadata_id, pdf_id)

    def test_claim_and_finish_request(self) -> None:
        request_id, _ = enqueue_backfill_request(
            "2026-07-01", "2026-07-02", download_pdfs=True
        )
        claimed = claim_next_sync_request()
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["id"], request_id)
        self.assertEqual(claimed["status"], "running")
        self.assertEqual(claimed["download_pdfs"], 1)
        self.assertIsNone(claim_next_sync_request())

        finish_sync_request(request_id, status="success")
        row = list_sync_requests(1)[0]
        self.assertEqual(row["status"], "success")
        self.assertIsNotNone(row["finished_at"])

    def test_recover_running_request_requeues_it(self) -> None:
        request_id, _ = enqueue_backfill_request(
            "2026-07-01", "2026-07-02", download_pdfs=False
        )
        claimed = claim_next_sync_request()
        self.assertEqual(claimed["id"], request_id)

        self.assertEqual(recover_running_sync_requests(), 1)
        row = list_sync_requests(1)[0]
        self.assertEqual(row["status"], "pending")
        self.assertIsNone(row["started_at"])
        self.assertIn("reinicio", row["error"])

    def test_completed_range_can_be_enqueued_again(self) -> None:
        first_id, _ = enqueue_backfill_request(
            "2026-07-01", "2026-07-02", download_pdfs=False
        )
        claim_next_sync_request()
        finish_sync_request(first_id, status="success")

        second_id, created = enqueue_backfill_request(
            "2026-07-01", "2026-07-02", download_pdfs=False
        )
        self.assertTrue(created)
        self.assertNotEqual(first_id, second_id)


if __name__ == "__main__":
    unittest.main()
