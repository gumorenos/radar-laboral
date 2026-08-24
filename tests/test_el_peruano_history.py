from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from radar_laboral.collectors.el_peruano_history import _iter_days, backfill
from radar_laboral.coverage import mark_coverage_day


LABOR_RECORD = {
    "id": "elperuano:2600000-1",
    "source": "El Peruano",
    "document_type": "DECRETO SUPREMO",
    "number": "001-2026-TR",
    "title": "Modifican disposiciones sobre teletrabajo",
    "summary": None,
    "publication_date": "2026-08-01",
    "effective_date": None,
    "issuer": "TRABAJO Y PROMOCIÓN DEL EMPLEO",
    "topic": None,
    "status": None,
    "edition": "regular",
    "official_url": "https://busquedas.elperuano.pe/dispositivo/NL/2600000-1",
    "pdf_url": "https://busquedas.elperuano.pe/dispositivo/NL/2600000-1/pdf",
    "pdf_path": None,
    "sha256": None,
    "captured_at": "2026-08-01T12:00:00+00:00",
    "updated_at": "2026-08-01T12:00:00+00:00",
}


class HistoricalBackfillTests(unittest.TestCase):
    def _with_data_dir(self, tmp: str):
        class EnvGuard:
            def __enter__(inner_self):
                inner_self.old = os.environ.get("RADAR_DATA_DIR")
                os.environ["RADAR_DATA_DIR"] = tmp

            def __exit__(inner_self, exc_type, exc, tb):
                if inner_self.old is None:
                    os.environ.pop("RADAR_DATA_DIR", None)
                else:
                    os.environ["RADAR_DATA_DIR"] = inner_self.old

        return EnvGuard()

    def test_iter_days_is_inclusive(self) -> None:
        self.assertEqual(
            list(_iter_days(date(2026, 8, 1), date(2026, 8, 3))),
            [date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3)],
        )

    def test_invalid_range_fails_fast(self) -> None:
        with self.assertRaises(ValueError):
            backfill(date(2026, 8, 2), date(2026, 8, 1), download_pdfs=False)

    def test_backfill_upserts_and_preserves_catalog_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self._with_data_dir(tmp):
            catalog = Path(tmp) / "catalog" / "norms.jsonl"
            with patch(
                "radar_laboral.collectors.el_peruano_history.fetch_day",
                return_value=[dict(LABOR_RECORD)],
            ), patch(
                "radar_laboral.collectors.el_peruano_history.local_today",
                return_value=date(2026, 8, 24),
            ):
                first = backfill(
                    date(2026, 8, 1),
                    date(2026, 8, 1),
                    download_pdfs=False,
                    catalog_path=catalog,
                    page_delay_seconds=0,
                    day_delay_seconds=0,
                )
                second = backfill(
                    date(2026, 8, 1),
                    date(2026, 8, 1),
                    download_pdfs=False,
                    catalog_path=catalog,
                    page_delay_seconds=0,
                    day_delay_seconds=0,
                )

            self.assertEqual(len(first), 1)
            self.assertEqual(len(second), 1)
            item = json.loads(catalog.read_text(encoding="utf-8").strip())
            self.assertEqual(item["id"], LABOR_RECORD["id"])
            self.assertEqual(item["edition"], "regular")
            self.assertEqual(item["labor_relevance"], "relevant")

            db_path = Path(tmp) / "radar_laboral.db"
            with sqlite3.connect(db_path) as conn:
                norm_count = conn.execute("SELECT COUNT(*) FROM norms").fetchone()[0]
                sync_count = conn.execute(
                    "SELECT COUNT(*) FROM sync_runs WHERE source = 'El Peruano histórico' "
                    "AND status = 'success'"
                ).fetchone()[0]
                coverage = conn.execute(
                    """
                    SELECT record_count, relevant_count, review_count, is_complete
                    FROM source_coverage_days
                    WHERE source = 'El Peruano' AND coverage_date = '2026-08-01'
                    """
                ).fetchone()

            self.assertEqual(norm_count, 1)
            self.assertEqual(sync_count, 2)
            self.assertEqual(coverage, (1, 1, 0, 1))

    def test_missing_only_skips_complete_days_and_sleeps_only_between_fetched_days(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self._with_data_dir(tmp):
            mark_coverage_day(date(2026, 8, 2), record_count=5, is_complete=True)
            with patch(
                "radar_laboral.collectors.el_peruano_history.fetch_day",
                return_value=[],
            ) as fetch_mock, patch(
                "radar_laboral.collectors.el_peruano_history.local_today",
                return_value=date(2026, 8, 24),
            ), patch(
                "radar_laboral.collectors.el_peruano_history.time.sleep"
            ) as sleep_mock:
                records = backfill(
                    date(2026, 8, 1),
                    date(2026, 8, 3),
                    download_pdfs=False,
                    catalog_path=Path(tmp) / "catalog" / "norms.jsonl",
                    page_delay_seconds=0,
                    day_delay_seconds=0.5,
                    skip_complete_days=True,
                )

            self.assertEqual(records, [])
            self.assertEqual(
                [call.args[1] for call in fetch_mock.call_args_list],
                [date(2026, 8, 1), date(2026, 8, 3)],
            )
            sleep_mock.assert_called_once_with(0.5)

    def test_missing_only_does_no_source_work_when_entire_range_is_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self._with_data_dir(tmp):
            for day in (date(2026, 8, 1), date(2026, 8, 2)):
                mark_coverage_day(day, record_count=0, is_complete=True)

            with patch(
                "radar_laboral.collectors.el_peruano_history.fetch_day"
            ) as fetch_mock, patch(
                "radar_laboral.collectors.el_peruano_history.time.sleep"
            ) as sleep_mock:
                records = backfill(
                    date(2026, 8, 1),
                    date(2026, 8, 2),
                    download_pdfs=False,
                    catalog_path=Path(tmp) / "catalog" / "norms.jsonl",
                    skip_complete_days=True,
                )

            self.assertEqual(records, [])
            fetch_mock.assert_not_called()
            sleep_mock.assert_not_called()
            with sqlite3.connect(Path(tmp) / "radar_laboral.db") as conn:
                run = conn.execute(
                    "SELECT status, records_seen FROM sync_runs ORDER BY id DESC LIMIT 1"
                ).fetchone()
            self.assertEqual(run, ("success", 0))

    def test_successful_empty_day_is_still_covered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self._with_data_dir(tmp):
            with patch(
                "radar_laboral.collectors.el_peruano_history.fetch_day",
                return_value=[],
            ), patch(
                "radar_laboral.collectors.el_peruano_history.local_today",
                return_value=date(2026, 8, 24),
            ):
                records = backfill(
                    date(2026, 8, 2),
                    date(2026, 8, 2),
                    download_pdfs=False,
                    catalog_path=Path(tmp) / "catalog" / "norms.jsonl",
                    page_delay_seconds=0,
                    day_delay_seconds=0,
                )

            self.assertEqual(records, [])
            with sqlite3.connect(Path(tmp) / "radar_laboral.db") as conn:
                row = conn.execute(
                    "SELECT record_count, is_complete FROM source_coverage_days "
                    "WHERE coverage_date = '2026-08-02'"
                ).fetchone()
            self.assertEqual(row, (0, 1))

    def test_failed_fetch_is_recorded_as_failed_sync_without_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self._with_data_dir(tmp):
            with patch(
                "radar_laboral.collectors.el_peruano_history.fetch_day",
                side_effect=RuntimeError("source unavailable"),
            ):
                with self.assertRaises(RuntimeError):
                    backfill(
                        date(2026, 8, 1),
                        date(2026, 8, 1),
                        download_pdfs=False,
                        catalog_path=Path(tmp) / "catalog" / "norms.jsonl",
                        page_delay_seconds=0,
                        day_delay_seconds=0,
                    )

            with sqlite3.connect(Path(tmp) / "radar_laboral.db") as conn:
                row = conn.execute(
                    "SELECT status, error FROM sync_runs ORDER BY id DESC LIMIT 1"
                ).fetchone()
                table_exists = conn.execute(
                    "SELECT 1 FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'source_coverage_days'"
                ).fetchone()
                coverage_count = (
                    conn.execute("SELECT COUNT(*) FROM source_coverage_days").fetchone()[0]
                    if table_exists
                    else 0
                )

            self.assertEqual(row[0], "failed")
            self.assertIn("source unavailable", row[1])
            self.assertEqual(coverage_count, 0)


if __name__ == "__main__":
    unittest.main()
