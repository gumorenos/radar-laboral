from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from radar_laboral.app import create_app
from radar_laboral.db import (
    claim_next_sync_request,
    enqueue_backfill_request,
    finish_sync_request,
    list_sync_requests,
)


class StatusRetryUiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            os.environ,
            {
                "RADAR_DATA_DIR": self.tmp.name,
                "RADAR_ADMIN_TOKEN": "test-admin-token",
                "RADAR_COVERAGE_DAYS": "3",
                "RADAR_TIMEZONE": "America/Lima",
            },
            clear=False,
        )
        self.env.start()
        self.app = create_app()
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def _failed_request(self) -> int:
        request_id, created = enqueue_backfill_request(
            "2026-09-01",
            "2026-09-03",
            download_pdfs=True,
        )
        self.assertTrue(created)
        claimed = claim_next_sync_request()
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["id"], request_id)
        finish_sync_request(request_id, status="failed", error="fallo sintético")
        return request_id

    def test_failed_request_renders_localized_dates_and_retry_button(self) -> None:
        request_id = self._failed_request()

        response = self.client.get("/status")

        self.assertEqual(response.status_code, 200)
        self.assertIn("01/09/2026 → 03/09/2026".encode(), response.data)
        self.assertIn(f">{request_id}<".encode(), response.data)
        self.assertIn(b">Repetir</button>", response.data)
        self.assertIn(b'data-start-date="2026-09-01"', response.data)
        self.assertIn(b'data-end-date="2026-09-03"', response.data)
        self.assertIn(b'data-download-pdfs="1"', response.data)
        self.assertIn(b"fallo sint", response.data)

    def test_failed_range_can_be_requeued_through_existing_admin_endpoint(self) -> None:
        failed_id = self._failed_request()

        response = self.client.post(
            "/admin/backfill",
            data={
                "start_date": "2026-09-01",
                "end_date": "2026-09-03",
                "download_pdfs": "1",
                "admin_token": "test-admin-token",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        rows = list_sync_requests(10)
        self.assertEqual(len(rows), 2)
        newest = rows[0]
        self.assertNotEqual(newest["id"], failed_id)
        self.assertEqual(newest["status"], "pending")
        self.assertEqual(newest["start_date"], "2026-09-01")
        self.assertEqual(newest["end_date"], "2026-09-03")
        self.assertEqual(newest["download_pdfs"], 1)
        self.assertEqual(rows[1]["status"], "failed")

    def test_retry_still_requires_valid_admin_token(self) -> None:
        self._failed_request()

        response = self.client.post(
            "/admin/backfill",
            data={
                "start_date": "2026-09-01",
                "end_date": "2026-09-03",
                "download_pdfs": "1",
                "admin_token": "wrong-token",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(list_sync_requests(10)), 1)


if __name__ == "__main__":
    unittest.main()
