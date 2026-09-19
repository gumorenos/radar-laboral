from __future__ import annotations

import argparse
import csv
import random
import time
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from .db import connect, data_dir
from .legal_text import extract_pdf_excerpt, normalize_pdf_text, select_legal_excerpt

LABELS = ("relevant", "review", "not_labor")
DEFAULT_EVIDENCE_MAX_CHARS = 6000
DEFAULT_REQUEST_TIMEOUT = 20.0
DEFAULT_OFFICIAL_DELAY_SECONDS = 0.2
DEFAULT_REMOTE_PDF_MAX_BYTES = 16 * 1024 * 1024
ALLOWED_OFFICIAL_HOST_SUFFIX = ".elperuano.pe"


def _sample_select_sql(where_clause: str = "") -> str:
    return f"""
        SELECT id, publication_date, source, document_type, number, title, summary,
               issuer, labor_relevance, relevance_reason, classification_score,
               rule_score, classification_method, official_url, classification_text_excerpt,
               pdf_url, pdf_path
        FROM norms
        {where_clause}
    """


def stratified_sample(per_class: int, *, seed: int = 20260905) -> list[dict[str, object]]:
    rng = random.Random(seed)
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    with connect() as conn:
        rows = conn.execute(
            _sample_select_sql(
                "WHERE labor_relevance IN ('relevant', 'review', 'not_labor') "
                "ORDER BY publication_date, id"
            )
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


def sample_ids_from_csv(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if "id" not in (reader.fieldnames or ()):
            raise ValueError("El CSV de muestra no contiene columna id")
        ids = [(row.get("id") or "").strip() for row in reader]
    ids = [item for item in ids if item]
    if not ids:
        raise ValueError("El CSV de muestra no contiene IDs utilizables")
    if len(ids) != len(set(ids)):
        raise ValueError("El CSV de muestra contiene IDs duplicados")
    return ids


def sample_by_ids(ids: list[str]) -> list[dict[str, object]]:
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    with connect() as conn:
        rows = conn.execute(
            _sample_select_sql(f"WHERE id IN ({placeholders})"),
            ids,
        ).fetchall()
    by_id = {str(row["id"]): dict(row) for row in rows}
    missing = [item for item in ids if item not in by_id]
    if missing:
        preview = ", ".join(missing[:5])
        suffix = "..." if len(missing) > 5 else ""
        raise ValueError(f"No se encontraron {len(missing)} IDs de la muestra: {preview}{suffix}")
    return [by_id[item] for item in ids]


def _resolved_pdf_path(raw_path: object) -> Path | None:
    if not raw_path:
        return None
    path = Path(str(raw_path))
    if not path.is_absolute():
        path = data_dir() / path
    return path


def _official_page_excerpt(
    session: requests.Session,
    url: str,
    *,
    timeout: float,
    max_chars: int,
) -> str | None:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    root = soup.find("article") or soup.find("main")
    if root is None:
        description = soup.find("meta", attrs={"name": "description"})
        description_text = ""
        if description is not None:
            description_text = str(description.get("content") or "").strip()
        body = soup.body or soup
        text = "\n".join(
            part for part in (description_text, body.get_text("\n", strip=True)) if part
        )
    else:
        text = root.get_text("\n", strip=True)

    cleaned = normalize_pdf_text(text)
    if not cleaned:
        return None
    return select_legal_excerpt(cleaned, max_chars=max_chars)



def _allowed_official_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "elperuano.pe" or host.endswith(ALLOWED_OFFICIAL_HOST_SUFFIX)


def _pdf_excerpt_from_bytes(payload: bytes, *, max_chars: int) -> str | None:
    if not payload.startswith(b"%PDF"):
        return None
    try:
        reader = PdfReader(BytesIO(payload))
    except Exception:
        return None

    pages: list[str] = []
    for page in reader.pages[:6]:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            pages.append(text)
    if not pages:
        return None
    return select_legal_excerpt("\n".join(pages), max_chars=max_chars)


def _pdf_links_from_html(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[str] = []
    for tag in soup.find_all(["a", "iframe", "embed", "object", "source"]):
        for attr in ("href", "src", "data"):
            raw = tag.get(attr)
            if not raw:
                continue
            url = urljoin(base_url, str(raw).strip())
            if _allowed_official_url(url):
                path = urlparse(url).path.lower()
                query = urlparse(url).query.lower()
                host = (urlparse(url).hostname or "").lower()
                if (
                    path.endswith(".pdf")
                    or "vistanl" in path
                    or "descarga" in path
                    or "referencias=" in query
                    or host.startswith("epdoc")
                ):
                    candidates.append(url)

    unique: list[str] = []
    seen: set[str] = set()
    for url in candidates:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def _remote_pdf_excerpt(
    session: requests.Session,
    row: dict[str, object],
    *,
    timeout: float,
    max_chars: int,
    max_bytes: int = DEFAULT_REMOTE_PDF_MAX_BYTES,
) -> str | None:
    official_url = str(row.get("official_url") or "").strip()
    pdf_url = str(row.get("pdf_url") or "").strip()

    queue: list[str] = []
    for candidate in (pdf_url, official_url.rstrip("/") + "/pdf" if official_url else ""):
        if candidate and candidate not in queue:
            queue.append(candidate)

    seen: set[str] = set()
    while queue and len(seen) < 8:
        url = queue.pop(0)
        if url in seen or not _allowed_official_url(url):
            continue
        seen.add(url)
        try:
            response = session.get(url, timeout=timeout, allow_redirects=True)
            response.raise_for_status()
        except requests.RequestException:
            continue

        final_url = str(getattr(response, "url", url) or url)
        if not _allowed_official_url(final_url):
            continue

        payload = bytes(getattr(response, "content", b"") or b"")
        if payload and len(payload) <= max_bytes:
            excerpt = _pdf_excerpt_from_bytes(payload, max_chars=max_chars)
            if excerpt:
                return excerpt

        content_type = str(getattr(response, "headers", {}).get("content-type", "")).lower()
        if payload and ("html" in content_type or payload.lstrip().startswith(b"<")):
            try:
                html = payload.decode(getattr(response, "encoding", None) or "utf-8", errors="replace")
            except Exception:
                html = ""
            for candidate in _pdf_links_from_html(html, final_url):
                if candidate not in seen and candidate not in queue:
                    queue.append(candidate)

    return None


def build_evidence(
    row: dict[str, object],
    *,
    session: requests.Session | None = None,
    fetch_official: bool = True,
    timeout: float = DEFAULT_REQUEST_TIMEOUT,
    max_chars: int = DEFAULT_EVIDENCE_MAX_CHARS,
) -> tuple[str, str]:
    """Return (source, text) without exposing any classifier decision.

    Evidence priority is deliberately independent of the current prediction:
    stored summary, cached official PDF, remotely resolved official PDF, official
    page, then title-only fallback.
    """
    summary = normalize_pdf_text(str(row.get("summary") or ""))
    if summary:
        excerpt = select_legal_excerpt(summary, max_chars=max_chars) or summary[:max_chars]
        return "summary", excerpt

    pdf_path = _resolved_pdf_path(row.get("pdf_path"))
    if pdf_path is not None:
        try:
            excerpt = extract_pdf_excerpt(pdf_path, max_chars=max_chars)
        except Exception:
            excerpt = None
        if excerpt:
            return "cached_pdf", excerpt

    official_url = str(row.get("official_url") or "").strip()
    if fetch_official and session is not None and official_url:
        remote_pdf_excerpt = _remote_pdf_excerpt(
            session,
            row,
            timeout=timeout,
            max_chars=max_chars,
        )
        if remote_pdf_excerpt:
            return "remote_pdf", remote_pdf_excerpt

        try:
            excerpt = _official_page_excerpt(
                session,
                official_url,
                timeout=timeout,
                max_chars=max_chars,
            )
        except (requests.RequestException, ValueError):
            excerpt = None
        except Exception:
            excerpt = None
        if excerpt:
            return "official_page", excerpt

    title = normalize_pdf_text(str(row.get("title") or ""))
    return "title_only", title[:max_chars]


def enrich_rows(
    rows: list[dict[str, object]],
    *,
    fetch_official: bool = True,
    timeout: float = DEFAULT_REQUEST_TIMEOUT,
    max_chars: int = DEFAULT_EVIDENCE_MAX_CHARS,
    official_delay_seconds: float = DEFAULT_OFFICIAL_DELAY_SECONDS,
) -> list[dict[str, object]]:
    session: requests.Session | None = None
    if fetch_official:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "radar-laboral/0.1 (+https://github.com/gumorenos/radar-laboral)",
                "Accept-Language": "es-PE,es;q=0.9",
            }
        )

    enriched: list[dict[str, object]] = []
    try:
        for row in rows:
            source, text = build_evidence(
                row,
                session=session,
                fetch_official=fetch_official,
                timeout=timeout,
                max_chars=max_chars,
            )
            item = dict(row)
            item["evidence_source"] = source
            item["evidence_chars"] = len(text)
            item["evidence_text"] = text
            enriched.append(item)
            if (
                fetch_official
                and source in {"remote_pdf", "official_page"}
                and official_delay_seconds > 0
            ):
                time.sleep(official_delay_seconds)
    finally:
        if session is not None:
            session.close()
    return enriched


def write_label_sheet(
    path: Path,
    rows: list[dict[str, object]],
    *,
    include_model_output: bool = False,
    enriched: bool = False,
) -> None:
    """Write an annotation sheet.

    The default is deliberately blind: annotators do not see the current model
    prediction, scores or reason before assigning the human label. This reduces
    anchoring bias when the resulting labels become the gold benchmark.
    """
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
        "official_url",
    ]
    if enriched:
        fieldnames.extend(["evidence_source", "evidence_chars", "evidence_text"])
    else:
        fieldnames.append("classification_text_excerpt")
    fieldnames.extend(["human_label", "human_notes"])

    if include_model_output:
        fieldnames.extend(
            [
                "current_prediction",
                "current_reason",
                "classification_score",
                "rule_score",
                "classification_method",
            ]
        )

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            output = {
                "id": row.get("id"),
                "publication_date": row.get("publication_date"),
                "source": row.get("source"),
                "document_type": row.get("document_type"),
                "number": row.get("number"),
                "title": row.get("title"),
                "summary": row.get("summary"),
                "issuer": row.get("issuer"),
                "official_url": row.get("official_url"),
                "human_label": "",
                "human_notes": "",
            }
            if enriched:
                output.update(
                    {
                        "evidence_source": row.get("evidence_source"),
                        "evidence_chars": row.get("evidence_chars"),
                        "evidence_text": row.get("evidence_text"),
                    }
                )
            else:
                output["classification_text_excerpt"] = row.get(
                    "classification_text_excerpt"
                )

            if include_model_output:
                output.update(
                    {
                        "current_prediction": row.get("labor_relevance"),
                        "current_reason": row.get("relevance_reason"),
                        "classification_score": row.get("classification_score"),
                        "rule_score": row.get("rule_score"),
                        "classification_method": row.get("classification_method"),
                    }
                )
            writer.writerow(output)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exporta una muestra estratificada del corpus para etiquetado humano"
    )
    parser.add_argument("output", type=Path)
    parser.add_argument("--per-class", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260905)
    parser.add_argument(
        "--from-csv",
        type=Path,
        default=None,
        help="Reutiliza exactamente los IDs de una muestra CSV previa",
    )
    parser.add_argument(
        "--enrich",
        action="store_true",
        help="Añade evidencia ciega desde summary, PDF cacheado o página oficial",
    )
    parser.add_argument(
        "--no-official-fetch",
        action="store_true",
        help="En modo --enrich no consulta páginas oficiales; usa solo datos locales",
    )
    parser.add_argument(
        "--evidence-max-chars",
        type=int,
        default=DEFAULT_EVIDENCE_MAX_CHARS,
        help="Máximo de caracteres de evidencia por fila",
    )
    parser.add_argument(
        "--official-delay",
        type=float,
        default=DEFAULT_OFFICIAL_DELAY_SECONDS,
        help="Pausa en segundos después de una página oficial usada como evidencia",
    )
    parser.add_argument(
        "--include-model-output",
        action="store_true",
        help="Incluye predicción y scores actuales; por defecto el etiquetado es ciego",
    )
    args = parser.parse_args()

    if args.from_csv is not None:
        rows = sample_by_ids(sample_ids_from_csv(args.from_csv))
    else:
        rows = stratified_sample(max(1, args.per_class), seed=args.seed)

    if args.enrich:
        rows = enrich_rows(
            rows,
            fetch_official=not args.no_official_fetch,
            max_chars=max(1000, args.evidence_max_chars),
            official_delay_seconds=max(0.0, args.official_delay),
        )

    write_label_sheet(
        args.output,
        rows,
        include_model_output=args.include_model_output,
        enriched=args.enrich,
    )
    mode = "con predicción actual" if args.include_model_output else "ciego"
    suffix = ", enriquecido" if args.enrich else ""
    print(f"Exportados {len(rows)} registros a {args.output} (modo {mode}{suffix})")


if __name__ == "__main__":
    main()
