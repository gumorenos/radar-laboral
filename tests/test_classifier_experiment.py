from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from radar_laboral.classifier_experiment import _gate_decision, run_experiment


class ClassifierExperimentTests(unittest.TestCase):
    def test_gate_fails_when_every_candidate_has_false_negatives(self) -> None:
        result = _gate_decision(
            [
                {
                    "name": "a",
                    "false_negatives": 2,
                    "labor_recall": 0.8,
                    "tracked_precision": 0.9,
                    "exact_accuracy": 0.8,
                },
                {
                    "name": "b",
                    "false_negatives": 1,
                    "labor_recall": 0.9,
                    "tracked_precision": 0.8,
                    "exact_accuracy": 0.9,
                },
            ]
        )
        self.assertFalse(result["gate_pass"])
        self.assertIsNone(result["recommended_by_gate"])
        self.assertEqual(result["diagnostic_leader"], "b")

    def test_gate_only_ranks_zero_false_negative_candidates(self) -> None:
        result = _gate_decision(
            [
                {
                    "name": "zero-a",
                    "false_negatives": 0,
                    "labor_recall": 1.0,
                    "tracked_precision": 0.8,
                    "exact_accuracy": 0.8,
                },
                {
                    "name": "zero-b",
                    "false_negatives": 0,
                    "labor_recall": 1.0,
                    "tracked_precision": 0.9,
                    "exact_accuracy": 0.7,
                },
                {
                    "name": "higher-accuracy-but-fn",
                    "false_negatives": 1,
                    "labor_recall": 0.99,
                    "tracked_precision": 0.99,
                    "exact_accuracy": 0.99,
                },
            ]
        )
        self.assertTrue(result["gate_pass"])
        self.assertEqual(result["recommended_by_gate"], "zero-b")

    def test_rules_baseline_runs_without_optional_models(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bench.jsonl"
            cases = [
                {
                    "id": "labor",
                    "expected_relevance": "relevant",
                    "record": {
                        "document_type": "Decreto Supremo",
                        "title": "Regulan la jornada de trabajo y horas extras",
                        "issuer": "Ministerio de Trabajo y Promoción del Empleo",
                    },
                },
                {
                    "id": "admin",
                    "expected_relevance": "not_labor",
                    "record": {
                        "document_type": "Resolución Ministerial",
                        "title": "Autorizan viaje de funcionario",
                        "issuer": "Ministerio de Trabajo y Promoción del Empleo",
                    },
                },
            ]
            path.write_text("\n".join(json.dumps(case) for case in cases), encoding="utf-8")
            result = run_experiment(path)
        self.assertEqual(result["results"][0]["name"], "rules_v4")
        self.assertEqual(result["results"][0]["false_negatives"], 0)
        self.assertTrue(result["gate_pass"])
        self.assertEqual(result["recommended_by_gate"], "rules_v4")


if __name__ == "__main__":
    unittest.main()
