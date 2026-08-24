from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from .classifier import CLASSIFIER_VERSION, classify_labor

SYNC_REQUEST_KIND_BACKFILL = "el_peruano_backfill"

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
    classification_version INTEGER,
    classification_score REAL,
    rule_score REAL,
    semantic_score REAL,
    semantic_model TEXT,
    classification_method TEXT,
    requires_review INTEGER,
    classification_evidence TEXT,
    classification_text_excerpt TEXT,
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
CREATE INDEX IF NOT EXISTS idx_norms_document_type
    ON norms(document_type);
CREATE INDEX IF NOT EXISTS idx_norms_issuer
    ON norms(issuer);

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

CREATE TABLE IF NOT EXISTS sync_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    download_pdfs INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_sync_requests_status_id
    ON sync_requests(status, id);
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
    "classification_version",
    "classification_score",
    "rule_score",
    "semantic_score",
    "semantic_model",
    "classification_method",
    "requires_review",
    "classification_evidence",
    "classification_text_excerpt",
    "official_url",
    "pdf_url",
    "pdf_path",
    "sha256",
    "captured_at",
    "updated_at",
)

FTS_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
FTS_TABLE_SQL = """
CREATE VIRTUAL TABLE norms_fts USING fts5(
    title,
    number,
    summary,
    issuer,
    topic,
    content='norms',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
)
"""
FTS_TRIGGER_SQL = """
CREATE TRIGGER IF NOT EXISTS norms_fts_ai AFTER INSERT ON norms BEGIN
    INSERT INTO norms_fts(rowid, title, number, summary, issuer, topic)
    VALUES (new.rowid, new.title, new.number, new.summary, new.issuer, new.topic);
END;

CREATE TRIGGER IF NOT EXISTS norms_fts_ad AFTER DELETE ON norms BEGIN
    INSERT INTO norms_fts(norms_fts, rowid, title, number, summary, issuer, topic)
    VALUES ('delete', old.rowid, old.title, old.number, old.summary, old.issuer, old.topic);
END;

CREATE TRIGGER IF NOT EXISTS norms_fts_au AFTER UPDATE ON norms BEGIN
    INSERT INTO norms_fts(norms_fts, rowid, title, number, summary, issuer, topic)
    VALUES ('delete', old.rowid, old.title, old.number, old.summary, old.issuer, old.topic);
    INSERT INTO norms_fts(rowid, title, number, summary, issuer, topic)
    VALUES (new.rowid, new.title, new.number, new.summary, new.issuer, new.topic);
END;
"""


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
        "classification_version": "INTEGER",
        "edition": "TEXT",
        "classification_score": "REAL",
        "rule_score": "REAL",
        "semantic_score": "REAL",
        "semantic_model": "TEXT",
        "classification_method": "TEXT",
        "requires_review": "INTEGER",
        "classification_evidence": "TEXT",
        "classification_text_excerpt": "TEXT",
    }
    for column, sql_type in additions.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE norms ADD COLUMN {column} {sql_type}")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_norms_labor_relevance ON norms(labor_relevance)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_norms_edition ON norms(edition)")


def _evidence_json(classification: Mapping[str, object]) -> str:
    return json.dumps(
        classification.get("classification_evidence") or {},
        ensure_ascii=False,
        sort_keys=True,
    )


def _classification_storage(classification: Mapping[str, object]) -> dict[str, object]:
    return {
        "labor_relevance": classification["labor_relevance"],
        "relevance_reason": classification["relevance_reason"],
        "classification_version": classification["classification_version"],
        "topic": classification["topic"],
        "classification_score": classification.get("classification_score"),
        "rule_score": classification.get("rule_score"),
        "semantic_score": classification.get("semantic_score"),
        "semantic_model": classification.get("semantic_model"),
        "classification_method": classification.get("classification_method"),
        "requires_review": int(bool(classification.get("requires_review"))),
        "classification_evidence": _evidence_json(classification),
    }


def _backfill_norm_classification(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT id, source, document_type, number, title, summary, issuer, topic,
               classification_text_excerpt
        FROM norms
        WHERE labor_relevance IS NULL
           OR relevance_reason IS NULL
           OR classification_version IS NULL
           OR classification_version < ?
           OR classification_score IS NULL
           OR classification_method IS NULL
           OR classification_evidence IS NULL
        """,
        (CLASSIFIER_VERSION,),
    ).fetchall()
    for row in rows:
        classification = classify_labor(dict(row))
        stored = _classification_storage(classification)
        conn.execute(
            """
            UPDATE norms
            SET labor_relevance = ?,
                relevance_reason = ?,
                topic = ?,
                classification_version = ?,
                classification_score = ?,
                rule_score = ?,
                semantic_score = ?,
                semantic_model = ?,
                classification_method = ?,
                requires_review = ?,
                classification_evidence = ?
            WHERE id = ?
            """,
            (
                stored["labor_relevance"],
                stored["relevance_reason"],
                stored["topic"],
                stored["classification_version"],
                stored["classification_score"],
                stored["rule_score"],
                stored["semantic_score"],
                stored["semantic_model"],
                stored["classification_method"],
                stored["requires_review"],
                stored["classification_evidence"],
                row["id"],
            ),
        )


def _ensure_norm_fts(conn: sqlite3.Connection) -> bool:
    """Create and seed the optional FTS5 index without making FTS5 a hard dependency."""
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'norms_fts'"
        ).fetchone()
        if exists is None:
            conn.execute(FTS_TABLE_SQL)
            conn.execute("INSERT INTO norms_fts(norms_fts) VALUES ('rebuild')")
        conn.executescript(FTS_TRIGGER_SQL)
        return True
    except sqlite3.OperationalError:
        return False


def _fts_available(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("SELECT rowid FROM norms_fts LIMIT 0")
        return True
    except sqlite3.OperationalError:
        return False


def _fts_query(query: str) -> str | None:
    tokens = FTS_TOKEN_RE.findall(query.casefold())
    if not tokens:
        return None
    return " ".join(f'"{token}"*' for token in tokens)


def init_db() -> None:
    with connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        _ensure_norm_columns(conn)
        _backfill_norm_classification(conn)
        _ensure_norm_fts(conn)


def enrich_norm(record: Mapping[str, object], *, semantic_scorer=None) -> dict[str, object]:
    enriched = dict(record)
    classification = classify_labor(enriched, semantic_scorer=semantic_scorer)
    enriched.update(_classification_storage(classification))
    return enriched


def _record_with_existing_excerpt(record: Mapping[str, object]) -> dict[str, object]:
    candidate = dict(record)
    if candidate.get("classification_text_excerpt") or not candidate.get("id"):
        return candidate

    existing = get_norm(str(candidate["id"]))
    if existing is not None and existing["classification_text_excerpt"]:
        candidate["classification_text_excerpt"] = str(existing["classification_text_excerpt"])
    return candidate


def upsert_norm(record: Mapping[str, object], *, semantic_scorer=None) -> dict[str, object]:
    candidate = _record_with_existing_excerpt(record)
    enriched = enrich_norm(candidate, semantic_scorer=semantic_scorer)

    if isinstance(record, dict):
        record.update(
            {
                key: enriched.get(key)
                for key in (
                    "labor_relevance",
                    "relevance_reason",
                    "classification_version",
                    "topic",
                    "classification_score",
                    "rule_score",
                    "semantic_score",
                    "semantic_model",
                    "classification_method",
                    "requires_review",
                    "classification_evidence",
                    "classification_text_excerpt",
                )
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
            topic = excluded.topic,
            status = COALESCE(excluded.status, norms.status),
            edition = COALESCE(excluded.edition, norms.edition),
            labor_relevance = excluded.labor_relevance,
            relevance_reason = excluded.relevance_reason,
            classification_version = excluded.classification_version,
            classification_score = excluded.classification_score,
            rule_score = excluded.rule_score,
            semantic_score = excluded.semantic_score,
            semantic_model = excluded.semantic_model,
            classification_method = excluded.classification_method,
            requires_review = excluded.requires_review,
            classification_evidence = excluded.classification_evidence,
            classification_text_excerpt = COALESCE(excluded.classification_text_excerpt, norms.classification_text_excerpt),
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


def _search_filters(
    source: str,
    relevance: str,
    *,
    document_type: str = "",
    issuer: str = "",
    topic: str = "",
    edition: str = "",
    date_from: str = "",
    date_to: str = "",
    alias: str = "",
) -> tuple[list[str], list[str | int]]:
    prefix = f"{alias}." if alias else ""
    clauses: list[str] = []
    params: list[str | int] = []

    exact_filters = (
        ("source", source),
        ("document_type", document_type),
        ("issuer", issuer),
        ("topic", topic),
        ("edition", edition),
    )
    for column, value in exact_filters:
        if value:
            clauses.append(f"{prefix}{column} = ?")
            params.append(value)

    if date_from:
        clauses.append(f"{prefix}publication_date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append(f"{prefix}publication_date <= ?")
        params.append(date_to)

    if relevance == "tracked":
        clauses.append(f"{prefix}labor_relevance IN ('relevant', 'review')")
    elif relevance in {"relevant", "review", "not_labor"}:
        clauses.append(f"{prefix}labor_relevance = ?")
        params.append(relevance)

    return clauses, params


def _search_norms_fts(
    conn: sqlite3.Connection,
    fts_query: str,
    source: str,
    relevance: str,
    limit: int,
    offset: int,
    *,
    document_type: str = "",
    issuer: str = "",
    topic: str = "",
    edition: str = "",
    date_from: str = "",
    date_to: str = "",
):
    clauses, params = _search_filters(
        source,
        relevance,
        document_type=document_type,
        issuer=issuer,
        topic=topic,
        edition=edition,
        date_from=date_from,
        date_to=date_to,
        alias="n",
    )
    clauses.insert(0, "norms_fts MATCH ?")
    params.insert(0, fts_query)
    where = " AND ".join(clauses)
    params.extend([limit, offset])
    return conn.execute(
        f"""
        SELECT n.*
        FROM norms_fts
        JOIN norms AS n ON n.rowid = norms_fts.rowid
        WHERE {where}
        ORDER BY bm25(norms_fts, 5.0, 4.0, 1.0, 2.0, 3.0),
                 n.publication_date DESC,
                 n.captured_at DESC
        LIMIT ? OFFSET ?
        """,
        params,
    ).fetchall()


def _search_norms_like(
    conn: sqlite3.Connection,
    query: str,
    source: str,
    relevance: str,
    limit: int,
    offset: int,
    *,
    document_type: str = "",
    issuer: str = "",
    topic: str = "",
    edition: str = "",
    date_from: str = "",
    date_to: str = "",
):
    clauses, params = _search_filters(
        source,
        relevance,
        document_type=document_type,
        issuer=issuer,
        topic=topic,
        edition=edition,
        date_from=date_from,
        date_to=date_to,
    )
    if query:
        like = f"%{query}%"
        clauses.insert(
            0,
            "(title LIKE ? OR number LIKE ? OR summary LIKE ? OR issuer LIKE ? OR topic LIKE ?)",
        )
        params[0:0] = [like, like, like, like, like]

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([limit, offset])
    return conn.execute(
        f"""
        SELECT *
        FROM norms
        {where}
        ORDER BY publication_date DESC, captured_at DESC
        LIMIT ? OFFSET ?
        """,
        params,
    ).fetchall()


def search_norms(
    query: str = "",
    source: str = "",
    relevance: str = "relevant",
    limit: int = 200,
    offset: int = 0,
    *,
    document_type: str = "",
    issuer: str = "",
    topic: str = "",
    edition: str = "",
    date_from: str = "",
    date_to: str = "",
):
    safe_limit = max(1, min(int(limit), 1000))
    safe_offset = max(0, int(offset))
    fts_query = _fts_query(query) if query else None
    filter_args = {
        "document_type": document_type,
        "issuer": issuer,
        "topic": topic,
        "edition": edition,
        "date_from": date_from,
        "date_to": date_to,
    }

    with connect() as conn:
        if fts_query and _fts_available(conn):
            try:
                return _search_norms_fts(
                    conn,
                    fts_query,
                    source,
                    relevance,
                    safe_limit,
                    safe_offset,
                    **filter_args,
                )
            except sqlite3.OperationalError:
                pass
        return _search_norms_like(
            conn,
            query,
            source,
            relevance,
            safe_limit,
            safe_offset,
            **filter_args,
        )


def _distinct_values(conn: sqlite3.Connection, column: str) -> list[str]:
    allowed = {"source", "document_type", "issuer", "topic", "edition"}
    if column not in allowed:
        raise ValueError(f"Campo de filtro no permitido: {column}")
    rows = conn.execute(
        f"SELECT DISTINCT {column} FROM norms "
        f"WHERE {column} IS NOT NULL AND {column} <> '' ORDER BY {column}"
    ).fetchall()
    return [str(row[0]) for row in rows]


def list_norm_filter_options() -> dict[str, list[str]]:
    with connect() as conn:
        return {
            "sources": _distinct_values(conn, "source"),
            "document_types": _distinct_values(conn, "document_type"),
            "issuers": _distinct_values(conn, "issuer"),
            "topics": _distinct_values(conn, "topic"),
            "editions": _distinct_values(conn, "edition"),
        }


def list_sources() -> list[str]:
    return list_norm_filter_options()["sources"]


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


def enqueue_backfill_request(
    start_date: str,
    end_date: str,
    *,
    download_pdfs: bool = False,
) -> tuple[int, bool]:
    """Queue a historical El Peruano load, deduplicating identical active requests."""
    with connect() as conn:
        existing = conn.execute(
            """
            SELECT id
            FROM sync_requests
            WHERE kind = ? AND start_date = ? AND end_date = ? AND download_pdfs = ?
              AND status IN ('pending', 'running')
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                SYNC_REQUEST_KIND_BACKFILL,
                start_date,
                end_date,
                int(download_pdfs),
            ),
        ).fetchone()
        if existing is not None:
            return int(existing["id"]), False

        cursor = conn.execute(
            """
            INSERT INTO sync_requests (
                kind, start_date, end_date, download_pdfs, status, requested_at
            ) VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (
                SYNC_REQUEST_KIND_BACKFILL,
                start_date,
                end_date,
                int(download_pdfs),
                utc_now(),
            ),
        )
        return int(cursor.lastrowid), True


def list_sync_requests(limit: int = 20):
    safe_limit = max(1, min(int(limit), 100))
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM sync_requests ORDER BY id DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()


def claim_next_sync_request():
    """Atomically claim the oldest pending request for a single worker."""
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM sync_requests WHERE status = 'pending' ORDER BY id LIMIT 1"
        ).fetchone()
        if row is None:
            conn.commit()
            return None
        now = utc_now()
        conn.execute(
            """
            UPDATE sync_requests
            SET status = 'running', started_at = ?, finished_at = NULL, error = NULL
            WHERE id = ? AND status = 'pending'
            """,
            (now, row["id"]),
        )
        claimed = conn.execute(
            "SELECT * FROM sync_requests WHERE id = ?",
            (row["id"],),
        ).fetchone()
        conn.commit()
        return claimed
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def finish_sync_request(request_id: int, *, status: str, error: str | None = None) -> None:
    if status not in {"success", "failed"}:
        raise ValueError("Estado final de solicitud no válido")
    with connect() as conn:
        conn.execute(
            """
            UPDATE sync_requests
            SET status = ?, finished_at = ?, error = ?
            WHERE id = ?
            """,
            (status, utc_now(), error, int(request_id)),
        )


def recover_running_sync_requests() -> int:
    """Return interrupted jobs to the queue; the historical upsert is idempotent."""
    with connect() as conn:
        cursor = conn.execute(
            """
            UPDATE sync_requests
            SET status = 'pending', started_at = NULL, finished_at = NULL,
                error = 'Reencolado después de reinicio del worker'
            WHERE status = 'running'
            """
        )
        return int(cursor.rowcount)


def norm_date_bounds() -> dict[str, str | None]:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT MIN(publication_date) AS earliest, MAX(publication_date) AS latest
            FROM norms
            WHERE publication_date IS NOT NULL AND publication_date <> ''
            """
        ).fetchone()
    return {
        "earliest": str(row["earliest"]) if row and row["earliest"] else None,
        "latest": str(row["latest"]) if row and row["latest"] else None,
    }


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
