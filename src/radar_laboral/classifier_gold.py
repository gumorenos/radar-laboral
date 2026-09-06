from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

VALID_LABELS = {"relevant", "review", "not_labor"}
RECORD_FIELDS = (
    "publication_date",
    "source",
    "document_type",
    "number",
    "title",
    "summary",
    "issuer",
    "official_url",
    "classification_text_excerpt",
)


def load_labeled_rows(path: Path, *, allow_incomplete: bool = False) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"id", "human_label", "title"}
        missing = required.difference(reader.fieldnames or ())
        if missing:
            raise ValueError(f"Faltan columnas requeridas: {', '.join(sorted(missing))}")

        rows: list[dict[str, str]] = []
        for line_number, raw in enumerate(reader, start=2):
            row = {key: (value or "").strip() for key, value in raw.items() if key is not None}
            label = row.get("human_label", "")
            if not label:
                if allow_incomplete:
                    continue
                raise ValueError(f"Fila {line_number} sin human_label")
            if label not in VALID_LABELS:
                raise ValueError(
                    f"human_label inválido en fila {line_number}: {label!r}; "
                    f"use relevant, review o not_labor"
                )
            if not row.get("id"):
                raise ValueError(f"Fila {line_number} sin id")
            rows.append(row)
    return rows


def to_benchmark_case(row: dict[str, str]) -> dict[str, object]:
    record = {field: row.get(field, "") for field in RECORD_FIELDS if row.get(field, "")}
    case: dict[str, object] = {
        "id": row["id"],
        "expected_relevance": row["human_label"],
        "record": record,
    }
    notes = row.get("human_notes", "")
    if notes:
        case["human_notes"] = notes
    return case


def write_benchmark(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(to_benchmark_case(row), ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convierte una hoja CSV etiquetada por humanos en benchmark JSONL"
    )
    parser.add_argument("input", type=Path, help="CSV producido por classifier-sample")
    parser.add_argument("output", type=Path, help="JSONL gold de salida")
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Omite filas todavía no etiquetadas en vez de fallar",
    )
    args = parser.parse_args()

    rows = load_labeled_rows(args.input, allow_incomplete=args.allow_incomplete)
    if not rows:
        raise SystemExit("No hay filas etiquetadas para exportar")
    write_benchmark(args.output, rows)
    counts = {label: sum(row["human_label"] == label for row in rows) for label in sorted(VALID_LABELS)}
    print(
        f"Exportados {len(rows)} casos gold a {args.output}: "
        + ", ".join(f"{label}={count}" for label, count in counts.items())
    )


if __name__ == "__main__":
    main()
