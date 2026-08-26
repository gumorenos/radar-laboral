from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from radar_laboral.app import create_app
from radar_laboral.db import connect, get_norm, upsert_norm


def _record(
    record_id: str,
    title: str,
    *,
    publication_date: str = "2026-08-20",
    issuer: str = "TRABAJO Y PROMOCIÓN DEL EMPLEO",
) -> dict[str, object]:
    return {
        "id": record_id,
        "source": "El Peruano",
        "document_type": "DECRETO SUPREMO",
        "number": "009-2026-TR",
        "title": title,
        "summary": None,
        "publication_date": publication_date,
        "effective_date": None,
        "issuer": issuer,
        "topic": None,
        "status": None,
        "edition": "regular",
        "official_url": f"https://example.invalid/{record_id}",
        "pdf_url": None,
        "pdf_path": None,
        "sha256": None,
        "captured_at": f"{publication_date}T05:00:00+00:00",
        "updated_at": f"{publication_date}T05:00:00+00:00",
    }


class HrImpactAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            os.environ,
            {
                "RADAR_DATA_DIR": self.tmp.name,
                "RADAR_COVERAGE_DAYS": "3",
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

    def test_norm_list_shows_high_hr_impact_badge(self) -> None:
        upsert_norm(
            _record(
                "impact-ui-high",
                "Decreto Supremo que modifica el Reglamento de la Ley del Teletrabajo",
            )
        )

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Impacto RR.HH.".encode(), response.data)
        self.assertIn(b">Alto<", response.data)
        self.assertIn(b">directo<", response.data)

    def test_norm_detail_shows_operational_analysis_and_disclaimer(self) -> None:
        upsert_norm(
            _record(
                "impact-ui-detail",
                "Decreto Supremo que modifica el Reglamento de la Ley del Teletrabajo",
            )
        )

        response = self.client.get("/norm/impact-ui-detail")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Análisis operativo de RR.HH.".encode(), response.data)
        self.assertIn(b">Alto<", response.data)
        self.assertIn(b">Directo<", response.data)
        self.assertIn("Acción recomendada".encode(), response.data)
        self.assertIn(b"no sustituye la revisi", response.data.lower())
        self.assertIn(b"fuente oficial", response.data.lower())

    def test_not_labor_norm_has_no_derived_hr_impact(self) -> None:
        upsert_norm(
            _record(
                "impact-ui-not-labor",
                "Designan Asesor del Despacho Ministerial",
                issuer="OTRA ENTIDAD",
            )
        )
        norm = get_norm("impact-ui-not-labor")
        self.assertEqual(norm["labor_relevance"], "not_labor")

        listing = self.client.get("/", query_string={"relevance": "not_labor"})
        detail = self.client.get("/norm/impact-ui-not-labor")

        self.assertEqual(listing.status_code, 200)
        self.assertNotIn(b">Sin impacto<", listing.data)
        self.assertIn(b"No se calcula impacto operativo", detail.data)
        with connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM norm_hr_impact WHERE norm_id = ?",
                ("impact-ui-not-labor",),
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_project_is_labeled_potential_not_current_obligation(self) -> None:
        upsert_norm(
            _record(
                "impact-ui-project",
                "Disponen la publicación del proyecto de Decreto Supremo que modifica el Reglamento de la Ley del Teletrabajo",
            )
        )

        response = self.client.get("/norm/impact-ui-project")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b">Potencial<", response.data)
        self.assertIn(b"posible cambio futuro", response.data)
        self.assertIn(b"obligaci", response.data.lower())
        self.assertIn(b"no cambiar procesos", response.data.lower())

    def test_home_assesses_only_visible_page_rows_lazily(self) -> None:
        start = date(2026, 1, 1)
        for index in range(51):
            upsert_norm(
                _record(
                    f"impact-lazy-{index:02d}",
                    f"Decreto Supremo que modifica el Reglamento de la Ley del Teletrabajo {index:02d}",
                    publication_date=(start + timedelta(days=index)).isoformat(),
                )
            )

        with connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM norm_hr_impact").fetchone()[0], 0)

        first = self.client.get("/", query_string={"relevance": "relevant"})
        self.assertEqual(first.status_code, 200)
        with connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM norm_hr_impact").fetchone()[0], 50)

        second = self.client.get("/", query_string={"relevance": "relevant", "page": "2"})
        self.assertEqual(second.status_code, 200)
        with connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM norm_hr_impact").fetchone()[0], 51)


if __name__ == "__main__":
    unittest.main()
