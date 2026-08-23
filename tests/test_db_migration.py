from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from radar_laboral.db import init_db


LEGACY_SCHEMA = """
CREATE TABLE norms (
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
"""


class DatabaseMigrationTests(unittest.TestCase):
    def test_legacy_database_is_migrated_and_backfilled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "radar_laboral.db"
            with sqlite3.connect(db_path) as conn:
                conn.executescript(LEGACY_SCHEMA)
                conn.execute(
                    """
                    INSERT INTO norms (
                        id, source, document_type, number, title, publication_date,
                        issuer, official_url, captured_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "legacy:1",
                        "El Peruano",
                        "DECRETO SUPREMO",
                        "001-2026-TR",
                        "Modifican disposiciones sobre teletrabajo",
                        "2026-08-22",
                        "TRABAJO Y PROMOCIÓN DEL EMPLEO",
                        "https://example.invalid/1",
                        "2026-08-22T00:00:00+00:00",
                    ),
                )

            old_value = os.environ.get("RADAR_DATA_DIR")
            os.environ["RADAR_DATA_DIR"] = tmp
            try:
                init_db()
            finally:
                if old_value is None:
                    os.environ.pop("RADAR_DATA_DIR", None)
                else:
                    os.environ["RADAR_DATA_DIR"] = old_value

            with sqlite3.connect(db_path) as conn:
                columns = {row[1] for row in conn.execute("PRAGMA table_info(norms)")}
                row = conn.execute(
                    "SELECT labor_relevance, relevance_reason, topic FROM norms WHERE id = 'legacy:1'"
                ).fetchone()

            self.assertIn("labor_relevance", columns)
            self.assertIn("relevance_reason", columns)
            self.assertEqual(row[0], "relevant")
            self.assertIn("materia laboral específica", row[1])
            self.assertIn("Teletrabajo", row[2])


if __name__ == "__main__":
    unittest.main()
