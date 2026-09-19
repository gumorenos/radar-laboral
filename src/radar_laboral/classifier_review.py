from __future__ import annotations

import argparse
import csv
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Iterable

from flask import Flask, abort, redirect, render_template_string, request, url_for

VALID_LABELS = ("relevant", "review", "not_labor")
PROHIBITED_COLUMNS = {
    "current_prediction",
    "current_reason",
    "classification_score",
    "rule_score",
    "classification_method",
    "classification_text_excerpt",
}

PAGE_TEMPLATE = r"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Radar Laboral · Revisión ciega</title>
  <style>
    :root { color-scheme: light dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
    body { margin: 0; background: #f4f5f7; color: #191b1f; }
    main { max-width: 980px; margin: 0 auto; padding: 28px 20px 60px; }
    .top { display:flex; justify-content:space-between; gap:16px; align-items:center; margin-bottom:18px; }
    .eyebrow { color:#626975; font-size:.82rem; text-transform:uppercase; letter-spacing:.07em; }
    h1 { font-size:1.55rem; margin:.2rem 0 0; line-height:1.25; }
    .progress { min-width:210px; text-align:right; }
    progress { width:100%; height:10px; accent-color:#243c5a; }
    .card { background:white; border:1px solid #dde0e5; border-radius:14px; padding:22px; box-shadow:0 3px 14px rgba(0,0,0,.04); }
    .meta { display:flex; flex-wrap:wrap; gap:8px 14px; color:#555e6a; font-size:.92rem; margin:12px 0 18px; }
    .source { display:inline-block; padding:4px 9px; border-radius:999px; background:#eef1f4; font-size:.78rem; }
    .evidence { white-space:pre-wrap; line-height:1.55; max-height:46vh; overflow:auto; padding:16px; background:#f7f8fa; border-radius:10px; border:1px solid #e4e6ea; }
    .actions { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin:18px 0 12px; }
    button { border:1px solid #b8bec7; border-radius:9px; padding:12px 10px; font-weight:650; background:#fff; cursor:pointer; }
    button:hover { background:#f0f2f5; }
    button.primary { border-color:#243c5a; }
    textarea { width:100%; box-sizing:border-box; min-height:76px; resize:vertical; padding:10px; border:1px solid #c9ced6; border-radius:9px; font:inherit; }
    nav { display:flex; justify-content:space-between; margin-top:16px; gap:10px; }
    nav a, .official { color:#284d78; text-decoration:none; }
    nav a:hover, .official:hover { text-decoration:underline; }
    .done { text-align:center; padding:60px 20px; }
    .hint { color:#6d7480; font-size:.84rem; }
    @media (prefers-color-scheme:dark) {
      body { background:#111317; color:#eceff3; }
      .card { background:#191c21; border-color:#30353d; }
      .evidence { background:#12151a; border-color:#30353d; }
      button { background:#1d2127; color:#eceff3; border-color:#4a515c; }
      button:hover { background:#282d35; }
      textarea { background:#12151a; color:#eceff3; border-color:#4a515c; }
      .source { background:#2a3038; }
      nav a, .official { color:#89b9ef; }
    }
  </style>
</head>
<body>
<main>
  {% if done %}
  <div class="card done">
    <div class="eyebrow">Benchmark humano</div>
    <h1>Etiquetado completo</h1>
    <p>{{ labeled }} de {{ total }} casos tienen etiqueta humana.</p>
    <p class="hint">El CSV ya puede convertirse con radar-laboral-classifier-gold.</p>
  </div>
  {% else %}
  <div class="top">
    <div>
      <div class="eyebrow">Revisión ciega · caso {{ index + 1 }} de {{ total }}</div>
      <h1>{{ row.title or "(sin título)" }}</h1>
    </div>
    <div class="progress">
      <div>{{ labeled }}/{{ total }} etiquetados</div>
      <progress value="{{ labeled }}" max="{{ total }}"></progress>
    </div>
  </div>

  <div class="card">
    <div class="meta">
      <span>{{ display_date }}</span>
      <span>{{ row.document_type }}</span>
      <span>{{ row.number }}</span>
      <span>{{ row.issuer }}</span>
      <span class="source">{{ row.evidence_source or "sin evidencia enriquecida" }} · {{ row.evidence_chars or "0" }} chars</span>
    </div>

    {% if row.official_url %}
      <p><a class="official" href="{{ row.official_url }}" target="_blank" rel="noopener noreferrer">Abrir fuente oficial ↗</a></p>
    {% endif %}

    <div class="evidence">{{ row.evidence_text or row.summary or row.title }}</div>

    <form method="post" action="{{ url_for('save_label') }}">
      <input type="hidden" name="id" value="{{ row.id }}">
      <input type="hidden" name="index" value="{{ index }}">
      <div class="actions">
        <button class="primary" type="submit" name="human_label" value="relevant" title="Atajo: 1">1 · Relevant</button>
        <button class="primary" type="submit" name="human_label" value="review" title="Atajo: 2">2 · Review</button>
        <button class="primary" type="submit" name="human_label" value="not_labor" title="Atajo: 3">3 · Not labor</button>
      </div>
      <label for="notes">Notas opcionales</label>
      <textarea id="notes" name="human_notes" placeholder="Motivo o ambigüedad relevante">{{ row.human_notes }}</textarea>
    </form>

    <nav>
      {% if index > 0 %}<a href="{{ url_for('home', index=index-1) }}">← Anterior</a>{% else %}<span></span>{% endif %}
      <a href="{{ url_for('home', index=next_unlabeled) }}">Siguiente sin etiquetar →</a>
    </nav>
    <p class="hint">El guardado es inmediato en el CSV. Atajos: 1 relevant · 2 review · 3 not_labor.</p>
  </div>

  <script>
    const form = document.querySelector("form");
    document.addEventListener("keydown", (event) => {
      if (event.target && ["TEXTAREA","INPUT"].includes(event.target.tagName)) return;
      const map = {"1":"relevant","2":"review","3":"not_labor"};
      if (!map[event.key]) return;
      const button = form.querySelector('button[value="' + map[event.key] + '"]');
      if (button) button.click();
    });
  </script>
  {% endif %}
</main>
</body>
</html>"""


def _display_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        return value or ""
    return parsed.strftime("%d/%m/%Y")


def load_sheet(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or ())
        required = {"id", "title", "human_label", "human_notes"}
        missing = required.difference(fieldnames)
        if missing:
            raise ValueError(f"Faltan columnas requeridas: {', '.join(sorted(missing))}")
        leaked = PROHIBITED_COLUMNS.intersection(fieldnames)
        if leaked:
            raise ValueError(
                "La hoja no es ciega; contiene columnas del modelo: "
                + ", ".join(sorted(leaked))
            )
        rows = [
            {key: value or "" for key, value in raw.items() if key is not None}
            for raw in reader
        ]

    ids = [row["id"].strip() for row in rows]
    if not rows:
        raise ValueError("La hoja no contiene casos")
    if any(not item for item in ids):
        raise ValueError("La hoja contiene IDs vacíos")
    if len(ids) != len(set(ids)):
        raise ValueError("La hoja contiene IDs duplicados")

    invalid = sorted(
        {
            row["human_label"].strip()
            for row in rows
            if row["human_label"].strip() and row["human_label"].strip() not in VALID_LABELS
        }
    )
    if invalid:
        raise ValueError("Etiquetas humanas inválidas: " + ", ".join(invalid))
    return fieldnames, rows


def _atomic_write(path: Path, fieldnames: Iterable[str], rows: list[dict[str, str]]) -> None:
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _next_unlabeled(rows: list[dict[str, str]], start: int) -> int:
    if not rows:
        return 0
    for offset in range(1, len(rows) + 1):
        candidate = (start + offset) % len(rows)
        if not rows[candidate].get("human_label", "").strip():
            return candidate
    return min(start + 1, len(rows) - 1)


def create_review_app(csv_path: Path) -> Flask:
    path = csv_path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)

    # Validate before starting the local server. Data is re-read on every request
    # so edits are immediately durable and a restart resumes where it stopped.
    load_sheet(path)

    app = Flask(__name__)

    @app.get("/")
    def home():
        _, rows = load_sheet(path)
        total = len(rows)
        labeled = sum(bool(row["human_label"].strip()) for row in rows)

        if labeled == total:
            return render_template_string(
                PAGE_TEMPLATE,
                done=True,
                labeled=labeled,
                total=total,
            )

        try:
            index = int(request.args.get("index", ""))
        except ValueError:
            index = -1

        if not 0 <= index < total:
            index = next(
                (i for i, row in enumerate(rows) if not row["human_label"].strip()),
                0,
            )

        row = rows[index]
        return render_template_string(
            PAGE_TEMPLATE,
            done=False,
            row=row,
            index=index,
            total=total,
            labeled=labeled,
            display_date=_display_date(row.get("publication_date", "")),
            next_unlabeled=_next_unlabeled(rows, index),
        )

    @app.post("/label")
    def save_label():
        record_id = (request.form.get("id") or "").strip()
        label = (request.form.get("human_label") or "").strip()
        notes = request.form.get("human_notes") or ""
        if label not in VALID_LABELS:
            abort(400, "Etiqueta inválida")

        fieldnames, rows = load_sheet(path)
        match_index = next(
            (i for i, row in enumerate(rows) if row["id"].strip() == record_id),
            None,
        )
        if match_index is None:
            abort(404, "Caso no encontrado")

        rows[match_index]["human_label"] = label
        rows[match_index]["human_notes"] = notes.strip()
        _atomic_write(path, fieldnames, rows)

        next_index = _next_unlabeled(rows, match_index)
        return redirect(url_for("home", index=next_index))

    return app


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Abre una interfaz local para etiquetar una muestra ciega"
    )
    parser.add_argument("csv", type=Path, help="CSV ciego producido por classifier-sample")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit(
            "Por seguridad, classifier-review solo escucha en localhost. "
            "Use 127.0.0.1, localhost o ::1."
        )

    app = create_review_app(args.csv)
    print(f"Revisión ciega: http://{args.host}:{args.port}")
    print(f"CSV: {args.csv.expanduser().resolve()}")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
