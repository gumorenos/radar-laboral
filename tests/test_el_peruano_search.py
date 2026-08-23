from __future__ import annotations

import unittest
from datetime import date

from radar_laboral.collectors.el_peruano_search import (
    SearchCollectorError,
    _search_params,
    fetch_publication_type,
    parse_search_html,
)


RESULT_HTML = """
<html><body>
  <div>Dispositivos del 29/07/2026 al 29/07/2026</div>
  <div>2 dispositivos encontrados</div>
  <h3>ECONOMÍA Y FINANZAS</h3>
  <article>
    <a href="/dispositivo/NL/2538528-1">RESOLUCIÓN DIRECTORAL N° 0021-2026-EF/50.01</a>
    <a href="/dispositivo/NL/2538528-1">Resolución Directoral que modifica un anexo</a>
    <span>2538528-1</span>
    <span>miércoles 29.07.2026</span>
  </article>
  <h3>SUPERINTENDENCIA NACIONAL DE ADUANAS Y DE ADMINISTRACIÓN TRIBUTARIA</h3>
  <article>
    <a href="/dispositivo/EX/2538529-1">RESOLUCIÓN N° 000123-2026/SUNAT</a>
    <a href="/dispositivo/EX/2538529-1">Aprueban disposiciones extraordinarias</a>
    <span>2538529-1</span>
    <span>miércoles 29.07.2026</span>
  </article>
</body></html>
"""

EMPTY_HTML = """
<html><body>
  <div>Búsquedas El Peruano</div>
  <div>No hay resultados para mostrar.</div>
  <div>Cargando…</div>
</body></html>
"""

UNKNOWN_HTML = "<html><body><div>Cargando…</div></body></html>"


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[tuple[str, dict[str, str | int]]] = []

    def get(self, url: str, *, params: dict[str, str | int], timeout: int):
        self.calls.append((url, params))
        return FakeResponse(self.text)


class ElPeruanoSearchTests(unittest.TestCase):
    def test_parses_total_and_devices(self) -> None:
        records, total, explicit_empty = parse_search_html(
            RESULT_HTML,
            captured_at="2026-08-23T00:00:00+00:00",
        )

        self.assertEqual(total, 2)
        self.assertFalse(explicit_empty)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["publication_date"], "2026-07-29")
        self.assertEqual(records[0]["id"], "elperuano:2538528-1")
        self.assertEqual(records[0]["number"], "0021-2026-EF/50.01")
        self.assertEqual(records[1]["id"], "elperuano:2538529-1")

    def test_recognizes_explicit_empty_state(self) -> None:
        records, total, explicit_empty = parse_search_html(EMPTY_HTML)
        self.assertEqual(records, [])
        self.assertIsNone(total)
        self.assertTrue(explicit_empty)

    def test_empty_state_is_successful_zero_records(self) -> None:
        session = FakeSession(EMPTY_HTML)
        records = fetch_publication_type(
            session,
            date(2026, 8, 23),
            "NL",
            "regular",
            page_delay_seconds=0,
        )
        self.assertEqual(records, [])
        self.assertEqual(session.calls[0][1]["fechaIni"], "20260823")
        self.assertEqual(session.calls[0][1]["tipoPublicacion"], "NL")

    def test_unknown_empty_html_still_fails(self) -> None:
        session = FakeSession(UNKNOWN_HTML)
        with self.assertRaises(SearchCollectorError):
            fetch_publication_type(
                session,
                date(2026, 8, 23),
                "NL",
                "regular",
                page_delay_seconds=0,
            )

    def test_search_params_are_date_scoped(self) -> None:
        self.assertEqual(
            _search_params(date(2026, 7, 29), 20, "EX"),
            {
                "ci": "ONLY",
                "fechaFin": "20260729",
                "fechaIni": "20260729",
                "start": 20,
                "tipoPublicacion": "EX",
            },
        )


if __name__ == "__main__":
    unittest.main()
