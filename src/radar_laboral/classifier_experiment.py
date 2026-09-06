from __future__ import annotations

import argparse
import json
from pathlib import Path

from .benchmark import evaluate_cases, load_cases
from .llm_semantic import OpenAICompatibleSemanticScorer
from .semantic import DEFAULT_LOCAL_MODELS, local_scorer


def _summary(name: str, metrics: dict[str, object]) -> dict[str, object]:
    return {
        "name": name,
        "total": metrics["total"],
        "labor_recall": metrics["labor_recall"],
        "tracked_precision": metrics["tracked_precision"],
        "nonlabor_specificity": metrics["nonlabor_specificity"],
        "exact_accuracy": metrics["exact_accuracy"],
        "false_negatives": len(metrics["false_negatives"]),
        "false_positives": len(metrics["false_positives"]),
        "review_cases": len(metrics["review_cases"]),
    }


def run_experiment(
    path: Path,
    *,
    local_models: list[str] | None = None,
    use_llm: bool = False,
) -> dict[str, object]:
    cases = load_cases(path)
    results: list[dict[str, object]] = []

    baseline = evaluate_cases(cases)
    results.append(_summary("rules_v4", baseline))

    for model in local_models or []:
        scorer = local_scorer(model)
        metrics = evaluate_cases(cases, semantic_scorer=scorer)
        results.append(_summary(f"rules_v4+semantic:{model}", metrics))

    if use_llm:
        scorer = OpenAICompatibleSemanticScorer.from_env()
        metrics = evaluate_cases(cases, semantic_scorer=scorer)
        results.append(_summary(f"rules_v4+{scorer.name}", metrics))

    best = sorted(
        results,
        key=lambda row: (
            int(row["false_negatives"]),
            -float(row["labor_recall"]),
            -float(row["tracked_precision"]),
            -float(row["exact_accuracy"]),
        ),
    )[0]
    return {"benchmark": str(path), "results": results, "recommended_by_gate": best["name"]}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compara rules_v4 con señales semánticas locales y LLM opcional"
    )
    parser.add_argument("path", type=Path, help="Benchmark JSONL con etiquetas gold")
    parser.add_argument(
        "--local-model",
        action="append",
        default=[],
        help="Modelo sentence-transformers. Se puede repetir.",
    )
    parser.add_argument(
        "--default-local-models",
        action="store_true",
        help="Prueba E5-small y MiniLM multilingüe definidos por el proyecto",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Prueba RADAR_LLM_MODEL/RADAR_LLM_BASE_URL/RADAR_LLM_API_KEY",
    )
    args = parser.parse_args()
    models = list(args.local_model)
    if args.default_local_models:
        models.extend(model for model in DEFAULT_LOCAL_MODELS if model not in models)
    print(
        json.dumps(
            run_experiment(args.path, local_models=models, use_llm=args.llm),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
