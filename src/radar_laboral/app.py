from __future__ import annotations

import argparse
import threading
import webbrowser
from pathlib import Path

from flask import Flask, abort, redirect, render_template, request, send_file, url_for
from waitress import serve

from .db import (
    data_dir,
    get_norm,
    init_db,
    latest_sync_run,
    list_norm_filter_options,
    norm_stats,
    search_norms,
)

PAGE_SIZE = 50
MAX_PAGE = 100_000


def _page_number(value: str) -> int:
    try:
        return min(MAX_PAGE, max(1, int(value)))
    except (TypeError, ValueError):
        return 1


def create_app() -> Flask:
    app = Flask(__name__)
    init_db()

    @app.get("/")
    def index():
        query = request.args.get("q", "").strip()
        relevance = request.args.get("relevance", "relevant").strip()
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

        base_args = {
            "q": query,
            "relevance": relevance,
            **filters,
        }
        base_args = {key: value for key, value in base_args.items() if value}
        pagination = {
            "page": page,
            "has_previous": page > 1,
            "has_next": has_next,
            "previous_url": url_for("index", **base_args, page=page - 1) if page > 1 else None,
            "next_url": url_for("index", **base_args, page=page + 1) if has_next else None,
        }

        return render_template(
            "index.html",
            rows=rows,
            query=query,
            relevance=relevance,
            filters=filters,
            options=list_norm_filter_options(),
            pagination=pagination,
        )

    @app.get("/norm/<norm_id>/pdf")
    def norm_pdf(norm_id: str):
        row = get_norm(norm_id)
        if row is None:
            abort(404)

        if row["pdf_path"]:
            path = Path(row["pdf_path"])
            if not path.is_absolute():
                path = data_dir() / path
            if path.exists():
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
            last_sync=dict(last_sync) if last_sync else None,
        )

    @app.get("/api/status")
    def status_api():
        last_sync = latest_sync_run()
        return {
            "status": "ok",
            "stats": norm_stats(),
            "last_sync": dict(last_sync) if last_sync else None,
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
