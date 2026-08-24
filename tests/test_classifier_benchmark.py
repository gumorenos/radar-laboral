from __future__ import annotations

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
                    "expected_labor": True,
                    "record": {
                        "issuer": "TRABAJO Y PROMOCIÓN DEL EMPLEO",
                        "document_type": "RESOLUCIÓN MINISTERIAL",
                        "title": "Aprueban lineamientos institucionales para el año 2026",
                    },
                }
            ]
        )
        self.assertEqual(metrics["labor_recall"], 1.0)
        self.assertEqual(metrics["strict_relevant_recall"], 0.0)
        self.assertEqual(metrics["review_cases"], ["ambiguous-labor"])


if __name__ == "__main__":
    unittest.main()
