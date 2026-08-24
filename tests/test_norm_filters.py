from __future__ import annotations

import os
import tempfile
import unittest

from radar_laboral.db import init_db, list_norm_filter_options, search_norms, upsert_norm


def record(
    norm_id: str,
    *,
    title: str,
    document_type: str,
    issuer: str,
    publication_date: str,
    edition: str,
    source: str = "El Peruano",
) -> dict[str, object]:
    return {
        "id": norm_id,
        "source": source,
        "document_type": document_type,
        "number": f"{norm_id}-2026",
        "title": title,
        "summary": None,
        "publication_date": publication_date,
        "effective_date": None,
        "issuer": issuer,
        "topic": None,
        "status": None,
        "edition": edition,
        "official_url": f"https://example.invalid/{norm_id}",
        "pdf_url": None,
        "pdf_path": None,
        "sha256": None,
        "captured_at": f"{publication_date}T12:00:00+00:00",
        "updated_at": f"{publication_date}T12:00:00+00:00",
    }


class NormFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_data_dir = os.environ.get("RADAR_DATA_DIR")
        os.environ["RADAR_DATA_DIR"] = self.tmp.name
        init_db()

        upsert_norm(
            record(
                "filter-a",
                title="Regulan teletrabajo para trabajadores",
                document_type="DECRETO SUPREMO",
                issuer="TRABAJO Y PROMOCIÓN DEL EMPLEO",
                publication_date="2026-08-01",
                edition="regular",
            )
        )
        upsert_norm(
            record(
                "filter-b",
                title="Regulan jornada laboral y horas extras",
                document_type="RESOLUCIÓN MINISTERIAL",
                issuer="TRABAJO Y PROMOCIÓN DEL EMPLEO",
                publication_date="2026-08-02",
                edition="extraordinary",
            )
        )
        upsert_norm(
            record(
                "filter-c",
                title="Modifican reglas sobre vacaciones de trabajadores",
                document_type="LEY",
                issuer="CONGRESO DE LA REPÚBLICA",
                publication_date="2026-08-03",
                edition="regular",
                source="Archivo oficial",
            )
        )

    def tearDown(self) -> None:
        if self.old_data_dir is None:
            os.environ.pop("RADAR_DATA_DIR", None)
        else:
            os.environ["RADAR_DATA_DIR"] = self.old_data_dir
        self.tmp.cleanup()

    def ids(self, **kwargs) -> list[str]:
        return [row["id"] for row in search_norms(relevance="all", **kwargs)]

    def test_exact_metadata_filters(self) -> None:
        self.assertEqual(self.ids(source="Archivo oficial"), ["filter-c"])
        self.assertEqual(self.ids(document_type="RESOLUCIÓN MINISTERIAL"), ["filter-b"])
        self.assertEqual(self.ids(issuer="CONGRESO DE LA REPÚBLICA"), ["filter-c"])
        self.assertEqual(self.ids(topic="Teletrabajo"), ["filter-a"])
        self.assertEqual(self.ids(edition="extraordinary"), ["filter-b"])

    def test_date_range_is_inclusive(self) -> None:
        self.assertEqual(
            self.ids(date_from="2026-08-02", date_to="2026-08-02"),
            ["filter-b"],
        )
        self.assertEqual(
            self.ids(date_from="2026-08-02", date_to="2026-08-03"),
            ["filter-c", "filter-b"],
        )

    def test_filters_combine_with_full_text_search(self) -> None:
        rows = search_norms(
            query="regulan",
            relevance="relevant",
            edition="extraordinary",
            issuer="TRABAJO Y PROMOCIÓN DEL EMPLEO",
        )
        self.assertEqual([row["id"] for row in rows], ["filter-b"])

    def test_offset_applies_after_filtering(self) -> None:
        first = search_norms(relevance="all", limit=1, offset=0)
        second = search_norms(relevance="all", limit=1, offset=1)
        self.assertEqual([row["id"] for row in first], ["filter-c"])
        self.assertEqual([row["id"] for row in second], ["filter-b"])

        filtered = search_norms(
            query="regulan",
            relevance="relevant",
            issuer="TRABAJO Y PROMOCIÓN DEL EMPLEO",
            limit=1,
            offset=1,
        )
        self.assertEqual([row["id"] for row in filtered], ["filter-a"])

    def test_negative_offset_is_clamped_to_zero(self) -> None:
        rows = search_norms(relevance="all", limit=1, offset=-50)
        self.assertEqual([row["id"] for row in rows], ["filter-c"])

    def test_filter_options_are_distinct_and_sorted(self) -> None:
        options = list_norm_filter_options()
        self.assertEqual(options["sources"], ["Archivo oficial", "El Peruano"])
        self.assertIn("DECRETO SUPREMO", options["document_types"])
        self.assertIn("CONGRESO DE LA REPÚBLICA", options["issuers"])
        self.assertIn("Teletrabajo", options["topics"])
        self.assertEqual(options["editions"], ["extraordinary", "regular"])


if __name__ == "__main__":
    unittest.main()
