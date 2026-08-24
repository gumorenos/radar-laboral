from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from radar_laboral.app import create_app
from radar_laboral.case_law import (
    get_case_law,
    list_case_law_filter_options,
    search_case_law,
    upsert_case_law,
)
from radar_laboral.db import connect, upsert_norm
from radar_laboral.relations import list_related_norms_for_case_law


def case_record(
    case_id: str,
    *,
    title: str,
    docket: str,
    decision_date: str,
    court: str = "Tribunal Constitucional",
    document_type: str = "Sentencia",
    topic: str = "Teletrabajo",
    binding_level: str | None = "caso individual",
) -> dict[str, object]:
    return {
        "id": case_id,
        "source": court,
        "court": court,
        "document_type": document_type,
        "number": None,
        "docket_number": docket,
        "title": title,
        "summary": f"Sumilla de {title}",
        "decision_date": decision_date,
        "publication_date": decision_date,
        "topic": topic,
        "binding_level": binding_level,
        "official_url": f"https://example.invalid/{case_id}",
        "pdf_url": f"https://example.invalid/{case_id}.pdf",
        "pdf_path": None,
        "sha256": None,
        "captured_at": f"{decision_date}T12:00:00+00:00",
        "updated_at": None,
    }


def norm_record(norm_id: str) -> dict[str, object]:
    return {
        "id": norm_id,
        "source": "El Peruano",
        "document_type": "DECRETO SUPREMO",
        "number": "001-2026-TR",
        "title": "Regulan teletrabajo para trabajadores",
        "summary": None,
        "publication_date": "2026-08-01",
        "effective_date": None,
        "issuer": "TRABAJO Y PROMOCIÓN DEL EMPLEO",
        "topic": None,
        "status": None,
        "edition": "regular",
        "official_url": f"https://example.invalid/{norm_id}",
        "pdf_url": None,
        "pdf_path": None,
        "sha256": None,
        "captured_at": "2026-08-01T12:00:00+00:00",
        "updated_at": None,
    }


class CaseLawTests(unittest.TestCase):
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

    def test_upsert_search_filters_and_options(self) -> None:
        upsert_case_law(
            case_record(
                "case:1",
                title="Criterio sobre teletrabajo",
                docket="00001-2026-PA/TC",
                decision_date="2026-08-10",
            )
        )
        upsert_case_law(
            case_record(
                "case:2",
                title="Criterio sobre jornada máxima",
                docket="00002-2026-PA/TC",
                decision_date="2026-08-11",
                topic="Jornada y descansos",
                binding_level="precedente vinculante",
            )
        )

        self.assertEqual([row["id"] for row in search_case_law("00001")], ["case:1"])
        self.assertEqual(
            [row["id"] for row in search_case_law(topic="Jornada y descansos")],
            ["case:2"],
        )
        self.assertEqual(
            [row["id"] for row in search_case_law(date_from="2026-08-11", date_to="2026-08-11")],
            ["case:2"],
        )
        options = list_case_law_filter_options()
        self.assertEqual(options["courts"], ["Tribunal Constitucional"])
        self.assertIn("precedente vinculante", options["binding_levels"])
        self.assertIn("Teletrabajo", options["topics"])

        updated = case_record(
            "case:1",
            title="Criterio actualizado sobre teletrabajo",
            docket="00001-2026-PA/TC",
            decision_date="2026-08-10",
        )
        updated["summary"] = None
        upsert_case_law(updated)
        stored = get_case_law("case:1")
        self.assertEqual(stored["title"], "Criterio actualizado sobre teletrabajo")
        self.assertIn("Sumilla de Criterio sobre teletrabajo", stored["summary"])

    def test_library_route_filters_and_detail(self) -> None:
        upsert_case_law(
            case_record(
                "case:route",
                title="Sentencia sobre teletrabajo privado",
                docket="00100-2026-PA/TC",
                decision_date="2026-08-12",
            )
        )
        response = self.client.get(
            "/jurisprudencia",
            query_string={"q": "teletrabajo", "court": "Tribunal Constitucional"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"00100-2026-PA/TC", response.data)
        self.assertIn(b"Sentencia sobre teletrabajo privado", response.data)
        self.assertIn(b"Fuerza / alcance", response.data)

        detail = self.client.get("/jurisprudencia/case:route")
        self.assertEqual(detail.status_code, 200)
        self.assertIn(b"00100-2026-PA/TC", detail.data)
        self.assertIn(b"caso individual", detail.data)
        self.assertIn(b"no presume", detail.data)
        self.assertIn(b"Abrir fuente oficial", detail.data)
        self.assertIn(b"Abrir PDF", detail.data)

        pdf = self.client.get("/jurisprudencia/case:route/pdf")
        self.assertEqual(pdf.status_code, 302)
        self.assertEqual(pdf.location, "https://example.invalid/case:route.pdf")

    def test_case_law_pagination(self) -> None:
        start = date(2026, 1, 1)
        for index in range(52):
            day = (start + timedelta(days=index)).isoformat()
            upsert_case_law(
                case_record(
                    f"case:page:{index:02d}",
                    title=f"Pronunciamiento paginado {index:02d}",
                    docket=f"{index:05d}-2026-PA/TC",
                    decision_date=day,
                )
            )

        first = self.client.get("/jurisprudencia")
        self.assertEqual(first.status_code, 200)
        self.assertIn(b"Pronunciamiento paginado 51", first.data)
        self.assertNotIn(b"Pronunciamiento paginado 01", first.data)
        self.assertIn(b"page=2", first.data)

        second = self.client.get("/jurisprudencia", query_string={"page": "2"})
        self.assertEqual(second.status_code, 200)
        self.assertIn(b"Pronunciamiento paginado 01", second.data)
        self.assertIn(b"Pronunciamiento paginado 00", second.data)
        self.assertNotIn(b"page=3", second.data)

    def test_relation_to_norm_is_bidirectionally_visible(self) -> None:
        upsert_case_law(
            case_record(
                "case:relation",
                title="Interpreta teletrabajo",
                docket="00200-2026-PA/TC",
                decision_date="2026-08-13",
            )
        )
        upsert_norm(norm_record("norm:relation"))
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO document_relations (
                    from_kind, from_id, to_kind, to_id, relation_type, note, created_at
                ) VALUES ('case_law', ?, 'norm', ?, 'interprets', ?, ?)
                """,
                ("case:relation", "norm:relation", "criterio de prueba", "2026-08-14"),
            )

        related = list_related_norms_for_case_law("case:relation")
        self.assertEqual(len(related), 1)
        self.assertEqual(related[0]["id"], "norm:relation")
        self.assertEqual(related[0]["relation_direction"], "outgoing")

        detail = self.client.get("/jurisprudencia/case:relation")
        self.assertEqual(detail.status_code, 200)
        self.assertIn(b"001-2026-TR", detail.data)
        self.assertIn(b"Interpreta", detail.data)
        self.assertIn(b"desde este pronunciamiento", detail.data)
        self.assertIn(b"criterio de prueba", detail.data)

    def test_missing_case_returns_404(self) -> None:
        self.assertEqual(self.client.get("/jurisprudencia/no-existe").status_code, 404)
        self.assertEqual(self.client.get("/jurisprudencia/no-existe/pdf").status_code, 404)


if __name__ == "__main__":
    unittest.main()
