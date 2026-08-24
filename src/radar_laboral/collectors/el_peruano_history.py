from __future__ import annotations

import argparse
import time
from datetime import date, timedelta
from pathlib import Path

import requests

from radar_laboral.collectors.el_peruano import cache_pdf, default_catalog_path, merge_catalog
from radar_laboral.collectors.el_peruano_search import (
    TRACKED_RELEVANCE,
    fetch_day,
    local_today,
)
from radar_laboral.coverage import mark_coverage_day
from radar_laboral.db import (
    enrich_norm,
    finish_sync_run,
    init_db,
    start_sync_run,
    upsert_norm,
)

SOURCE = "El Peruano histórico"


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
    run_id = start_sync_run(SOURCE)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "radar-laboral/0.1 (+https://github.com/gumorenos/radar-laboral)",
            "Accept-Language": "es-PE,es;q=0.9",
        }
    )

    stored_records: list[dict[str, object]] = []
    try:
        for current_day in _iter_days(start_date, end_date):
            raw_records = fetch_day(
                session,
                current_day,
                page_delay_seconds=max(0.0, page_delay_seconds),
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
                stored_records.append(stored)

            if day_records:
                merge_catalog(day_records, catalog_path)

            mark_coverage_day(
                current_day,
                record_count=len(day_records),
                relevant_count=sum(
                    1 for item in day_records if item.get("labor_relevance") == "relevant"
                ),
                review_count=sum(
                    1 for item in day_records if item.get("labor_relevance") == "review"
                ),
                is_complete=current_day < local_today(),
            )

            if day_delay_seconds > 0 and current_day < end_date:
                time.sleep(day_delay_seconds)

        relevant_count = sum(
            1 for item in stored_records if item.get("labor_relevance") == "relevant"
        )
        review_count = sum(
            1 for item in stored_records if item.get("labor_relevance") == "review"
        )
        pdf_count = sum(1 for item in stored_records if item.get("pdf_path"))
        latest_date = max(
            (
                str(item.get("publication_date"))
                for item in stored_records
                if item.get("publication_date")
            ),
            default=None,
        )
        finish_sync_run(
            run_id,
            status="success",
            records_seen=len(stored_records),
            relevant_count=relevant_count,
            review_count=review_count,
            pdf_count=pdf_count,
            latest_publication_date=latest_date,
        )
        return stored_records
    except Exception as exc:
        finish_sync_run(
            run_id,
            status="failed",
            records_seen=len(stored_records),
            relevant_count=sum(
                1 for item in stored_records if item.get("labor_relevance") == "relevant"
            ),
            review_count=sum(
                1 for item in stored_records if item.get("labor_relevance") == "review"
            ),
            pdf_count=sum(1 for item in stored_records if item.get("pdf_path")),
            error=f"{type(exc).__name__}: {exc}"[:2000],
        )
        raise
    finally:
        session.close()


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use formato YYYY-MM-DD") from exc


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Carga un rango histórico de Normas Legales regulares y extraordinarias "
            "desde el buscador oficial de El Peruano"
        )
    )
    parser.add_argument("--from", dest="start_date", type=_parse_date, required=True)
    parser.add_argument("--to", dest="end_date", type=_parse_date, required=True)
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
    relevant_count = sum(
        1 for item in records if item.get("labor_relevance") == "relevant"
    )
    review_count = sum(1 for item in records if item.get("labor_relevance") == "review")
    pdf_count = sum(1 for item in records if item.get("pdf_path"))
    print(
        f"El Peruano histórico: {len(records)} registros; "
        f"{relevant_count} relevantes; {review_count} por revisar; "
        f"{pdf_count} PDF almacenados."
    )


if __name__ == "__main__":
    main()
