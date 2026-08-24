from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from radar_laboral.classifier import CLASSIFIER_VERSION
from radar_laboral.db import init_db, upsert_norm


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

VERSIONED_V1_SCHEMA = """
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
    labor_relevance TEXT,
    relevance_reason TEXT,
    classification_version INTEGER,
    official_url TEXT NOT NULL,
    pdf_url TEXT,
    pdf_path TEXT,
    sha256 TEXT,
    captured_at TEXT NOT NULL,
    updated_at TEXT
);
"""


class DatabaseMigrationTests(unittest.TestCase):
    def _run_init(self, tmp: str) -> None:
        old_value = os.environ.get("RADAR_DATA_DIR")
        os.environ["RADAR_DATA_DIR"] = tmp
        try:
            init_db()
        finally:
            if old_value is None:
                os.environ.pop("RADAR_DATA_DIR", None)
            else:
                os.environ["RADAR_DATA_DIR"] = old_value

    def _with_data_dir(self, tmp: str):
        class EnvGuard:
            def __enter__(inner_self):
                inner_self.old = os.environ.get("RADAR_DATA_DIR")
                os.environ["RADAR_DATA_DIR"] = tmp

            def __exit__(inner_self, exc_type, exc, tb):
                if inner_self.old is None:
                    os.environ.pop("RADAR_DATA_DIR", None)
                else:
                    os.environ["RADAR_DATA_DIR"] = inner_self.old

        return EnvGuard()

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

            self._run_init(tmp)

            with sqlite3.connect(db_path) as conn:
                columns = {row[1] for row in conn.execute("PRAGMA table_info(norms)")}
                row = conn.execute(
                    "SELECT labor_relevance, relevance_reason, topic, classification_version "
                    "FROM norms WHERE id = 'legacy:1'"
                ).fetchone()

            self.assertIn("labor_relevance", columns)
            self.assertIn("relevance_reason", columns)
            self.assertIn("classification_version", columns)
            self.assertIn("edition", columns)
            self.assertEqual(row[0], "relevant")
            self.assertIn("materia laboral específica", row[1])
            self.assertIn("Teletrabajo", row[2])
            self.assertEqual(row[3], CLASSIFIER_VERSION)

    def test_old_classification_is_recomputed_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "radar_laboral.db"
            with sqlite3.connect(db_path) as conn:
                conn.executescript(VERSIONED_V1_SCHEMA)
                conn.execute(
                    """
                    INSERT INTO norms (
                        id, source, document_type, title, publication_date, issuer,
                        labor_relevance, relevance_reason, classification_version,
                        official_url, captured_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "legacy:generic",
                        "El Peruano",
                        "RESOLUCIÓN",
                        "Aprueban medidas relacionadas con trabajadores de la entidad",
                        "2026-08-22",
                        "OTRA ENTIDAD",
                        "review",
                        "terminología laboral general",
                        1,
                        "https://example.invalid/generic",
                        "2026-08-22T00:00:00+00:00",
                    ),
                )

            self._run_init(tmp)

            with sqlite3.connect(db_path) as conn:
                row = conn.execute(
                    "SELECT labor_relevance, classification_version FROM norms "
                    "WHERE id = 'legacy:generic'"
                ).fetchone()
                columns = {item[1] for item in conn.execute("PRAGMA table_info(norms)")}

            self.assertEqual(row[0], "not_labor")
            self.assertEqual(row[1], CLASSIFIER_VERSION)
            self.assertIn("edition", columns)

    def test_upsert_persists_edition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self._with_data_dir(tmp):
            init_db()
            upsert_norm(
                {
                    "id": "edition:1",
                    "source": "El Peruano",
                    "document_type": "DECRETO SUPREMO",
                    "number": "001-2026-TR",
                    "title": "Modifican disposiciones sobre teletrabajo",
                    "publication_date": "2026-08-22",
                    "issuer": "TRABAJO Y PROMOCIÓN DEL EMPLEO",
                    "edition": "extraordinary",
                    "official_url": "https://example.invalid/edition-1",
                    "captured_at": "2026-08-22T00:00:00+00:00",
                }
            )

            with sqlite3.connect(Path(tmp) / "radar_laboral.db") as conn:
                edition = conn.execute(
                    "SELECT edition FROM norms WHERE id = 'edition:1'"
                ).fetchone()[0]

            self.assertEqual(edition, "extraordinary")


if __name__ == "__main__":
    unittest.main()
