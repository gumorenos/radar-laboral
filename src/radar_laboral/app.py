from __future__ import annotations

import argparse
import hmac
import os
import threading
import webbrowser
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, abort, redirect, render_template, request, send_file, url_for
from waitress import serve

from .case_law import (
    get_case_law,
    list_case_law_filter_options,
    search_case_law,
)
from .db import (
    data_dir,
    enqueue_backfill_request,
    get_norm,
    init_db,
    latest_sync_run,
    list_norm_filter_options,
    list_sync_requests,
    norm_date_bounds,
    norm_stats,
    search_norms,
)
from .relations import (
    list_related_case_law,
    list_related_norms,
    list_related_norms_for_case_law,
)

PAGE_SIZE = 50
MAX_PAGE = 100_000
DEFAULT_MAX_BACKFILL_DAYS = 366
DEFAULT_TIMEZONE = "America/Lima"
RELATION_LABELS = {
    "amends": "Modifica",
    "repeals": "Deroga",
    "regulates": "Reglamenta",
    "interprets": "Interpreta",
    "applies": "Aplica",
    "explains": "Explica",
    "supports": "Sustenta",
    "limits": "Limita",
}


def _page_number(value: str) -> int:
    try:
        return min(MAX_PAGE, max(1, int(value)))
    except (TypeError, ValueError):
        return 1


def _pagination(endpoint: str, page: int, has_next: bool, args: dict[str, str]):
    clean = {key: value for key, value in args.items() if value}
    return {
        "page": page,
        "has_previous": page > 1,
        "has_next": has_next,
        "previous_url": url_for(endpoint, **clean, page=page - 1) if page > 1 else None,
        "next_url": url_for(endpoint, **clean, page=page + 1) if has_next else None,
    }


def _document_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = data_dir() / path
    return path


def _env_positive_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _local_today() -> date:
    timezone_name = os.getenv("RADAR_TIMEZONE", DEFAULT_TIMEZONE)
    try:
        zone = ZoneInfo(timezone_name)
    except Exception:
        zone = ZoneInfo(DEFAULT_TIMEZONE)
    return datetime.now(zone).date()


def _admin_token() -> str:
    return os.getenv("RADAR_ADMIN_TOKEN", "").strip()


def _valid_admin_token(candidate: str) -> bool:
    configured = _admin_token()
    return bool(configured) and hmac.compare_digest(configured, candidate)


def create_app() -> Flask:
    app = Flask(__name__)
    init_db()

    @app.get("/")
    def index():
        query = request.args.get("q", "").strip()
        relevance = request.args.get("relevance", "tracked").strip()
        page = _page_number(request.args.get("page", "1"))
        filters = {
            "source": request.args.get("source", "").strip(),
            "document_type": request.args.get("document_type", "").strip(),
            "issuer": request.args.get("issuer", "").strip(),
            "topic": request.args.get("topic", "").strip(),
            "edition": request.args.get("edition", "").strip(),
            "date_from": request.args.get("date_from", "").strip(),
            "date_to": request.args.get("date_to", "").strip(),
        }
        offset = (page - 1) * PAGE_SIZE
        fetched = search_norms(
            query=query,
            relevance=relevance,
            limit=PAGE_SIZE + 1,
            offset=offset,
            **filters,
        )
        has_next = len(fetched) > PAGE_SIZE
        rows = fetched[:PAGE_SIZE]
        return render_template(
            "index.html",
            rows=rows,
            query=query,
            relevance=relevance,
            filters=filters,
            options=list_norm_filter_options(),
            stats=norm_stats(),
            date_bounds=norm_date_bounds(),
            pagination=_pagination(
                "index",
                page,
                has_next,
                {"q": query, "relevance": relevance, **filters},
            ),
        )

    @app.get("/norm/<norm_id>")
    def norm_detail(norm_id: str):
        row = get_norm(norm_id)
        if row is None:
            abort(404)
        return render_template(
            "norm_detail.html",
            norm=row,
            related_norms=list_related_norms(norm_id),
            related_case_law=list_related_case_law(norm_id),
            relation_labels=RELATION_LABELS,
        )

    @app.get("/norm/<norm_id>/pdf")
    def norm_pdf(norm_id: str):
        row = get_norm(norm_id)
        if row is None:
            abort(404)
        path = _document_path(row["pdf_path"])
        if path and path.exists():
            return send_file(path, mimetype="application/pdf")
        if row["pdf_url"]:
            return redirect(row["pdf_url"])
        abort(404)

    @app.get("/jurisprudencia")
    def case_law_index():
        query = request.args.get("q", "").strip()
        page = _page_number(request.args.get("page", "1"))
        filters = {
            "court": request.args.get("court", "").strip(),
            "document_type": request.args.get("document_type", "").strip(),
            "topic": request.args.get("topic", "").strip(),
            "binding_level": request.args.get("binding_level", "").strip(),
            "date_from": request.args.get("date_from", "").strip(),
            "date_to": request.args.get("date_to", "").strip(),
        }
        offset = (page - 1) * PAGE_SIZE
        fetched = search_case_law(
            query,
            limit=PAGE_SIZE + 1,
            offset=offset,
            **filters,
        )
        has_next = len(fetched) > PAGE_SIZE
        rows = fetched[:PAGE_SIZE]
        return render_template(
            "case_law_index.html",
            rows=rows,
            query=query,
            filters=filters,
            options=list_case_law_filter_options(),
            pagination=_pagination(
                "case_law_index",
                page,
                has_next,
                {"q": query, **filters},
            ),
        )

    @app.get("/jurisprudencia/<case_id>")
    def case_law_detail(case_id: str):
        row = get_case_law(case_id)
        if row is None:
            abort(404)
        return render_template(
            "case_law_detail.html",
            case=row,
            related_norms=list_related_norms_for_case_law(case_id),
            relation_labels=RELATION_LABELS,
        )

    @app.get("/jurisprudencia/<case_id>/pdf")
    def case_law_pdf(case_id: str):
        row = get_case_law(case_id)
        if row is None:
            abort(404)
        path = _document_path(row["pdf_path"])
        if path and path.exists():
            return send_file(path, mimetype="application/pdf")
        if row["pdf_url"]:
            return redirect(row["pdf_url"])
        abort(404)

    @app.get("/status")
    def status_page():
        last_sync = latest_sync_run()
        return render_template(
            "status.html",
            stats=norm_stats(),
            date_bounds=norm_date_bounds(),
            last_sync=dict(last_sync) if last_sync else None,
            sync_requests=[dict(row) for row in list_sync_requests(20)],
            admin_enabled=bool(_admin_token()),
            today=_local_today().isoformat(),
            max_backfill_days=_env_positive_int(
                "RADAR_MAX_BACKFILL_DAYS", DEFAULT_MAX_BACKFILL_DAYS
            ),
            queued=request.args.get("queued", "").strip(),
            created=request.args.get("created", "").strip(),
            sync_error=request.args.get("sync_error", "").strip(),
        )

    @app.post("/admin/backfill")
    def queue_backfill():
        if not _admin_token():
            abort(503, description="La carga histórica web no está habilitada")
        if not _valid_admin_token(request.form.get("admin_token", "")):
            abort(403)

        start_raw = request.form.get("start_date", "").strip()
        end_raw = request.form.get("end_date", "").strip() or _local_today().isoformat()
        try:
            start_date = date.fromisoformat(start_raw)
            end_date = date.fromisoformat(end_raw)
        except ValueError:
            return redirect(url_for("status_page", sync_error="Fecha inválida"))

        today = _local_today()
        if end_date < start_date:
            return redirect(
                url_for("status_page", sync_error="La fecha final no puede ser anterior a la inicial")
            )
        if end_date > today:
            return redirect(
                url_for("status_page", sync_error="La fecha final no puede estar en el futuro")
            )

        days = (end_date - start_date).days + 1
        max_days = _env_positive_int("RADAR_MAX_BACKFILL_DAYS", DEFAULT_MAX_BACKFILL_DAYS)
        if days > max_days:
            return redirect(
                url_for(
                    "status_page",
                    sync_error=f"El rango máximo permitido es de {max_days} días",
                )
            )

        request_id, created = enqueue_backfill_request(
            start_date.isoformat(),
            end_date.isoformat(),
            download_pdfs=request.form.get("download_pdfs") == "1",
        )
        return redirect(
            url_for(
                "status_page",
                queued=request_id,
                created="1" if created else "0",
            )
        )

    @app.get("/api/status")
    def status_api():
        last_sync = latest_sync_run()
        return {
            "status": "ok",
            "stats": norm_stats(),
            "date_bounds": norm_date_bounds(),
            "last_sync": dict(last_sync) if last_sync else None,
            "sync_requests": [dict(row) for row in list_sync_requests(10)],
        }

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Radar Laboral Perú")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()

    url_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    url = f"http://{url_host}:{args.port}"
    if args.open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    serve(create_app(), host=args.host, port=args.port, threads=4)


if __name__ == "__main__":
    main()
