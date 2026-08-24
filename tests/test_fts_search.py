from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from radar_laboral.db import (
    _fts_available,
    connect,
    init_db,
    search_norms,
    upsert_norm,
)


def norm(
    norm_id: str,
    *,
    title: str,
    number: str,
    issuer: str = "TRABAJO Y PROMOCIÓN DEL EMPLEO",
    publication_date: str = "2026-08-01",
) -> dict[str, object]:
    return {
        "id": norm_id,
        "source": "El Peruano",
        "document_type": "DECRETO SUPREMO",
        "number": number,
        "title": title,
        "summary": None,
        "publication_date": publication_date,
        "effective_date": None,
        "issuer": issuer,
        "topic": None,
        "status": None,
        "edition": "regular",
        "official_url": f"https://example.invalid/{norm_id}",
        "pdf_url": None,
        "pdf_path": None,
        "sha256": None,
        "captured_at": f"{publication_date}T12:00:00+00:00",
        "updated_at": f"{publication_date}T12:00:00+00:00",
    }


class FtsSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_data_dir = os.environ.get("RADAR_DATA_DIR")
        os.environ["RADAR_DATA_DIR"] = self.tmp.name
        init_db()

    def tearDown(self) -> None:
        if self.old_data_dir is None:
            os.environ.pop("RADAR_DATA_DIR", None)
        else:
            os.environ["RADAR_DATA_DIR"] = self.old_data_dir
        self.tmp.cleanup()

    def _require_fts5(self) -> None:
        with connect() as conn:
            if not _fts_available(conn):
                self.skipTest("SQLite de este entorno no incluye FTS5")

    def test_prefix_and_diacritic_insensitive_search(self) -> None:
        self._require_fts5()
        upsert_norm(
            norm(
                "fts:1",
                title="Regulan compensación y teletrabajo para trabajadores",
                number="001-2026-TR",
            )
        )

        accentless = search_norms("compensacion", relevance="relevant")
        prefix = search_norms("teletra", relevance="relevant")
        by_number = search_norms("001 2026 TR", relevance="relevant")

        self.assertEqual([row["id"] for row in accentless], ["fts:1"])
        self.assertEqual([row["id"] for row in prefix], ["fts:1"])
        self.assertEqual([row["id"] for row in by_number], ["fts:1"])

    def test_fts_index_tracks_database_updates(self) -> None:
        self._require_fts5()
        upsert_norm(
            norm(
                "fts:update",
                title="Regulan teletrabajo en el sector privado",
                number="002-2026-TR",
            )
        )
        self.assertEqual(len(search_norms("teletrabajo", relevance="relevant")), 1)

        with connect() as conn:
            conn.execute(
                "UPDATE norms SET title = ?, topic = ? WHERE id = ?",
                ("Regulan jornada remota en el sector privado", "Jornada", "fts:update"),
            )

        self.assertEqual(search_norms("teletrabajo", relevance="relevant"), [])
        self.assertEqual(
            [row["id"] for row in search_norms("jornada remota", relevance="relevant")],
            ["fts:update"],
        )

    def test_fts_respects_source_and_relevance_filters(self) -> None:
        self._require_fts5()
        upsert_norm(
            norm(
                "fts:relevant",
                title="Regulan teletrabajo y jornada laboral",
                number="003-2026-TR",
            )
        )
        upsert_norm(
            norm(
                "fts:not-labor",
                title="Designan representante para comisión institucional",
                number="004-2026-PCM",
                issuer="PRESIDENCIA DEL CONSEJO DE MINISTROS",
            )
        )

        relevant = search_norms("teletrabajo", source="El Peruano", relevance="relevant")
        discarded = search_norms("representante", source="El Peruano", relevance="not_labor")
        wrong_source = search_norms("teletrabajo", source="Otra fuente", relevance="relevant")

        self.assertEqual([row["id"] for row in relevant], ["fts:relevant"])
        self.assertEqual([row["id"] for row in discarded], ["fts:not-labor"])
        self.assertEqual(wrong_source, [])

    def test_like_fallback_keeps_search_working_without_fts(self) -> None:
        upsert_norm(
            norm(
                "fts:fallback",
                title="Regulan teletrabajo especial",
                number="005-2026-TR",
            )
        )

        with patch("radar_laboral.db._fts_available", return_value=False):
            rows = search_norms("teletrabajo", relevance="relevant")

        self.assertEqual([row["id"] for row in rows], ["fts:fallback"])

    def test_existing_rows_are_indexed_when_fts_is_created(self) -> None:
        self._require_fts5()
        db_path = Path(self.tmp.name) / "radar_laboral.db"
        with sqlite3.connect(db_path) as conn:
            conn.execute("DROP TRIGGER IF EXISTS norms_fts_ai")
            conn.execute("DROP TRIGGER IF EXISTS norms_fts_ad")
            conn.execute("DROP TRIGGER IF EXISTS norms_fts_au")
            conn.execute("DROP TABLE IF EXISTS norms_fts")
            conn.execute(
                """
                INSERT INTO norms (
                    id, source, document_type, number, title, publication_date,
                    issuer, labor_relevance, relevance_reason, classification_version,
                    official_url, captured_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "fts:legacy",
                    "El Peruano",
                    "DECRETO SUPREMO",
                    "006-2026-TR",
                    "Regulan compensación por tiempo de servicios",
                    "2026-07-31",
                    "TRABAJO Y PROMOCIÓN DEL EMPLEO",
                    "relevant",
                    "fixture",
                    2,
                    "https://example.invalid/fts-legacy",
                    "2026-07-31T12:00:00+00:00",
                ),
            )

        init_db()
        rows = search_norms("compensacion", relevance="relevant")
        self.assertEqual([row["id"] for row in rows], ["fts:legacy"])


if __name__ == "__main__":
    unittest.main()
