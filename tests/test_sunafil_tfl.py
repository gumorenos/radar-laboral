from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from radar_laboral.case_law import get_case_law, upsert_case_law
from radar_laboral.collectors.sunafil_tfl import (
    SOURCE,
    TflCollectorError,
    _binding_level,
    collect,
    parse_detail_html,
    parse_listing_html,
)
from radar_laboral.db import connect, init_db


LISTING_HTML = """
<html><body>
  <article class="card">
    <h3><a href="/institucion/sunafil/normas-legales/6556395-001-2025-sunafil-tfl">Resolución de Sala Plena N.° 001-2025-SUNAFIL-TFL</a></h3>
    <p>Declarar FUNDADO EN PARTE el recurso de revisión interpuesto por CENCOSUD RETAIL PERU S.A.</p>
    <time>10 de marzo de 2025</time>
    <a href="https://cdn.www.gob.pe/uploads/document/file/1/ju20250309.pdf">Descargar</a>
    <a href="/institucion/sunafil/normas-legales/6556395-001-2025-sunafil-tfl">Leer más</a>
  </article>
  <article class="card">
    <h3><a href="/institucion/sunafil/normas-legales/7000000-008-2023-sunafil-tfl">Resolución de Sala Plena N.° 008-2023-SUNAFIL-TFL</a></h3>
    <p>Establecer criterios administrativos interpretativos e integradores de observancia obligatoria.</p>
    <time>9 de mayo de 2023</time>
    <a href="https://cdn.www.gob.pe/uploads/document/file/2/tfl-008.pdf">Descargar</a>
    <a href="/institucion/sunafil/normas-legales/7000000-008-2023-sunafil-tfl">Leer más</a>
  </article>
  <nav><a href="?sheet=2">2</a></nav>
</body></html>
"""

DETAIL_HTML = """
<html><head><meta name="description" content="Detalle oficial SUNAFIL"></head><body>
<main>
  <h2>Resolución de Sala Plena N.° 001-2025-SUNAFIL-TFL</h2>
  <p>10 de marzo de 2025</p>
  <p>Declarar FUNDADO EN PARTE el recurso de revisión interpuesto por CENCOSUD RETAIL PERU S.A. y ESTABLECER como precedentes administrativos de observancia obligatoria los criterios establecidos en los fundamentos 6.15, 6.16 y 6.17.</p>
  <section><span>JU20250309</span><span>PDF</span><a href="https://cdn.www.gob.pe/uploads/document/file/7823349/ju20250309.pdf?v=1">Descargar</a></section>
</main>
</body></html>
"""


def listing_record(resource_id: str = "6556395") -> dict[str, object]:
    return {
        "id": f"sunafil-tfl:{resource_id}",
        "source": SOURCE,
        "court": "Tribunal de Fiscalización Laboral - Sala Plena",
        "document_type": "Resolución de Sala Plena",
        "number": "001-2025-SUNAFIL-TFL",
        "docket_number": None,
        "title": "Resolución de Sala Plena N.° 001-2025-SUNAFIL-TFL",
        "summary": "Resumen corto del listado",
        "decision_date": None,
        "publication_date": "2025-03-10",
        "topic": None,
        "binding_level": None,
        "official_url": f"https://www.gob.pe/institucion/sunafil/normas-legales/{resource_id}-001-2025-sunafil-tfl",
        "pdf_url": "https://cdn.www.gob.pe/uploads/document/file/1/a.pdf",
        "pdf_path": None,
        "sha256": None,
        "captured_at": "2026-08-24T04:00:00+00:00",
        "updated_at": "2026-08-24T04:00:00+00:00",
    }


class SunafilTflParserTests(unittest.TestCase):
    def test_listing_parser_extracts_stable_ids_metadata_and_next_page(self) -> None:
        records, has_next = parse_listing_html(
            LISTING_HTML,
            captured_at="2026-08-24T04:00:00+00:00",
        )
        self.assertTrue(has_next)
        self.assertEqual(len(records), 2)
        current = next(item for item in records if item["id"] == "sunafil-tfl:6556395")
        self.assertEqual(current["number"], "001-2025-SUNAFIL-TFL")
        self.assertEqual(current["publication_date"], "2025-03-10")
        self.assertEqual(current["source"], SOURCE)
        self.assertEqual(current["pdf_url"], "https://cdn.www.gob.pe/uploads/document/file/1/ju20250309.pdf")
        mandatory = next(item for item in records if item["id"] == "sunafil-tfl:7000000")
        self.assertEqual(mandatory["binding_level"], "criterio de observancia obligatoria")

    def test_detail_parser_uses_official_summary_and_explicit_binding_language(self) -> None:
        record = parse_detail_html(
            DETAIL_HTML,
            "https://www.gob.pe/institucion/sunafil/normas-legales/6556395-001-2025-sunafil-tfl",
            captured_at="2026-08-24T04:00:00+00:00",
        )
        self.assertEqual(record["id"], "sunafil-tfl:6556395")
        self.assertEqual(record["publication_date"], "2025-03-10")
        self.assertEqual(record["decision_date"], None)
        self.assertIn("CENCOSUD", record["summary"])
        self.assertEqual(
            record["binding_level"],
            "precedente administrativo de observancia obligatoria",
        )
        self.assertIn("ju20250309.pdf", str(record["pdf_url"]))

    def test_binding_level_never_infers_from_document_type_alone(self) -> None:
        self.assertIsNone(_binding_level("Se declara infundado el recurso de revisión."))
        self.assertEqual(
            _binding_level("Se establecen criterios de observancia obligatoria para la inspección."),
            "criterio de observancia obligatoria",
        )

    def test_detail_requires_recognizable_official_metadata(self) -> None:
        with self.assertRaises(TflCollectorError):
            parse_detail_html(
                "<html><main><p>sin resolución</p></main></html>",
                "https://www.gob.pe/institucion/sunafil/normas-legales/6556395-001-2025-sunafil-tfl",
            )


class SunafilTflCollectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            os.environ,
            {
                "RADAR_DATA_DIR": self.tmp.name,
                "RADAR_CASE_LAW_CATALOG_PATH": str(Path(self.tmp.name) / "catalog" / "case_law.jsonl"),
            },
            clear=False,
        )
        self.env.start()
        init_db()

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def test_collect_fetches_detail_once_then_reuses_stored_metadata(self) -> None:
        preliminary = listing_record()
        detail = dict(preliminary)
        detail["summary"] = "ESTABLECER precedentes administrativos de observancia obligatoria para la prueba."
        detail["binding_level"] = "precedente administrativo de observancia obligatoria"

        with (
            patch("radar_laboral.collectors.sunafil_tfl.fetch_listing_page", return_value=([preliminary], False)),
            patch("radar_laboral.collectors.sunafil_tfl.fetch_detail", return_value=detail) as fetch_detail,
        ):
            first = collect(download_pdfs=False, page_delay_seconds=0, detail_delay_seconds=0)
            second = collect(download_pdfs=False, page_delay_seconds=0, detail_delay_seconds=0)

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(fetch_detail.call_count, 1)
        stored = get_case_law("sunafil-tfl:6556395")
        self.assertEqual(stored["binding_level"], "precedente administrativo de observancia obligatoria")
        self.assertIn("precedentes administrativos", stored["summary"])

        catalog = Path(os.environ["RADAR_CASE_LAW_CATALOG_PATH"])
        lines = catalog.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertIn("sunafil-tfl:6556395", lines[0])

        with connect() as conn:
            runs = conn.execute(
                "SELECT status, records_seen, pdf_count FROM sync_runs WHERE source = ? ORDER BY id",
                (SOURCE,),
            ).fetchall()
        self.assertEqual([tuple(row) for row in runs], [("success", 1, 0), ("success", 1, 0)])

    def test_refresh_details_forces_refetch(self) -> None:
        preliminary = listing_record()
        upsert_case_law(preliminary)
        with (
            patch("radar_laboral.collectors.sunafil_tfl.fetch_listing_page", return_value=([preliminary], False)),
            patch("radar_laboral.collectors.sunafil_tfl.fetch_detail", return_value=preliminary) as fetch_detail,
        ):
            collect(
                download_pdfs=False,
                refresh_details=True,
                page_delay_seconds=0,
                detail_delay_seconds=0,
            )
        fetch_detail.assert_called_once()

    def test_first_empty_listing_is_recorded_as_failure(self) -> None:
        with patch("radar_laboral.collectors.sunafil_tfl.fetch_listing_page", return_value=([], False)):
            with self.assertRaises(TflCollectorError):
                collect(download_pdfs=False, page_delay_seconds=0, detail_delay_seconds=0)

        with connect() as conn:
            row = conn.execute(
                "SELECT status, error FROM sync_runs WHERE source = ? ORDER BY id DESC LIMIT 1",
                (SOURCE,),
            ).fetchone()
        self.assertEqual(row["status"], "failed")
        self.assertIn("no devolvió resoluciones", row["error"])


if __name__ == "__main__":
    unittest.main()
