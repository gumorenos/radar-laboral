from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from radar_laboral.classifier_gold import load_labeled_rows, write_benchmark
from radar_laboral.classifier_sample import write_label_sheet


class ClassifierGoldWorkflowTests(unittest.TestCase):
    def sample_rows(self) -> list[dict[str, object]]:
        return [
            {
                "id": "elperuano:test-1",
                "publication_date": "2026-01-10",
                "source": "elperuano",
                "document_type": "DECRETO SUPREMO",
                "number": "001-2026-TR",
                "title": "Regula una materia laboral",
                "summary": "Resumen",
                "issuer": "Ministerio de Trabajo y Promoción del Empleo",
                "official_url": "https://example.test/1",
                "classification_text_excerpt": "Texto legal relevante",
                "labor_relevance": "relevant",
                "relevance_reason": "materia laboral específica",
                "classification_score": 0.91,
                "rule_score": 0.91,
                "classification_method": "rules_v4",
            }
        ]

    def test_label_sheet_is_blind_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.csv"
            write_label_sheet(path, self.sample_rows())
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertIn("human_label", rows[0])
            self.assertNotIn("current_prediction", rows[0])
            self.assertNotIn("classification_score", rows[0])

    def test_label_sheet_can_include_model_output_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.csv"
            write_label_sheet(path, self.sample_rows(), include_model_output=True)
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["current_prediction"], "relevant")
            self.assertEqual(rows[0]["classification_method"], "rules_v4")

    def test_unlabeled_rows_fail_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.csv"
            write_label_sheet(path, self.sample_rows())
            with self.assertRaisesRegex(ValueError, "sin human_label"):
                load_labeled_rows(path)
            self.assertEqual(load_labeled_rows(path, allow_incomplete=True), [])

    def test_labeled_csv_converts_to_benchmark_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "labels.csv"
            jsonl_path = Path(tmp) / "gold.jsonl"
            write_label_sheet(csv_path, self.sample_rows())

            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
                fieldnames = list(rows[0].keys())
            rows[0]["human_label"] = "review"
            rows[0]["human_notes"] = "Requiere revisión jurídica"
            with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

            labeled = load_labeled_rows(csv_path)
            write_benchmark(jsonl_path, labeled)
            case = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
            self.assertEqual(case["id"], "elperuano:test-1")
            self.assertEqual(case["expected_relevance"], "review")
            self.assertEqual(case["record"]["title"], "Regula una materia laboral")
            self.assertEqual(case["human_notes"], "Requiere revisión jurídica")

    def test_invalid_human_label_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.csv"
            path.write_text(
                "id,title,human_label\n1,Norma,maybe\n",
                encoding="utf-8-sig",
            )
            with self.assertRaisesRegex(ValueError, "human_label inválido"):
                load_labeled_rows(path)


if __name__ == "__main__":
    unittest.main()
