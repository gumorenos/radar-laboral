from __future__ import annotations

import argparse
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from radar_laboral.db import (
    enrich_norm,
    finish_sync_run,
    init_db,
    start_sync_run,
    upsert_norm,
)
from radar_laboral.collectors.el_peruano import (
    BUSQUEDAS_URL,
    DEVICE_RE,
    NUMBER_RE,
    SOURCE,
    cache_pdf,
    default_catalog_path,
    merge_catalog,
)

SEARCH_URL = f"{BUSQUEDAS_URL}/"
PAGE_SIZE = 20
PUBLICATION_TYPES = (
    ("NL", "regular"),
    ("EX", "extraordinary"),
)
TOTAL_RE = re.compile(r"(?P<count>[\d.,]+)\s+dispositivos\s+encontrados", re.I)
DOT_DATE_RE = re.compile(r"\b(?P<day>\d{2})\.(?P<month>\d{2})\.(?P<year>\d{4})\b")
TRACKED_RELEVANCE = {"relevant", "review"}


class HistoricalCollectorError(RuntimeError):
    pass


def _iso_dot_date(value: re.Match[str]) -> str:
    return date(
        int(value.group("year")),
        int(value.group("month")),
        int(value.group("day")),
    ).isoformat()


def _clean_lines(node: Tag) -> list[str]:
    return [line.strip() for line in node.get_text("\n", strip=True).splitlines() if line.strip()]


def _result_context(anchor: Tag, op: str) -> Tag:
    node: Tag | None = anchor
    while node is not None:
        text = node.get_text(" ", strip=True)
        if op in text and DOT_DATE_RE.search(text):
            return node
        parent = node.parent
        node = parent if isinstance(parent, Tag) else None
    return anchor.parent if isinstance(anchor.parent, Tag) else anchor


def _issuer_from_context(context: Tag, heading: str, op: str) -> str | None:
    for line in _clean_lines(context):
        if line == heading or op in line or DOT_DATE_RE.search(line):
            continue
        if NUMBER_RE.match(line):
            continue
        if len(line) <= 140 and line.upper() == line and any(ch.isalpha() for ch in line):
            return line

    for previous in context.find_all_previous(["h2", "h3", "h4", "strong"], limit=12):
        text = previous.get_text(" ", strip=True)
        if not text or text == heading or NUMBER_RE.match(text):
            continue
        if len(text) <= 140 and text.upper() == text and any(ch.isalpha() for ch in text):
            return text
    return None


def _anchor_texts(anchors: list[Tag]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for anchor in anchors:
        text = anchor.get_text(" ", strip=True)
        if not text or text.lower() in {"pdf", "html", "cuadernillo"}:
            continue
        if text not in seen:
            seen.add(text)
            unique.append(text)
    return unique


def _heading_and_summary(anchors: list[Tag]) -> tuple[str | None, str | None]:
    texts = _anchor_texts(anchors)
    if not texts:
        return None, None

    numbered = next((text for text in texts if NUMBER_RE.match(text)), None)
    if numbered:
        alternatives = [text for text in texts if text != numbered]
        summary = max(alternatives, key=len) if alternatives else None
        return numbered, summary

    heading = min(texts, key=len)
    alternatives = [text for text in texts if text != heading]
    summary = max(alternatives, key=len) if alternatives else None
    return heading, summary


def parse_search_html(
    html: str,
    *,
    edition: str = "regular",
    captured_at: str | None = None,
) -> tuple[list[dict[str, str | None]], int | None]:
    soup = BeautifulSoup(html, "html.parser")
    captured_at = captured_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    page_text = soup.get_text(" ", strip=True)
    total_match = TOTAL_RE.search(page_text)
    total = None
    if total_match:
        total = int(re.sub(r"[^0-9]", "", total_match.group("count")))

    groups: dict[str, dict[str, object]] = {}
    for anchor in soup.find_all("a", href=True):
        absolute = urljoin(SEARCH_URL, str(anchor.get("href", "")).strip())
        device_match = DEVICE_RE.search(urlparse(absolute).path)
        if not device_match:
            continue
        op = device_match.group("op")
        group = groups.setdefault(op, {"url": absolute, "anchors": [], "first": anchor})
        group["anchors"].append(anchor)

    records: list[dict[str, str | None]] = []
    for op, group in groups.items():
        anchors = list(group["anchors"])
        heading, summary = _heading_and_summary(anchors)
        if not heading:
            continue

        first = group["first"]
        context = _result_context(first, op)
        context_text = context.get_text(" ", strip=True)
        date_match = DOT_DATE_RE.search(context_text)
        if not date_match:
            continue

        number_match = NUMBER_RE.match(heading)
        document_type = number_match.group("document_type").strip() if number_match else heading
        number = number_match.group("number").strip() if number_match else None
        issuer = _issuer_from_context(context, heading, op)
        official_url = str(group["url"])
        records.append(
            {
                "id": f"elperuano:{op}",
                "source": SOURCE,
                "document_type": document_type,
                "number": number,
                "title": summary or heading,
                "summary": None,
                "publication_date": _iso_dot_date(date_match),
                "effective_date": None,
                "issuer": issuer,
                "topic": None,
                "status": None,
                "edition": edition,
                "official_url": official_url,
                "pdf_url": official_url.rstrip("/") + "/pdf",
                "pdf_path": None,
                "sha256": None,
                "captured_at": captured_at,
                "updated_at": captured_at,
            }
        )

    records.sort(key=lambda item: (item["publication_date"] or "", item["id"] or ""))
    return records, total


def _search_params(day: date, start: int, publication_type: str) -> dict[str, str | int]:
    compact = day.strftime("%Y%m%d")
    return {
        "ci": "ONLY",
        "fechaFin": compact,
        "fechaIni": compact,
        "start": start,
        "tipoPublicacion": publication_type,
    }


def fetch_publication_type(
    session: requests.Session,
    day: date,
    publication_type: str,
    edition: str,
    *,
    page_delay_seconds: float = 0.25,
) -> list[dict[str, str | None]]:
    offset = 0
    expected_total: int | None = None
    records: dict[str, dict[str, str | None]] = {}
    max_pages = 100

    for page_index in range(max_pages):
        response = session.get(
            SEARCH_URL,
            params=_search_params(day, offset, publication_type),
            timeout=30,
        )
        response.raise_for_status()
        page_records, total = parse_search_html(response.text, edition=edition)
        if expected_total is None and total is not None:
            expected_total = total

        for record in page_records:
            records[str(record["id"])] = record

        if expected_total == 0:
            break
        if expected_total is not None and len(records) >= expected_total:
            break
        if not page_records:
            if expected_total is None and page_index == 0:
                break
            raise HistoricalCollectorError(
                f"El Peruano informó {expected_total or 'más'} dispositivos {publication_type} "
                f"para {day.isoformat()}, pero start={offset} no devolvió registros reconocibles."
            )

        offset += PAGE_SIZE
        if page_delay_seconds > 0:
            time.sleep(page_delay_seconds)
    else:
        raise HistoricalCollectorError(
            f"Se alcanzó el límite de paginación {publication_type} para {day.isoformat()}."
        )

    if expected_total is not None and len(records) != expected_total:
        raise HistoricalCollectorError(
            f"El Peruano informó {expected_total} dispositivos {publication_type} para {day.isoformat()} "
            f"pero se normalizaron {len(records)}. Se evita aceptar un backfill incompleto."
        )

    return sorted(records.values(), key=lambda item: item["id"] or "")


def fetch_day(
    session: requests.Session,
    day: date,
    *,
    page_delay_seconds: float = 0.25,
) -> list[dict[str, str | None]]:
    combined: dict[str, dict[str, str | None]] = {}
    for publication_type, edition in PUBLICATION_TYPES:
        records = fetch_publication_type(
            session,
            day,
            publication_type,
            edition,
            page_delay_seconds=page_delay_seconds,
        )
        for record in records:
            key = str(record["id"])
            previous = combined.get(key)
            if previous and previous.get("edition") != record.get("edition"):
                raise HistoricalCollectorError(
                    f"El dispositivo {key} aparece en más de una edición para {day.isoformat()}."
                )
            combined[key] = record
    return sorted(combined.values(), key=lambda item: item["id"] or "")


def _iter_days(start_date: date, end_date: date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def backfill(
    start_date: date,
    end_date: date,
    *,
    download_pdfs: bool = True,
    catalog_path: Path | None = None,
    page_delay_seconds: float = 0.25,
    day_delay_seconds: float = 0.5,
) -> list[dict[str, object]]:
    if end_date < start_date:
        raise ValueError("La fecha final no puede ser anterior a la fecha inicial")

    catalog_path = catalog_path or default_catalog_path()
    init_db()
    run_id = start_sync_run("El Peruano histórico")
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "radar-laboral/0.1 (+https://github.com/gumorenos/radar-laboral)",
            "Accept-Language": "es-PE,es;q=0.9",
        }
    )

    accumulated: list[dict[str, object]] = []
    try:
        for day in _iter_days(start_date, end_date):
            raw_records = fetch_day(
                session,
                day,
                page_delay_seconds=page_delay_seconds,
            )
            day_records: list[dict[str, object]] = []
            for raw in raw_records:
                enriched = enrich_norm(raw)
                if download_pdfs and enriched.get("labor_relevance") in TRACKED_RELEVANCE:
                    try:
                        cache_pdf(session, enriched)
                    except requests.RequestException:
                        pass
                stored = upsert_norm(enriched)
                day_records.append(stored)
                accumulated.append(stored)

            if day_records:
                merge_catalog(day_records, catalog_path)

            if day_delay_seconds > 0 and day < end_date:
                time.sleep(day_delay_seconds)

        relevant_count = sum(1 for item in accumulated if item.get("labor_relevance") == "relevant")
        review_count = sum(1 for item in accumulated if item.get("labor_relevance") == "review")
        pdf_count = sum(1 for item in accumulated if item.get("pdf_path"))
        finish_sync_run(
            run_id,
            status="success",
            records_seen=len(accumulated),
            relevant_count=relevant_count,
            review_count=review_count,
            pdf_count=pdf_count,
            latest_publication_date=end_date.isoformat(),
        )
        return accumulated
    except Exception as exc:
        relevant_count = sum(1 for item in accumulated if item.get("labor_relevance") == "relevant")
        review_count = sum(1 for item in accumulated if item.get("labor_relevance") == "review")
        pdf_count = sum(1 for item in accumulated if item.get("pdf_path"))
        finish_sync_run(
            run_id,
            status="failed",
            records_seen=len(accumulated),
            relevant_count=relevant_count,
            review_count=review_count,
            pdf_count=pdf_count,
            error=f"{type(exc).__name__}: {exc}"[:2000],
        )
        raise
    finally:
        session.close()


def _parse_cli_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use formato YYYY-MM-DD") from exc


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Carga Normas Legales regulares y extraordinarias desde el buscador oficial de El Peruano"
    )
    parser.add_argument("--from", dest="start_date", type=_parse_cli_date, required=True)
    parser.add_argument("--to", dest="end_date", type=_parse_cli_date, required=True)
    parser.add_argument("--no-pdf", action="store_true")
    parser.add_argument("--catalog", type=Path, default=default_catalog_path())
    parser.add_argument("--page-delay", type=float, default=0.25)
    parser.add_argument("--day-delay", type=float, default=0.5)
    args = parser.parse_args()

    records = backfill(
        args.start_date,
        args.end_date,
        download_pdfs=not args.no_pdf,
        catalog_path=args.catalog,
        page_delay_seconds=max(0.0, args.page_delay),
        day_delay_seconds=max(0.0, args.day_delay),
    )
    relevant = sum(1 for item in records if item.get("labor_relevance") == "relevant")
    review = sum(1 for item in records if item.get("labor_relevance") == "review")
    pdfs = sum(1 for item in records if item.get("pdf_path"))
    print(
        f"El Peruano histórico: {len(records)} registros; {relevant} relevantes; "
        f"{review} por revisar; {pdfs} PDF almacenados."
    )


if __name__ == "__main__":
    main()
