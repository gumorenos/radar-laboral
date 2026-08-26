from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from radar_laboral.benchmark import evaluate_cases, load_cases


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "classifier_seed_v1.jsonl"
OFFICIAL_BENCHMARK = ROOT / "benchmarks" / "classifier_official_v2.jsonl"
PDF_BENCHMARK = ROOT / "benchmarks" / "classifier_official_pdf_v1.jsonl"
TOPICS_BENCHMARK = ROOT / "benchmarks" / "classifier_official_topics_v1.jsonl"


class ClassifierBenchmarkTests(unittest.TestCase):
    def test_seed_benchmark_has_no_known_false_negatives(self) -> None:
        cases = load_cases(BENCHMARK)
        metrics = evaluate_cases(cases)

        self.assertGreaterEqual(len(cases), 20)
        self.assertEqual(metrics["false_negatives"], [])
        self.assertEqual(metrics["labor_recall"], 1.0)
        self.assertGreaterEqual(metrics["nonlabor_specificity"], 0.85)

    def test_official_benchmark_protects_recall_and_hard_negatives(self) -> None:
        cases = load_cases(OFFICIAL_BENCHMARK)
        metrics = evaluate_cases(cases)

        self.assertGreaterEqual(len(cases), 20)
        self.assertEqual(metrics["false_negatives"], [])
        self.assertEqual(metrics["labor_recall"], 1.0)
        self.assertGreaterEqual(metrics["nonlabor_specificity"], 0.9)
        self.assertGreaterEqual(metrics["tracked_precision"], 0.9)

    def test_pdf_text_controls_are_not_lost_by_generic_titles(self) -> None:
        cases = load_cases(PDF_BENCHMARK)
        metrics = evaluate_cases(cases)

        self.assertGreaterEqual(len(cases), 5)
        self.assertEqual(metrics["false_negatives"], [])
        self.assertEqual(metrics["labor_recall"], 1.0)
        self.assertGreaterEqual(metrics["strict_relevant_recall"], 0.8)

    def test_priority_topic_controls_remain_visible_and_precise(self) -> None:
        cases = load_cases(TOPICS_BENCHMARK)
        metrics = evaluate_cases(cases)

        self.assertGreaterEqual(len(cases), 9)
        self.assertEqual(metrics["false_negatives"], [])
        self.assertEqual(metrics["labor_recall"], 1.0)
        self.assertGreaterEqual(metrics["strict_relevant_recall"], 0.95)
        self.assertGreaterEqual(metrics["review_exact_recall"], 0.9)
        self.assertGreaterEqual(metrics["exact_accuracy"], 0.9)

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
