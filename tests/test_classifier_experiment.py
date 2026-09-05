from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from radar_laboral.classifier_experiment import run_experiment


class ClassifierExperimentTests(unittest.TestCase):
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
        self.assertEqual(result["recommended_by_gate"], "rules_v4")


if __name__ == "__main__":
    unittest.main()
