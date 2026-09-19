from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from .db import connect
from .classifier_gold import VALID_LABELS


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {key: (value or "").strip() for key, value in raw.items() if key is not None}
            for raw in csv.DictReader(handle)
        ]


def load_labeled_sample(path: Path) -> dict[str, dict[str, str]]:
    rows = _read_csv(path)
    if not rows:
        raise ValueError("La muestra etiquetada está vacía")

    result: dict[str, dict[str, str]] = {}
    for line_number, row in enumerate(rows, start=2):
        record_id = row.get("id", "")
        label = row.get("human_label", "")
        if not record_id:
            raise ValueError(f"Fila {line_number} sin id")
        if record_id in result:
            raise ValueError(f"ID duplicado en muestra etiquetada: {record_id}")
        if label not in VALID_LABELS:
            raise ValueError(
                f"human_label inválido en fila {line_number}: {label!r}; "
                "la auditoría requiere la muestra completamente etiquetada"
            )
        result[record_id] = row
    return result


def load_manifest(path: Path) -> dict[str, dict[str, str]]:
    rows = _read_csv(path)
    if not rows:
        raise ValueError("El manifest está vacío")

    result: dict[str, dict[str, str]] = {}
    for line_number, row in enumerate(rows, start=2):
        record_id = row.get("id", "")
        stratum = row.get("sampling_stratum", "")
        if not record_id:
            raise ValueError(f"Manifest fila {line_number} sin id")
        if record_id in result:
            raise ValueError(f"ID duplicado en manifest: {record_id}")
        if stratum not in VALID_LABELS:
            raise ValueError(
                f"sampling_stratum inválido en manifest fila {line_number}: {stratum!r}"
            )
        result[record_id] = row
    return result


def population_counts_from_db() -> dict[str, int]:
    counts = {label: 0 for label in VALID_LABELS}
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT labor_relevance, COUNT(*) AS n
            FROM norms
            WHERE labor_relevance IN ('relevant', 'review', 'not_labor')
            GROUP BY labor_relevance
            """
        ).fetchall()
    for row in rows:
        counts[str(row["labor_relevance"])] = int(row["n"])
    return counts


def _confusion_template() -> dict[str, dict[str, float]]:
    return {
        expected: {predicted: 0.0 for predicted in sorted(VALID_LABELS)}
        for expected in sorted(VALID_LABELS)
    }


def audit_sample(
    labels: dict[str, dict[str, str]],
    manifest: dict[str, dict[str, str]],
    *,
    population_counts: dict[str, int] | None = None,
) -> dict[str, object]:
    label_ids = set(labels)
    manifest_ids = set(manifest)
    if label_ids != manifest_ids:
        missing_manifest = sorted(label_ids - manifest_ids)
        missing_labels = sorted(manifest_ids - label_ids)
        raise ValueError(
            "Muestra y manifest no contienen exactamente los mismos IDs; "
            f"sin manifest={missing_manifest[:5]}, sin etiqueta={missing_labels[:5]}"
        )

    confusion = _confusion_template()
    per_stratum: dict[str, Counter[str]] = {
        stratum: Counter() for stratum in sorted(VALID_LABELS)
    }
    false_negatives: list[str] = []
    false_positives: list[str] = []
    exact_matches = 0

    for record_id in labels:
        expected = labels[record_id]["human_label"]
        predicted = manifest[record_id]["sampling_stratum"]
        confusion[expected][predicted] += 1.0
        per_stratum[predicted][expected] += 1
        if expected == predicted:
            exact_matches += 1
        if expected != "not_labor" and predicted == "not_labor":
            false_negatives.append(record_id)
        if expected == "not_labor" and predicted != "not_labor":
            false_positives.append(record_id)

    total = len(labels)
    labor_total = sum(
        1 for row in labels.values() if row["human_label"] != "not_labor"
    )
    labor_tracked = sum(
        1
        for record_id, row in labels.items()
        if row["human_label"] != "not_labor"
        and manifest[record_id]["sampling_stratum"] != "not_labor"
    )
    tracked_predictions = sum(
        1
        for row in manifest.values()
        if row["sampling_stratum"] != "not_labor"
    )
    tracked_true = sum(
        1
        for record_id, row in manifest.items()
        if row["sampling_stratum"] != "not_labor"
        and labels[record_id]["human_label"] != "not_labor"
    )
    nonlabor_total = total - labor_total
    nonlabor_excluded = sum(
        1
        for record_id, row in labels.items()
        if row["human_label"] == "not_labor"
        and manifest[record_id]["sampling_stratum"] == "not_labor"
    )

    sample_metrics = {
        "total": total,
        "labor_recall": round(labor_tracked / labor_total, 4) if labor_total else 1.0,
        "tracked_precision": (
            round(tracked_true / tracked_predictions, 4)
            if tracked_predictions
            else 1.0
        ),
        "nonlabor_specificity": (
            round(nonlabor_excluded / nonlabor_total, 4)
            if nonlabor_total
            else 1.0
        ),
        "exact_accuracy": round(exact_matches / total, 4) if total else 1.0,
        "false_negatives": len(false_negatives),
        "false_positives": len(false_positives),
    }

    result: dict[str, object] = {
        "sample_size": total,
        "sampling_warning": (
            "La muestra fue estratificada por la predicción original; las métricas "
            "sin ponderar son diagnósticas y no estiman directamente el corpus."
        ),
        "sample_metrics": sample_metrics,
        "sample_confusion_human_by_original_prediction": confusion,
        "sample_human_labels_by_sampling_stratum": {
            stratum: dict(sorted(counter.items()))
            for stratum, counter in sorted(per_stratum.items())
        },
        "false_negative_ids": false_negatives,
        "false_positive_ids": false_positives,
    }

    if population_counts is not None:
        result["population_counts"] = dict(sorted(population_counts.items()))
        result["weighted_estimate"] = weighted_estimate(
            labels,
            manifest,
            population_counts=population_counts,
        )
    return result


def weighted_estimate(
    labels: dict[str, dict[str, str]],
    manifest: dict[str, dict[str, str]],
    *,
    population_counts: dict[str, int],
) -> dict[str, object]:
    sample_counts = Counter(
        row["sampling_stratum"] for row in manifest.values()
    )
    for stratum in VALID_LABELS:
        population = int(population_counts.get(stratum, 0))
        sample = int(sample_counts.get(stratum, 0))
        if population > 0 and sample == 0:
            raise ValueError(
                f"No hay observaciones del estrato {stratum} para ponderar {population} registros"
            )

    weights = {
        stratum: (
            float(population_counts.get(stratum, 0)) / sample_counts[stratum]
            if sample_counts[stratum]
            else 0.0
        )
        for stratum in VALID_LABELS
    }

    confusion = _confusion_template()
    exact = 0.0
    labor_total = 0.0
    labor_tracked = 0.0
    tracked_total = 0.0
    tracked_true = 0.0
    nonlabor_total = 0.0
    nonlabor_excluded = 0.0

    for record_id, manifest_row in manifest.items():
        predicted = manifest_row["sampling_stratum"]
        expected = labels[record_id]["human_label"]
        weight = weights[predicted]
        confusion[expected][predicted] += weight

        if predicted == expected:
            exact += weight
        tracked = predicted != "not_labor"
        expected_labor = expected != "not_labor"

        if expected_labor:
            labor_total += weight
            if tracked:
                labor_tracked += weight
        else:
            nonlabor_total += weight
            if not tracked:
                nonlabor_excluded += weight

        if tracked:
            tracked_total += weight
            if expected_labor:
                tracked_true += weight

    population_total = float(sum(max(0, int(v)) for v in population_counts.values()))
    return {
        "method": "post-stratification by original predicted class",
        "weights": {key: round(value, 6) for key, value in sorted(weights.items())},
        "estimated_labor_recall": (
            round(labor_tracked / labor_total, 4) if labor_total else 1.0
        ),
        "estimated_tracked_precision": (
            round(tracked_true / tracked_total, 4) if tracked_total else 1.0
        ),
        "estimated_nonlabor_specificity": (
            round(nonlabor_excluded / nonlabor_total, 4)
            if nonlabor_total
            else 1.0
        ),
        "estimated_exact_accuracy": (
            round(exact / population_total, 4) if population_total else 1.0
        ),
        "estimated_confusion_human_by_original_prediction": {
            expected: {
                predicted: round(value, 2)
                for predicted, value in sorted(predictions.items())
            }
            for expected, predictions in sorted(confusion.items())
        },
        "note": (
            "Estimación válida bajo el supuesto de que, dentro de cada estrato "
            "de predicción original, la muestra fue aleatoria y representativa."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audita etiquetas humanas frente al estrato original de rules_v4"
    )
    parser.add_argument("labels", type=Path, help="CSV ciego ya etiquetado")
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Sidecar privado generado junto a la muestra",
    )
    parser.add_argument(
        "--population-from-db",
        action="store_true",
        help="Pondera la muestra usando el conteo actual de cada estrato en SQLite",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Guarda el reporte JSON además de imprimirlo",
    )
    args = parser.parse_args()

    labels = load_labeled_sample(args.labels)
    manifest = load_manifest(args.manifest)
    population_counts = population_counts_from_db() if args.population_from_db else None
    report = audit_sample(
        labels,
        manifest,
        population_counts=population_counts,
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print(payload)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
