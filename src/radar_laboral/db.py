from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Mapping

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
    "official_url",
    "pdf_url",
    "pdf_path",
    "sha256",
    "captured_at",
    "updated_at",
)


def data_dir() -> Path:
    path = Path(os.getenv("RADAR_DATA_DIR", "storage")).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    (path / "pdfs").mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "radar_laboral.db"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def upsert_norm(record: Mapping[str, object]) -> None:
    values = [record.get(column) for column in NORM_COLUMNS]
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
            official_url = excluded.official_url,
            pdf_url = COALESCE(excluded.pdf_url, norms.pdf_url),
            pdf_path = COALESCE(excluded.pdf_path, norms.pdf_path),
            sha256 = COALESCE(excluded.sha256, norms.sha256),
            updated_at = COALESCE(excluded.updated_at, norms.updated_at)
    """
    with connect() as conn:
        conn.execute(sql, values)


def get_norm(norm_id: str):
    with connect() as conn:
        return conn.execute("SELECT * FROM norms WHERE id = ?", (norm_id,)).fetchone()


def search_norms(query: str = "", source: str = "", limit: int = 200):
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
