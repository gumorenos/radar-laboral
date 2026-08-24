from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from radar_laboral.app import create_app
from radar_laboral.coverage import mark_coverage_day
from radar_laboral.db import finish_sync_run, start_sync_run, upsert_norm


def _record(
    record_id: str,
    title: str,
    issuer: str,
    document_type: str = "RESOLUCIÓN",
    *,
    publication_date: str = "2026-08-23",
    edition: str = "regular",
) -> dict[str, object]:
    return {
        "id": record_id,
        "source": "El Peruano",
        "document_type": document_type,
        "number": None,
        "title": title,
        "summary": None,
        "publication_date": publication_date,
        "effective_date": None,
        "issuer": issuer,
        "topic": None,
        "status": None,
        "edition": edition,
        "official_url": f"https://example.invalid/{record_id}",
        "pdf_url": None,
        "pdf_path": None,
        "sha256": None,
        "captured_at": f"{publication_date}T05:00:00+00:00",
        "updated_at": f"{publication_date}T05:00:00+00:00",
    }


class AppStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            os.environ,
            {
                "RADAR_DATA_DIR": self.tmp.name,
                "RADAR_ADMIN_TOKEN": "",
                "RADAR_COVERAGE_DAYS": "3",
            },
            clear=False,
        )
        self.env.start()
        self.app = create_app()
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def test_health_endpoint(self) -> None:
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_home_defaults_to_relevant_and_review_records(self) -> None:
        upsert_norm(
            _record(
                "relevant",
                "Modifican disposiciones sobre teletrabajo y jornada laboral",
                "PODER EJECUTIVO",
                "DECRETO SUPREMO",
            )
        )
        upsert_norm(
            _record(
                "review",
                "Aprueban lineamientos institucionales para el año 2026",
                "TRABAJO Y PROMOCIÓN DEL EMPLEO",
            )
        )
        upsert_norm(
            _record(
                "not-labor",
                "Aprueban medidas relacionadas con trabajadores de la entidad",
                "OTRA ENTIDAD",
            )
        )

        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"teletrabajo", response.data)
        self.assertIn(b"lineamientos institucionales", response.data)
        self.assertNotIn(b"trabajadores de la entidad", response.data)
        self.assertIn(b"Laborales + por revisar", response.data)
        self.assertIn(b"Filtros avanzados", response.data)
        self.assertIn(b"Cobertura verificada:", response.data)
        self.assertIn(b"primera fecha faltante", response.data.lower())

    def test_home_explains_when_inventory_has_no_tracked_records(self) -> None:
        upsert_norm(
            _record(
                "not-labor",
                "Aprueban medidas internas de la entidad",
                "OTRA ENTIDAD",
            )
        )
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"ninguno est", response.data)
        self.assertIn(b"cobertura hist", response.data.lower())

    def test_home_applies_advanced_filters(self) -> None:
        upsert_norm(
            _record(
                "regular",
                "Regulan teletrabajo regular",
                "TRABAJO Y PROMOCIÓN DEL EMPLEO",
                "DECRETO SUPREMO",
                publication_date="2026-08-20",
                edition="regular",
            )
        )
        upsert_norm(
            _record(
                "extraordinary",
                "Regulan jornada laboral extraordinaria",
                "TRABAJO Y PROMOCIÓN DEL EMPLEO",
                "RESOLUCIÓN MINISTERIAL",
                publication_date="2026-08-21",
                edition="extraordinary",
            )
        )

        response = self.client.get(
            "/",
            query_string={
                "relevance": "all",
                "edition": "extraordinary",
                "document_type": "RESOLUCIÓN MINISTERIAL",
                "date_from": "2026-08-21",
                "date_to": "2026-08-21",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"jornada laboral extraordinaria", response.data)
        self.assertNotIn(b"teletrabajo regular", response.data)
        self.assertIn(b"Filtros avanzados", response.data)
        self.assertIn(b"activos", response.data)
        self.assertIn(b"Extraordinaria", response.data)

    def test_home_paginates_and_preserves_search_filters(self) -> None:
        start = date(2026, 1, 1)
        for index in range(52):
            publication_date = (start + timedelta(days=index)).isoformat()
            upsert_norm(
                _record(
                    f"page-{index:02d}",
                    f"Norma paginada {index:02d} sobre teletrabajo",
                    "TRABAJO Y PROMOCIÓN DEL EMPLEO",
                    "DECRETO SUPREMO",
                    publication_date=publication_date,
                    edition="regular",
                )
            )

        query = {
            "q": "teletrabajo",
            "relevance": "relevant",
            "edition": "regular",
        }
        first = self.client.get("/", query_string=query)
        self.assertEqual(first.status_code, 200)
        self.assertIn(b"Norma paginada 51", first.data)
        self.assertNotIn(b"Norma paginada 01", first.data)
        self.assertIn(b"Siguiente", first.data)
        self.assertIn(b"page=2", first.data)
        self.assertIn(b"edition=regular", first.data)
        self.assertIn(b"q=teletrabajo", first.data)

        second = self.client.get("/", query_string={**query, "page": "2"})
        self.assertEqual(second.status_code, 200)
        self.assertIn(b"Norma paginada 01", second.data)
        self.assertIn(b"Norma paginada 00", second.data)
        self.assertNotIn(b"Norma paginada 02", second.data)
        self.assertIn("Página 2".encode(), second.data)
        self.assertIn(b"Anterior", second.data)
        self.assertNotIn(b"page=3", second.data)

    def test_invalid_page_falls_back_to_first_page(self) -> None:
        response = self.client.get("/", query_string={"page": "abc"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Página 2".encode(), response.data)

    def test_status_api_reports_latest_sync_date_bounds_and_coverage(self) -> None:
        fixed_today = date(2026, 8, 24)
        upsert_norm(
            _record(
                "dated",
                "Regulan teletrabajo",
                "TRABAJO Y PROMOCIÓN DEL EMPLEO",
                publication_date="2026-07-22",
            )
        )
        closed_day = fixed_today - timedelta(days=1)
        mark_coverage_day(closed_day, record_count=3, relevant_count=1, is_complete=True)
        run_id = start_sync_run("El Peruano")
        finish_sync_run(
            run_id,
            status="success",
            records_seen=3,
            relevant_count=1,
            review_count=1,
            pdf_count=2,
            latest_publication_date="2026-08-23",
        )

        with patch("radar_laboral.app._local_today", return_value=fixed_today):
            response = self.client.get("/api/status")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["last_sync"]["status"], "success")
        self.assertEqual(payload["last_sync"]["records_seen"], 3)
        self.assertEqual(payload["date_bounds"]["earliest"], "2026-07-22")
        self.assertIn("stats", payload)
        self.assertEqual(payload["sync_requests"], [])
        self.assertIn("coverage", payload)
        self.assertEqual(payload["coverage"]["target_days"], 3)
        self.assertEqual(payload["coverage"]["verified_days"], 1)
        self.assertEqual(payload["coverage"]["window_end"], "2026-08-23")

    def test_status_page_renders_coverage_and_historical_selector_state(self) -> None:
        response = self.client.get("/status")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Estado del Radar", response.data)
        self.assertIn(b"Cobertura diaria verificada", response.data)
        self.assertIn(b"Carga hist", response.data)
        self.assertIn(b"Traer desde", response.data)
        self.assertIn(b"RADAR_ADMIN_TOKEN", response.data)


if __name__ == "__main__":
    unittest.main()
