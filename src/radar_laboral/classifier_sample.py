from __future__ import annotations

import argparse
import csv
import random
from collections import defaultdict
from pathlib import Path

from .db import connect

LABELS = ("relevant", "review", "not_labor")


def stratified_sample(per_class: int, *, seed: int = 20260905) -> list[dict[str, object]]:
    rng = random.Random(seed)
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, publication_date, source, document_type, number, title, summary,
                   issuer, labor_relevance, relevance_reason, classification_score,
                   rule_score, classification_method, official_url, classification_text_excerpt
            FROM norms
            WHERE labor_relevance IN ('relevant', 'review', 'not_labor')
            ORDER BY publication_date, id
            """
        ).fetchall()
    for row in rows:
        groups[str(row["labor_relevance"])].append(dict(row))

    selected: list[dict[str, object]] = []
    for label in LABELS:
        candidates = groups.get(label, [])
        if len(candidates) <= per_class:
            picked = candidates
        else:
            picked = rng.sample(candidates, per_class)
        selected.extend(picked)
    rng.shuffle(selected)
    return selected


def write_label_sheet(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "id",
        "publication_date",
        "source",
        "document_type",
        "number",
        "title",
        "summary",
        "issuer",
        "current_prediction",
        "current_reason",
        "classification_score",
        "rule_score",
        "classification_method",
        "official_url",
        "classification_text_excerpt",
        "human_label",
        "human_notes",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "id": row.get("id"),
                    "publication_date": row.get("publication_date"),
                    "source": row.get("source"),
                    "document_type": row.get("document_type"),
                    "number": row.get("number"),
                    "title": row.get("title"),
                    "summary": row.get("summary"),
                    "issuer": row.get("issuer"),
                    "current_prediction": row.get("labor_relevance"),
                    "current_reason": row.get("relevance_reason"),
                    "classification_score": row.get("classification_score"),
                    "rule_score": row.get("rule_score"),
                    "classification_method": row.get("classification_method"),
                    "official_url": row.get("official_url"),
                    "classification_text_excerpt": row.get("classification_text_excerpt"),
                    "human_label": "",
                    "human_notes": "",
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exporta una muestra estratificada del corpus para etiquetado humano"
    )
    parser.add_argument("output", type=Path)
    parser.add_argument("--per-class", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260905)
    args = parser.parse_args()
    rows = stratified_sample(max(1, args.per_class), seed=args.seed)
    write_label_sheet(args.output, rows)
    print(f"Exportados {len(rows)} registros a {args.output}")


if __name__ == "__main__":
    main()
