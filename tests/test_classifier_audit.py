from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from radar_laboral.classifier_audit import (
    audit_sample,
    load_labeled_sample,
    load_manifest,
    population_counts_from_manifest,
    weighted_estimate,
)


class ClassifierAuditTests(unittest.TestCase):
    def test_weighted_estimate_uses_original_stratum_population(self) -> None:
        labels = {
            "a": {"human_label": "relevant"},
            "b": {"human_label": "not_labor"},
            "c": {"human_label": "review"},
        }
        manifest = {
            "a": {"sampling_stratum": "relevant"},
            "b": {"sampling_stratum": "review"},
            "c": {"sampling_stratum": "not_labor"},
        }
        result = weighted_estimate(
            labels,
            manifest,
            population_counts={
                "relevant": 900,
                "review": 90,
                "not_labor": 10,
            },
        )
        self.assertEqual(
            result["weights"],
            {"not_labor": 10.0, "relevant": 900.0, "review": 90.0},
        )
        self.assertAlmostEqual(result["estimated_exact_accuracy"], 0.9)

    def test_manifest_population_snapshot_must_be_consistent(self) -> None:
        manifest = {
            "a": {
                "sampling_stratum": "relevant",
                "stratum_population_count": "100",
            },
            "b": {
                "sampling_stratum": "relevant",
                "stratum_population_count": "101",
            },
            "c": {
                "sampling_stratum": "review",
                "stratum_population_count": "20",
            },
            "d": {
                "sampling_stratum": "not_labor",
                "stratum_population_count": "30",
            },
        }
        with self.assertRaisesRegex(ValueError, "inconsistente"):
            population_counts_from_manifest(manifest)

    def test_audit_rejects_mismatched_ids(self) -> None:
        with self.assertRaisesRegex(ValueError, "mismos IDs"):
            audit_sample(
                {"a": {"human_label": "relevant"}},
                {"b": {"sampling_stratum": "relevant"}},
            )

    def test_loaders_require_complete_gold_and_valid_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            labels_path = Path(tmp) / "labels.csv"
            manifest_path = Path(tmp) / "manifest.csv"

            with labels_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["id", "human_label"],
                )
                writer.writeheader()
                writer.writerow({"id": "a", "human_label": "relevant"})

            with manifest_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "id",
                        "sampling_stratum",
                        "stratum_population_count",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "id": "a",
                        "sampling_stratum": "relevant",
                        "stratum_population_count": "123",
                    }
                )

            labels = load_labeled_sample(labels_path)
            manifest = load_manifest(manifest_path)

        self.assertEqual(labels["a"]["human_label"], "relevant")
        self.assertEqual(manifest["a"]["sampling_stratum"], "relevant")


if __name__ == "__main__":
    unittest.main()
