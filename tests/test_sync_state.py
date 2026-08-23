from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from radar_laboral.collectors.el_peruano import cache_pdf, default_catalog_path
from radar_laboral.db import (
    data_dir,
    finish_sync_run,
    init_db,
    latest_sync_run,
    norm_stats,
    start_sync_run,
    upsert_norm,
)


class _FailIfNetworkSession:
    def get(self, *args, **kwargs):
        raise AssertionError("No debería acceder a red cuando el PDF ya está cacheado")


class SyncStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"RADAR_DATA_DIR": self.tmp.name}, clear=False)
        self.env.start()
        init_db()

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def test_sync_run_and_stats(self) -> None:
        record = {
            "id": "test:teletrabajo",
            "source": "El Peruano",
            "document_type": "LEY",
            "number": "99999",
            "title": "Ley que modifica disposiciones sobre teletrabajo",
            "summary": None,
            "publication_date": "2026-08-23",
            "effective_date": None,
            "issuer": "CONGRESO DE LA REPÚBLICA",
            "topic": None,
            "status": None,
            "official_url": "https://busquedas.elperuano.pe/test",
            "pdf_url": None,
            "pdf_path": None,
            "sha256": None,
            "captured_at": "2026-08-23T05:00:00+00:00",
            "updated_at": "2026-08-23T05:00:00+00:00",
        }
        enriched = upsert_norm(record)
        self.assertEqual(enriched["labor_relevance"], "relevant")

        run_id = start_sync_run("El Peruano")
        finish_sync_run(
            run_id,
            status="success",
            records_seen=1,
            relevant_count=1,
            pdf_count=0,
            latest_publication_date="2026-08-23",
        )

        last = latest_sync_run("El Peruano")
        self.assertIsNotNone(last)
        self.assertEqual(last["status"], "success")
        self.assertEqual(last["records_seen"], 1)
        self.assertEqual(last["latest_publication_date"], "2026-08-23")

        stats = norm_stats()
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["relevant"], 1)
        self.assertEqual(stats["pdf_cached"], 0)

    def test_cached_pdf_is_reused_without_network(self) -> None:
        relative = Path("pdfs/elperuano/2026/123-1.pdf")
        pdf = data_dir() / relative
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(b"%PDF-1.4\nradar laboral\n%%EOF\n")

        stored = {
            "id": "elperuano:123-1",
            "source": "El Peruano",
            "document_type": "DECRETO SUPREMO",
            "number": "001-2026-TR",
            "title": "Modifican disposiciones sobre jornada de trabajo",
            "summary": None,
            "publication_date": "2026-08-23",
            "effective_date": None,
            "issuer": "TRABAJO Y PROMOCIÓN DEL EMPLEO",
            "topic": None,
            "status": None,
            "official_url": "https://busquedas.elperuano.pe/dispositivo/NL/123-1",
            "pdf_url": "https://epdoc2.elperuano.pe/test.pdf",
            "pdf_path": relative.as_posix(),
            "sha256": "stored-hash",
            "captured_at": "2026-08-23T05:00:00+00:00",
            "updated_at": "2026-08-23T05:00:00+00:00",
        }
        upsert_norm(stored)

        incoming = dict(stored)
        incoming["pdf_url"] = "https://busquedas.elperuano.pe/dispositivo/NL/123-1/pdf"
        incoming["pdf_path"] = None
        incoming["sha256"] = None

        cache_pdf(_FailIfNetworkSession(), incoming)
        self.assertEqual(incoming["pdf_path"], relative.as_posix())
        self.assertEqual(incoming["pdf_url"], "https://epdoc2.elperuano.pe/test.pdf")
        self.assertEqual(incoming["sha256"], "stored-hash")

    def test_runtime_catalog_path_can_live_in_persistent_storage(self) -> None:
        expected = Path(self.tmp.name) / "catalog" / "norms.jsonl"
        with patch.dict(os.environ, {"RADAR_CATALOG_PATH": str(expected)}, clear=False):
            self.assertEqual(default_catalog_path(), expected.resolve())


if __name__ == "__main__":
    unittest.main()
