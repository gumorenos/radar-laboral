from __future__ import annotations

import os
import sqlite3
from pathlib import Path

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
"""


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
