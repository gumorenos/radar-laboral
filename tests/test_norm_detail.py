from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from radar_laboral.app import create_app
from radar_laboral.db import connect, upsert_norm
from radar_laboral.relations import list_related_case_law, list_related_norms


def norm_record(norm_id: str, title: str, number: str) -> dict[str, object]:
    return {
        "id": norm_id,
        "source": "El Peruano",
        "document_type": "DECRETO SUPREMO",
        "number": number,
        "title": title,
        "summary": "Sumilla oficial de prueba",
        "publication_date": "2026-08-01",
        "effective_date": "2026-08-02",
        "issuer": "TRABAJO Y PROMOCIÓN DEL EMPLEO",
        "topic": None,
        "status": "vigente",
        "edition": "extraordinary",
        "classification_text_excerpt": "Artículo 1.- Se regulan derechos vinculados al teletrabajo.",
        "official_url": f"https://example.invalid/{norm_id}",
        "pdf_url": f"https://example.invalid/{norm_id}.pdf",
        "pdf_path": None,
        "sha256": "a" * 64,
        "captured_at": "2026-08-01T12:00:00+00:00",
        "updated_at": "2026-08-01T13:00:00+00:00",
    }


class NormDetailTests(unittest.TestCase):
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

    def test_missing_norm_returns_404(self) -> None:
        response = self.client.get("/norm/no-existe")
        self.assertEqual(response.status_code, 404)

    def test_detail_renders_traceability_and_classification(self) -> None:
        upsert_norm(
            norm_record(
                "norm:detail",
                "Regulan teletrabajo para trabajadores del sector privado",
                "001-2026-TR",
            )
        )

        response = self.client.get("/norm/norm:detail")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"001-2026-TR", response.data)
        self.assertIn(b"teletrabajo", response.data)
        self.assertIn(b"Sumilla oficial de prueba", response.data)
        self.assertIn(b"Extraordinaria", response.data)
        self.assertIn(b"SHA-256", response.data)
        self.assertIn(("a" * 64).encode(), response.data)
        self.assertIn(b"Motivo de clasificaci", response.data)
        self.assertIn(b"Auditor", response.data)
        self.assertIn(b"Score combinado", response.data)
        self.assertIn(b"Score de reglas", response.data)
        self.assertIn(b"rules_v4", response.data)
        self.assertIn(b"Evidencia estructurada", response.data)
        self.assertIn(b"specific_labor_topic", response.data)
        self.assertIn(b"Extracto legal usado", response.data)
        self.assertIn(b"Art", response.data)
        self.assertIn(b"Abrir fuente oficial", response.data)
        self.assertIn(b"Abrir PDF", response.data)
        self.assertIn(b"Todav", response.data)

    def test_index_links_title_to_detail(self) -> None:
        upsert_norm(
            norm_record(
                "norm:linked",
                "Regulan teletrabajo enlazado",
                "002-2026-TR",
            )
        )
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'href="/norm/norm:linked"', response.data)

    def test_related_norms_and_case_law_preserve_relation_direction(self) -> None:
        upsert_norm(
            norm_record(
                "norm:base",
                "Regulan teletrabajo base",
                "003-2026-TR",
            )
        )
        upsert_norm(
            norm_record(
                "norm:related",
                "Modifican reglas de teletrabajo relacionadas",
                "004-2026-TR",
            )
        )

        with connect() as conn:
            conn.execute(
                """
                INSERT INTO case_law (
                    id, source, court, document_type, number, docket_number,
                    title, summary, decision_date, publication_date, topic,
                    binding_level, official_url, pdf_url, pdf_path, sha256,
                    captured_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "case:1",
                    "Tribunal Constitucional",
                    "Tribunal Constitucional",
                    "Sentencia",
                    None,
                    "00001-2026-PA/TC",
                    "Criterio sobre teletrabajo",
                    "Sumilla jurisprudencial",
                    "2026-08-10",
                    "2026-08-11",
                    "Teletrabajo",
                    "caso individual",
                    "https://example.invalid/case-1",
                    "https://example.invalid/case-1.pdf",
                    None,
                    None,
                    "2026-08-11T12:00:00+00:00",
                    None,
                ),
            )
            conn.execute(
                """
                INSERT INTO document_relations (
                    from_kind, from_id, to_kind, to_id, relation_type, note, created_at
                ) VALUES ('norm', ?, 'norm', ?, 'amends', ?, ?)
                """,
                ("norm:base", "norm:related", "relación de prueba", "2026-08-12"),
            )
            conn.execute(
                """
                INSERT INTO document_relations (
                    from_kind, from_id, to_kind, to_id, relation_type, note, created_at
                ) VALUES ('case_law', ?, 'norm', ?, 'interprets', ?, ?)
                """,
                ("case:1", "norm:base", "criterio registrado", "2026-08-12"),
            )

        norm_relations = list_related_norms("norm:base")
        case_relations = list_related_case_law("norm:base")
        self.assertEqual(len(norm_relations), 1)
        self.assertEqual(norm_relations[0]["id"], "norm:related")
        self.assertEqual(norm_relations[0]["relation_direction"], "outgoing")
        self.assertEqual(len(case_relations), 1)
        self.assertEqual(case_relations[0]["id"], "case:1")
        self.assertEqual(case_relations[0]["relation_direction"], "incoming")

        response = self.client.get("/norm/norm:base")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"004-2026-TR", response.data)
        self.assertIn(b"Modifica", response.data)
        self.assertIn(b"desde esta norma", response.data)
        self.assertIn(b"00001-2026-PA/TC", response.data)
        self.assertIn(b"Interpreta", response.data)
        self.assertIn(b"hacia esta norma", response.data)
        self.assertIn(b"caso individual", response.data)
        self.assertIn(b"criterio registrado", response.data)


if __name__ == "__main__":
    unittest.main()
