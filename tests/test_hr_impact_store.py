from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from radar_laboral.db import connect, get_norm, init_db, search_norms, upsert_norm
from radar_laboral.hr_impact_store import (
    get_hr_impact,
    impacts_for_records,
    init_hr_impact_store,
)


def norm_record(norm_id: str, title: str) -> dict[str, object]:
    return {
        "id": norm_id,
        "source": "El Peruano",
        "document_type": "DECRETO SUPREMO",
        "number": "009-2026-TR",
        "title": title,
        "publication_date": "2026-07-22",
        "issuer": "TRABAJO Y PROMOCIÓN DEL EMPLEO",
        "official_url": f"https://example.invalid/{norm_id}",
        "captured_at": "2026-07-22T12:00:00+00:00",
    }


class HrImpactStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"RADAR_DATA_DIR": self.tmp.name}, clear=False)
        self.env.start()
        init_db()
        init_hr_impact_store()

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def test_impact_is_persisted_and_reused_when_inputs_are_unchanged(self) -> None:
        upsert_norm(norm_record("impact:1", "Decreto Supremo que modifica el Reglamento de la Ley del Teletrabajo"))
        first = get_hr_impact("impact:1")
        self.assertIsNotNone(first)
        self.assertEqual(first["hr_impact_level"], "high")

        with patch("radar_laboral.hr_impact_store.assess_hr_impact") as assessor:
            second = get_hr_impact("impact:1")

        assessor.assert_not_called()
        self.assertEqual(second["input_fingerprint"], first["input_fingerprint"])
        self.assertEqual(second["assessed_at"], first["assessed_at"])

    def test_changed_classifier_inputs_invalidate_cached_impact(self) -> None:
        base = norm_record("impact:2", "Aprueban lineamientos institucionales")
        upsert_norm(base)
        first = get_hr_impact("impact:2")
        self.assertIsNotNone(first)

        changed = norm_record(
            "impact:2",
            "Decreto Supremo que modifica el Reglamento de la Ley del Teletrabajo",
        )
        upsert_norm(changed)
        second = get_hr_impact("impact:2")

        self.assertIsNotNone(second)
        self.assertNotEqual(second["input_fingerprint"], first["input_fingerprint"])
        self.assertEqual(second["hr_impact_scope"], "direct")
        self.assertEqual(second["hr_impact_level"], "high")

    def test_batch_helper_accepts_sqlite_rows_without_reloading_norms(self) -> None:
        upsert_norm(norm_record("impact:3", "Decreto Supremo que modifica el Reglamento de la Ley del Teletrabajo"))
        rows = search_norms(relevance="tracked", limit=10)

        with patch("radar_laboral.hr_impact_store.get_norm") as get_norm_mock:
            impacts = impacts_for_records(rows)

        get_norm_mock.assert_not_called()
        self.assertIn("impact:3", impacts)
        self.assertEqual(impacts["impact:3"]["hr_impact_level"], "high")

    def test_not_labor_rows_are_not_persisted_as_fake_impact(self) -> None:
        upsert_norm(norm_record("impact:4", "Designan Asesor del Despacho Ministerial"))
        row = get_norm("impact:4")
        self.assertEqual(row["labor_relevance"], "not_labor")

        impacts = impacts_for_records([row])

        self.assertEqual(impacts, {})
        self.assertIsNone(get_hr_impact("impact:4"))
        with connect() as conn:
            stored = conn.execute(
                "SELECT 1 FROM norm_hr_impact WHERE norm_id = ?",
                ("impact:4",),
            ).fetchone()
        self.assertIsNone(stored)

    def test_store_initialization_preserves_existing_database(self) -> None:
        upsert_norm(norm_record("impact:existing", "Decreto Supremo que regula el teletrabajo"))
        before = dict(get_norm("impact:existing"))
        with connect() as conn:
            conn.execute("DROP TABLE norm_hr_impact")

        init_hr_impact_store()

        after = dict(get_norm("impact:existing"))
        self.assertEqual(after, before)
        with connect() as conn:
            table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'norm_hr_impact'"
            ).fetchone()
        self.assertIsNotNone(table)

    def test_missing_norm_returns_none(self) -> None:
        self.assertIsNone(get_hr_impact("missing"))


if __name__ == "__main__":
    unittest.main()
