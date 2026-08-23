from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from radar_laboral.app import create_app
from radar_laboral.db import finish_sync_run, start_sync_run


class AppStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"RADAR_DATA_DIR": self.tmp.name}, clear=False)
        self.env.start()
        self.app = create_app()
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def test_health_endpoint(self) -> None:
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_status_api_reports_latest_sync(self) -> None:
        run_id = start_sync_run("El Peruano")
        finish_sync_run(
            run_id,
            status="success",
            records_seen=3,
            relevant_count=1,
            review_count=1,
            pdf_count=2,
            latest_publication_date="2026-08-23",
        )

        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["last_sync"]["status"], "success")
        self.assertEqual(payload["last_sync"]["records_seen"], 3)
        self.assertIn("stats", payload)

    def test_status_page_renders(self) -> None:
        response = self.client.get("/status")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Estado del Radar", response.data)


if __name__ == "__main__":
    unittest.main()
