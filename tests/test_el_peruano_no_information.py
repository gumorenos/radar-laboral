from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from radar_laboral.collectors.el_peruano import CollectorError, collect


class ElPeruanoNoInformationTests(unittest.TestCase):
    def _session_for(self, html: str) -> MagicMock:
        response = MagicMock()
        response.text = html
        response.raise_for_status.return_value = None
        session = MagicMock()
        session.get.return_value = response
        return session

    @patch("radar_laboral.collectors.el_peruano.finish_sync_run")
    @patch("radar_laboral.collectors.el_peruano.start_sync_run", return_value=7)
    @patch("radar_laboral.collectors.el_peruano.init_db")
    @patch("radar_laboral.collectors.el_peruano.requests.Session")
    def test_explicit_no_information_is_successful_empty_sync(
        self,
        session_factory: MagicMock,
        _init_db: MagicMock,
        _start_sync_run: MagicMock,
        finish_sync_run: MagicMock,
    ) -> None:
        session_factory.return_value = self._session_for(
            '<div class="alert">No se encontró información.</div>'
        )

        records = collect(download_pdfs=False, catalog_path=Path("unused.jsonl"))

        self.assertEqual(records, [])
        finish_sync_run.assert_called_once_with(
            7,
            status="success",
            records_seen=0,
            relevant_count=0,
            review_count=0,
            pdf_count=0,
            latest_publication_date=None,
        )

    @patch("radar_laboral.collectors.el_peruano.finish_sync_run")
    @patch("radar_laboral.collectors.el_peruano.start_sync_run", return_value=8)
    @patch("radar_laboral.collectors.el_peruano.init_db")
    @patch("radar_laboral.collectors.el_peruano.requests.Session")
    def test_unrecognized_empty_response_still_fails(
        self,
        session_factory: MagicMock,
        _init_db: MagicMock,
        _start_sync_run: MagicMock,
        finish_sync_run: MagicMock,
    ) -> None:
        session_factory.return_value = self._session_for("<html><body>unexpected markup</body></html>")

        with self.assertRaises(CollectorError):
            collect(download_pdfs=False, catalog_path=Path("unused.jsonl"))

        self.assertEqual(finish_sync_run.call_count, 1)
        args, kwargs = finish_sync_run.call_args
        self.assertEqual(args, (8,))
        self.assertEqual(kwargs["status"], "failed")
        self.assertIn("CollectorError", kwargs["error"])


if __name__ == "__main__":
    unittest.main()
