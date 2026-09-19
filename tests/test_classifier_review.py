from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from radar_laboral.classifier_review import create_review_app, load_sheet


FIELDNAMES = [
    "id",
    "publication_date",
    "source",
    "document_type",
    "number",
    "title",
    "summary",
    "issuer",
    "official_url",
    "evidence_source",
    "evidence_chars",
    "evidence_text",
    "human_label",
    "human_notes",
]


def _write_sheet(path: Path, rows: list[dict[str, str]], fieldnames: list[str] | None = None) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames or FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


class ClassifierReviewTests(unittest.TestCase):
    def sample_row(self) -> dict[str, str]:
        return {
            "id": "elperuano:test-1",
            "publication_date": "2026-09-19",
            "source": "elperuano",
            "document_type": "DECRETO SUPREMO",
            "number": "001-2026-TR",
            "title": "Regula una materia laboral",
            "summary": "",
            "issuer": "Ministerio de Trabajo y Promoción del Empleo",
            "official_url": "https://busquedas.elperuano.pe/test",
            "evidence_source": "remote_pdf",
            "evidence_chars": "42",
            "evidence_text": "Artículo 1. Se regula una materia laboral.",
            "human_label": "",
            "human_notes": "",
        }

    def test_refuses_model_output_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.csv"
            row = self.sample_row()
            row["current_prediction"] = "relevant"
            _write_sheet(path, [row], FIELDNAMES + ["current_prediction"])
            with self.assertRaisesRegex(ValueError, "no es ciega"):
                load_sheet(path)

    def test_get_renders_blind_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.csv"
            _write_sheet(path, [self.sample_row()])
            app = create_review_app(path)
            client = app.test_client()
            response = client.get("/")
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn("Regula una materia laboral", html)
            self.assertIn("remote_pdf", html)
            self.assertIn("19/09/2026", html)
            self.assertNotIn("current_prediction", html)

    def test_post_saves_label_and_notes_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.csv"
            _write_sheet(path, [self.sample_row()])
            app = create_review_app(path)
            client = app.test_client()
            response = client.post(
                "/label",
                data={
                    "id": "elperuano:test-1",
                    "human_label": "review",
                    "human_notes": "Revisar alcance de la obligación",
                    "index": "0",
                },
            )
            self.assertEqual(response.status_code, 302)
            _, rows = load_sheet(path)
            self.assertEqual(rows[0]["human_label"], "review")
            self.assertEqual(rows[0]["human_notes"], "Revisar alcance de la obligación")

    def test_invalid_label_is_rejected_without_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.csv"
            _write_sheet(path, [self.sample_row()])
            app = create_review_app(path)
            client = app.test_client()
            response = client.post(
                "/label",
                data={
                    "id": "elperuano:test-1",
                    "human_label": "maybe",
                    "human_notes": "",
                    "index": "0",
                },
            )
            self.assertEqual(response.status_code, 400)
            _, rows = load_sheet(path)
            self.assertEqual(rows[0]["human_label"], "")


if __name__ == "__main__":
    unittest.main()
