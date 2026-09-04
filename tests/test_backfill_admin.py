from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from radar_laboral.app import create_app
from radar_laboral.db import finish_sync_request, list_sync_requests


class BackfillAdminTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            os.environ,
            {
                "RADAR_DATA_DIR": self.tmp.name,
                "RADAR_ADMIN_TOKEN": "test-secret",
                "RADAR_MAX_BACKFILL_DAYS": "366",
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

    def _queue(self, *, download_pdfs: bool = False) -> int:
        payload = {
            "start_date": "2026-07-01",
            "end_date": "2026-07-31",
            "admin_token": "test-secret",
        }
        if download_pdfs:
            payload["download_pdfs"] = "1"
        response = self.client.post("/admin/backfill", data=payload)
        self.assertEqual(response.status_code, 302)
        return int(list_sync_requests()[0]["id"])

    def test_status_renders_enabled_selector_without_exposing_token(self) -> None:
        response = self.client.get("/status")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Traer desde", response.data)
        self.assertIn(b"Clave administrativa", response.data)
        self.assertNotIn(b"test-secret", response.data)

    def test_wrong_token_is_forbidden(self) -> None:
        response = self.client.post(
            "/admin/backfill",
            data={
                "start_date": "2026-07-01",
                "end_date": "2026-07-31",
                "admin_token": "wrong",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(list_sync_requests(), [])

    def test_valid_request_is_queued(self) -> None:
        response = self.client.post(
            "/admin/backfill",
            data={
                "start_date": "2026-07-01",
                "end_date": "2026-07-31",
                "admin_token": "test-secret",
                "download_pdfs": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/status?", response.location)
        rows = list_sync_requests()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["start_date"], "2026-07-01")
        self.assertEqual(rows[0]["end_date"], "2026-07-31")
        self.assertEqual(rows[0]["download_pdfs"], 1)
        self.assertEqual(rows[0]["status"], "pending")

    def test_duplicate_active_request_is_not_queued_twice(self) -> None:
        payload = {
            "start_date": "2026-07-01",
            "end_date": "2026-07-31",
            "admin_token": "test-secret",
        }
        first = self.client.post("/admin/backfill", data=payload)
        second = self.client.post("/admin/backfill", data=payload)
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertIn("created=0", second.location)
        self.assertEqual(len(list_sync_requests()), 1)

    def test_invalid_range_is_rejected_before_queueing(self) -> None:
        response = self.client.post(
            "/admin/backfill",
            data={
                "start_date": "2026-08-01",
                "end_date": "2026-07-01",
                "admin_token": "test-secret",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("sync_error=", response.location)
        self.assertEqual(list_sync_requests(), [])

    def test_range_limit_is_enforced(self) -> None:
        with patch.dict(os.environ, {"RADAR_MAX_BACKFILL_DAYS": "10"}, clear=False):
            response = self.client.post(
                "/admin/backfill",
                data={
                    "start_date": "2026-07-01",
                    "end_date": "2026-07-31",
                    "admin_token": "test-secret",
                },
            )
        self.assertEqual(response.status_code, 302)
        self.assertIn("sync_error=", response.location)
        self.assertEqual(list_sync_requests(), [])

    def test_failed_request_has_retry_button_and_visible_peru_dates(self) -> None:
        request_id = self._queue()
        finish_sync_request(request_id, status="failed", error="temporary source failure")

        response = self.client.get("/status")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Repetir", response.data)
        self.assertIn(f'data-retry-request="{request_id}"'.encode(), response.data)
        self.assertIn(b"01/07/2026", response.data)
        self.assertIn(b"31/07/2026", response.data)
        self.assertNotIn(b"test-secret", response.data)

    def test_retry_failed_request_creates_same_new_request(self) -> None:
        request_id = self._queue(download_pdfs=True)
        finish_sync_request(request_id, status="failed", error="temporary source failure")

        response = self.client.post(
            f"/admin/backfill/retry/{request_id}",
            data={"admin_token": "test-secret"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(f"retried={request_id}", response.location)
        rows = list_sync_requests()
        self.assertEqual(len(rows), 2)
        newest, original = rows
        self.assertEqual(original["id"], request_id)
        self.assertEqual(original["status"], "failed")
        self.assertEqual(newest["status"], "pending")
        self.assertEqual(newest["start_date"], original["start_date"])
        self.assertEqual(newest["end_date"], original["end_date"])
        self.assertEqual(newest["download_pdfs"], original["download_pdfs"])

    def test_retry_requires_admin_token(self) -> None:
        request_id = self._queue()
        finish_sync_request(request_id, status="failed", error="temporary source failure")

        response = self.client.post(
            f"/admin/backfill/retry/{request_id}",
            data={"admin_token": "wrong"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(list_sync_requests()), 1)

    def test_non_failed_request_cannot_be_retried(self) -> None:
        request_id = self._queue()

        response = self.client.post(
            f"/admin/backfill/retry/{request_id}",
            data={"admin_token": "test-secret"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("sync_error=", response.location)
        self.assertEqual(len(list_sync_requests()), 1)


class BackfillAdminDisabledTests(unittest.TestCase):
    def test_unconfigured_admin_token_disables_post(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(
                os.environ,
                {"RADAR_DATA_DIR": tmp, "RADAR_ADMIN_TOKEN": ""},
                clear=False,
            ):
                app = create_app()
                app.config.update(TESTING=True)
                client = app.test_client()
                response = client.post(
                    "/admin/backfill",
                    data={
                        "start_date": "2026-07-01",
                        "end_date": "2026-07-31",
                        "admin_token": "anything",
                    },
                )
                self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
