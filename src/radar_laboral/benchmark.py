from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

from .classifier import classify_labor
from .semantic import E5SentenceTransformerScorer


Case = Mapping[str, object]
Classifier = Callable[[Mapping[str, object]], Mapping[str, object]]


def load_cases(path: Path) -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON inválido en {path}:{line_number}") from exc
        if not isinstance(item, dict) or "record" not in item or "expected_labor" not in item:
            raise ValueError(f"Caso incompleto en {path}:{line_number}")
        cases.append(item)
    return cases


def evaluate_cases(
    cases: Iterable[Case],
    *,
    semantic_scorer=None,
) -> dict[str, object]:
    total = 0
    labor_total = 0
    nonlabor_total = 0
    labor_tracked = 0
    labor_strict = 0
    nonlabor_excluded = 0
    false_negatives: list[str] = []
    false_positives: list[str] = []
    review_cases: list[str] = []
    rows: list[dict[str, object]] = []

    for index, case in enumerate(cases, start=1):
        total += 1
        expected_labor = bool(case["expected_labor"])
        case_id = str(case.get("id") or f"case-{index}")
        record = case["record"]
        if not isinstance(record, Mapping):
            raise ValueError(f"record inválido en {case_id}")

        result = classify_labor(record, semantic_scorer=semantic_scorer)
        predicted = str(result["labor_relevance"])
        tracked = predicted in {"relevant", "review"}

        if predicted == "review":
            review_cases.append(case_id)

        if expected_labor:
            labor_total += 1
            if tracked:
                labor_tracked += 1
            else:
                false_negatives.append(case_id)
            if predicted == "relevant":
                labor_strict += 1
        else:
            nonlabor_total += 1
            if predicted == "not_labor":
                nonlabor_excluded += 1
            else:
                false_positives.append(case_id)

        rows.append(
            {
                "id": case_id,
                "expected_labor": expected_labor,
                "predicted": predicted,
                "classification_score": result.get("classification_score"),
                "rule_score": result.get("rule_score"),
                "semantic_score": result.get("semantic_score"),
                "method": result.get("classification_method"),
            }
        )

    tracked_predictions = labor_tracked + len(false_positives)
    return {
        "total": total,
        "labor_total": labor_total,
        "nonlabor_total": nonlabor_total,
        "labor_recall": round(labor_tracked / labor_total, 4) if labor_total else 1.0,
        "strict_relevant_recall": round(labor_strict / labor_total, 4) if labor_total else 1.0,
        "nonlabor_specificity": round(nonlabor_excluded / nonlabor_total, 4) if nonlabor_total else 1.0,
        "tracked_precision": round(labor_tracked / tracked_predictions, 4) if tracked_predictions else 1.0,
        "false_negatives": false_negatives,
        "false_positives": false_positives,
        "review_cases": review_cases,
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evalúa el clasificador laboral sobre un benchmark JSONL")
    parser.add_argument("path", type=Path, help="Archivo JSONL versionado con casos etiquetados")
    parser.add_argument(
        "--semantic",
        action="store_true",
        help="Activa el backend E5 opcional; requiere instalar radar-laboral[semantic]",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Modelo sentence-transformers; por defecto multilingual-e5-small",
    )
    parser.add_argument(
        "--fail-on-false-negative",
        action="store_true",
        help="Devuelve código 2 si una norma laboral conocida termina como not_labor",
    )
    args = parser.parse_args()

    scorer = None
    if args.semantic:
        scorer = E5SentenceTransformerScorer(**({"model_name": args.model} if args.model else {}))

    metrics = evaluate_cases(load_cases(args.path), semantic_scorer=scorer)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    if args.fail_on_false_negative and metrics["false_negatives"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
