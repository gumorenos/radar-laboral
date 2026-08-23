from __future__ import annotations

import unittest
from datetime import date

from radar_laboral.collectors.el_peruano_history import (
    _search_params,
    fetch_day,
    parse_search_html,
)


def result_html(op: str, heading: str, summary: str, *, issuer: str = "TRABAJO Y PROMOCIÓN DEL EMPLEO") -> str:
    return f"""
    <div class="result">
      <h4>{issuer}</h4>
      <a href="/dispositivo/NL/{op}">{heading}</a>
      <a href="/dispositivo/NL/{op}">{summary}</a>
      <span>{op} sábado 01.08.2026</span>
    </div>
    """


class _Response:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self) -> None:
        return None


class _Session:
    def __init__(self, pages: dict[int, str]):
        self.pages = pages
        self.starts: list[int] = []

    def get(self, url, *, params, timeout):
        start = int(params["start"])
        self.starts.append(start)
        return _Response(self.pages[start])


class ElPeruanoHistoricalTests(unittest.TestCase):
    def test_parses_numbered_and_unnumbered_devices(self) -> None:
        html = (
            "<div>2 dispositivos encontrados</div>"
            + result_html(
                "2539375-4",
                "RESOLUCIÓN SUPREMA N° 248-2026-PCM",
                "Aceptan renuncia de Secretaria de la Secretaría del Consejo de Ministros",
                issuer="PRESIDENCIA DEL CONSEJO DE MINISTROS",
            )
            + result_html(
                "2539300-1",
                "ACUERDO del Pleno",
                "Modifican el cronograma electoral aprobado mediante Acuerdo",
                issuer="JURADO NACIONAL DE ELECCIONES",
            )
        )

        records, total = parse_search_html(html, captured_at="2026-08-23T05:00:00+00:00")
        self.assertEqual(total, 2)
        self.assertEqual(len(records), 2)

        numbered = next(item for item in records if item["id"] == "elperuano:2539375-4")
        self.assertEqual(numbered["document_type"], "RESOLUCIÓN SUPREMA")
        self.assertEqual(numbered["number"], "248-2026-PCM")
        self.assertEqual(numbered["publication_date"], "2026-08-01")
        self.assertEqual(numbered["issuer"], "PRESIDENCIA DEL CONSEJO DE MINISTROS")
        self.assertTrue(str(numbered["title"]).startswith("Aceptan renuncia"))

        unnumbered = next(item for item in records if item["id"] == "elperuano:2539300-1")
        self.assertEqual(unnumbered["document_type"], "ACUERDO del Pleno")
        self.assertIsNone(unnumbered["number"])
        self.assertEqual(unnumbered["issuer"], "JURADO NACIONAL DE ELECCIONES")

    def test_search_params_match_official_date_search(self) -> None:
        params = _search_params(date(2026, 8, 1), 20)
        self.assertEqual(
            params,
            {
                "ci": "ONLY",
                "fechaFin": "20260801",
                "fechaIni": "20260801",
                "start": 20,
                "tipoPublicacion": "NL",
            },
        )

    def test_fetch_day_paginates_in_twenty_record_pages(self) -> None:
        first_page_items = "".join(
            result_html(
                f"2539{i:03d}-1",
                f"RESOLUCIÓN MINISTERIAL N° {i:03d}-2026-TR",
                f"Aprueban disposición laboral número {i}",
            )
            for i in range(20)
        )
        second_page_item = result_html(
            "2539999-1",
            "DECRETO SUPREMO N° 999-2026-TR",
            "Aprueban disposición final sobre teletrabajo",
        )
        session = _Session(
            {
                0: "<div>21 dispositivos encontrados</div>" + first_page_items,
                20: "<div>21 dispositivos encontrados</div>" + second_page_item,
            }
        )

        records = fetch_day(session, date(2026, 8, 1), page_delay_seconds=0)
        self.assertEqual(len(records), 21)
        self.assertEqual(session.starts, [0, 20])


if __name__ == "__main__":
    unittest.main()
