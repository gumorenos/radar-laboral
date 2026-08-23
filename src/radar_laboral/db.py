from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from .classifier import classify_labor

SCHEMA = """
CREATE TABLE IF NOT EXISTS norms (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    document_type TEXT,
    number TEXT,
    title TEXT NOT NULL,
    summary TEXT,
    publication_date TEXT,
    effective_date TEXT,
    issuer TEXT,
    topic TEXT,
    status TEXT,
    edition TEXT,
    labor_relevance TEXT,
    relevance_reason TEXT,
    official_url TEXT NOT NULL,
    pdf_url TEXT,
    pdf_path TEXT,
    sha256 TEXT,
    captured_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_norms_publication_date
    ON norms(publication_date DESC);
CREATE INDEX IF NOT EXISTS idx_norms_number
    ON norms(number);
CREATE INDEX IF NOT EXISTS idx_norms_source
    ON norms(source);
CREATE INDEX IF NOT EXISTS idx_norms_topic
    ON norms(topic);
CREATE INDEX IF NOT EXISTS idx_norms_edition
    ON norms(edition);

CREATE TABLE IF NOT EXISTS case_law (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    court TEXT NOT NULL,
    document_type TEXT,
    number TEXT,
    docket_number TEXT,
    title TEXT NOT NULL,
    summary TEXT,
    decision_date TEXT,
    publication_date TEXT,
    topic TEXT,
    binding_level TEXT,
    official_url TEXT NOT NULL,
    pdf_url TEXT,
    pdf_path TEXT,
    sha256 TEXT,
    captured_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_case_law_decision_date
    ON case_law(decision_date DESC);
CREATE INDEX IF NOT EXISTS idx_case_law_number
    ON case_law(number);
CREATE INDEX IF NOT EXISTS idx_case_law_court
    ON case_law(court);
CREATE INDEX IF NOT EXISTS idx_case_law_topic
    ON case_law(topic);

CREATE TABLE IF NOT EXISTS concepts (
    slug TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT,
    topic TEXT,
    content_path TEXT NOT NULL,
    last_reviewed_at TEXT,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_concepts_topic
    ON concepts(topic);

CREATE TABLE IF NOT EXISTS document_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_kind TEXT NOT NULL,
    from_id TEXT NOT NULL,
    to_kind TEXT NOT NULL,
    to_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    note TEXT,
    created_at TEXT,
    UNIQUE(from_kind, from_id, to_kind, to_id, relation_type)
);

CREATE INDEX IF NOT EXISTS idx_document_relations_from
    ON document_relations(from_kind, from_id);
CREATE INDEX IF NOT EXISTS idx_document_relations_to
    ON document_relations(to_kind, to_id);

CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    records_seen INTEGER NOT NULL DEFAULT 0,
    relevant_count INTEGER NOT NULL DEFAULT 0,
    review_count INTEGER NOT NULL DEFAULT 0,
    pdf_count INTEGER NOT NULL DEFAULT 0,
    latest_publication_date TEXT,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_sync_runs_source_started
    ON sync_runs(source, started_at DESC);
"""

NORM_COLUMNS = (
    "id",
    "source",
    "document_type",
    "number",
    "title",
    "summary",
    "publication_date",
    "effective_date",
    "issuer",
    "topic",
    "status",
    "edition",
    "labor_relevance",
    "relevance_reason",
    "official_url",
    "pdf_url",
    "pdf_path",
    "sha256",
    "captured_at",
    "updated_at",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def data_dir() -> Path:
    path = Path(os.getenv("RADAR_DATA_DIR", "storage")).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    (path / "pdfs").mkdir(parents=True, exist_ok=True)
    (path / "catalog").mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "radar_laboral.db"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def _ensure_norm_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(norms)").fetchall()}
    additions = {
        "labor_relevance": "TEXT",
        "relevance_reason": "TEXT",
        "edition": "TEXT",
    }
    for column, sql_type in additions.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE norms ADD COLUMN {column} {sql_type}")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_norms_labor_relevance ON norms(labor_relevance)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_norms_edition ON norms(edition)")


def _backfill_norm_classification(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT id, source, document_type, number, title, summary, issuer, topic
        FROM norms
        WHERE labor_relevance IS NULL OR relevance_reason IS NULL
        """
    ).fetchall()
    for row in rows:
        classification = classify_labor(dict(row))
        conn.execute(
            """
            UPDATE norms
            SET labor_relevance = ?,
                relevance_reason = ?,
                topic = COALESCE(?, topic)
            WHERE id = ?
            """,
            (
                classification["labor_relevance"],
                classification["relevance_reason"],
                classification["topic"],
                row["id"],
            ),
        )


def init_db() -> None:
    with connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        _ensure_norm_columns(conn)
        _backfill_norm_classification(conn)


def enrich_norm(record: Mapping[str, object]) -> dict[str, object]:
    enriched = dict(record)
    classification = classify_labor(enriched)
    enriched["labor_relevance"] = classification["labor_relevance"]
    enriched["relevance_reason"] = classification["relevance_reason"]
    if classification["topic"]:
        enriched["topic"] = classification["topic"]
    return enriched


def upsert_norm(record: Mapping[str, object]) -> dict[str, object]:
    enriched = enrich_norm(record)

    if isinstance(record, dict):
        record.update(
            {
                "labor_relevance": enriched["labor_relevance"],
                "relevance_reason": enriched["relevance_reason"],
                "topic": enriched.get("topic"),
            }
        )

    values = [enriched.get(column) for column in NORM_COLUMNS]
    placeholders = ", ".join("?" for _ in NORM_COLUMNS)
    columns = ", ".join(NORM_COLUMNS)
    sql = f"""
        INSERT INTO norms ({columns})
        VALUES ({placeholders})
        ON CONFLICT(id) DO UPDATE SET
            source = excluded.source,
            document_type = COALESCE(excluded.document_type, norms.document_type),
            number = COALESCE(excluded.number, norms.number),
            title = excluded.title,
            summary = COALESCE(excluded.summary, norms.summary),
            publication_date = COALESCE(excluded.publication_date, norms.publication_date),
            effective_date = COALESCE(excluded.effective_date, norms.effective_date),
            issuer = COALESCE(excluded.issuer, norms.issuer),
            topic = COALESCE(excluded.topic, norms.topic),
            status = COALESCE(excluded.status, norms.status),
            edition = COALESCE(excluded.edition, norms.edition),
            labor_relevance = excluded.labor_relevance,
            relevance_reason = excluded.relevance_reason,
            official_url = excluded.official_url,
            pdf_url = COALESCE(excluded.pdf_url, norms.pdf_url),
            pdf_path = COALESCE(excluded.pdf_path, norms.pdf_path),
            sha256 = COALESCE(excluded.sha256, norms.sha256),
            updated_at = COALESCE(excluded.updated_at, norms.updated_at)
    """
    with connect() as conn:
        conn.execute(sql, values)
    return enriched


def get_norm(norm_id: str):
    with connect() as conn:
        return conn.execute("SELECT * FROM norms WHERE id = ?", (norm_id,)).fetchone()


def search_norms(
    query: str = "",
    source: str = "",
    relevance: str = "tracked",
    limit: int = 200,
):
    clauses: list[str] = []
    params: list[str | int] = []

    if query:
        like = f"%{query}%"
        clauses.append(
            "(title LIKE ? OR number LIKE ? OR summary LIKE ? OR issuer LIKE ? OR topic LIKE ?)"
        )
        params.extend([like, like, like, like, like])

    if source:
        clauses.append("source = ?")
        params.append(source)

    if relevance == "tracked":
        clauses.append("labor_relevance IN ('relevant', 'review')")
    elif relevance in {"relevant", "review", "not_labor"}:
        clauses.append("labor_relevance = ?")
        params.append(relevance)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT *
        FROM norms
        {where}
        ORDER BY publication_date DESC, captured_at DESC
        LIMIT ?
    """
    params.append(limit)

    with connect() as conn:
        return conn.execute(sql, params).fetchall()


def list_sources() -> list[str]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT source FROM norms WHERE source <> '' ORDER BY source"
        ).fetchall()
    return [row[0] for row in rows]


def start_sync_run(source: str) -> int:
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO sync_runs (source, started_at, status) VALUES (?, ?, 'running')",
            (source, utc_now()),
        )
        return int(cursor.lastrowid)


def finish_sync_run(
    run_id: int,
    *,
    status: str,
    records_seen: int = 0,
    relevant_count: int = 0,
    review_count: int = 0,
    pdf_count: int = 0,
    latest_publication_date: str | None = None,
    error: str | None = None,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE sync_runs
            SET finished_at = ?, status = ?, records_seen = ?, relevant_count = ?,
                review_count = ?, pdf_count = ?, latest_publication_date = ?, error = ?
            WHERE id = ?
            """,
            (
                utc_now(),
                status,
                records_seen,
                relevant_count,
                review_count,
                pdf_count,
                latest_publication_date,
                error,
                run_id,
            ),
        )


def latest_sync_run(source: str | None = None):
    with connect() as conn:
        if source:
            return conn.execute(
                "SELECT * FROM sync_runs WHERE source = ? ORDER BY id DESC LIMIT 1",
                (source,),
            ).fetchone()
        return conn.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1").fetchone()


def norm_stats() -> dict[str, int]:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN labor_relevance = 'relevant' THEN 1 ELSE 0 END) AS relevant,
                SUM(CASE WHEN labor_relevance = 'review' THEN 1 ELSE 0 END) AS review,
                SUM(CASE WHEN labor_relevance = 'not_labor' THEN 1 ELSE 0 END) AS not_labor,
                SUM(CASE WHEN pdf_path IS NOT NULL THEN 1 ELSE 0 END) AS pdf_cached
            FROM norms
            """
        ).fetchone()
    return {key: int(row[key] or 0) for key in row.keys()}
