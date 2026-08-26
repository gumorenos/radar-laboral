from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from radar_laboral.benchmark import evaluate_cases, load_cases


BENCHMARK = Path(__file__).resolve().parents[1] / "benchmarks" / "classifier_seed_v1.jsonl"


class ClassifierBenchmarkTests(unittest.TestCase):
    def test_seed_benchmark_has_no_known_false_negatives(self) -> None:
        cases = load_cases(BENCHMARK)
        metrics = evaluate_cases(cases)

        self.assertGreaterEqual(len(cases), 20)
        self.assertEqual(metrics["false_negatives"], [])
        self.assertEqual(metrics["labor_recall"], 1.0)
        self.assertGreaterEqual(metrics["nonlabor_specificity"], 0.85)

    def test_benchmark_tracks_reviews_as_visible_not_as_false_negatives(self) -> None:
        metrics = evaluate_cases(
            [
                {
                    "id": "ambiguous-labor",
                    "expected_relevance": "review",
                    "record": {
                        "issuer": "TRABAJO Y PROMOCIÓN DEL EMPLEO",
                        "document_type": "RESOLUCIÓN MINISTERIAL",
                        "title": "Aprueban lineamientos institucionales para el año 2026",
                    },
                }
            ]
        )
        self.assertEqual(metrics["labor_recall"], 1.0)
        self.assertEqual(metrics["expected_review_total"], 1)
        self.assertEqual(metrics["review_exact_recall"], 1.0)
        self.assertEqual(metrics["review_cases"], ["ambiguous-labor"])
        self.assertEqual(metrics["exact_accuracy"], 1.0)

    def test_legacy_expected_labor_is_backward_compatible(self) -> None:
        metrics = evaluate_cases(
            [
                {
                    "id": "legacy-positive",
                    "expected_labor": True,
                    "record": {
                        "issuer": "TRABAJO Y PROMOCIÓN DEL EMPLEO",
                        "document_type": "DECRETO SUPREMO",
                        "title": "Modifican el Reglamento de la Ley del Teletrabajo",
                    },
                },
                {
                    "id": "legacy-negative",
                    "expected_labor": False,
                    "record": {
                        "issuer": "TRABAJO Y PROMOCIÓN DEL EMPLEO",
                        "document_type": "RESOLUCIÓN MINISTERIAL",
                        "title": "Designan Asesor del Despacho Ministerial",
                    },
                },
            ]
        )
        self.assertEqual(metrics["false_negatives"], [])
        self.assertEqual(metrics["false_positives"], [])
        self.assertEqual(metrics["exact_accuracy"], 1.0)

    def test_load_cases_accepts_three_state_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "benchmark.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "id": "review-case",
                        "expected_relevance": "review",
                        "record": {
                            "issuer": "TRABAJO Y PROMOCIÓN DEL EMPLEO",
                            "document_type": "RESOLUCIÓN MINISTERIAL",
                            "title": "Aprueban lineamientos institucionales",
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            cases = load_cases(path)

        self.assertEqual(cases[0]["expected_relevance"], "review")
        self.assertTrue(cases[0]["expected_labor"])

    def test_load_cases_rejects_invalid_expected_relevance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "benchmark.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "id": "bad-case",
                        "expected_relevance": "maybe",
                        "record": {"title": "Texto"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_cases(path)


if __name__ == "__main__":
    unittest.main()
