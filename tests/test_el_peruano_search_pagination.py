from __future__ import annotations

import unittest
from datetime import date

from radar_laboral.collectors.el_peruano_search import (
    SearchCollectorError,
    fetch_day,
    fetch_publication_type,
    parse_search_html,
)


def result_html(
    op: str,
    heading: str,
    summary: str,
    *,
    issuer: str = "TRABAJO Y PROMOCIÓN DEL EMPLEO",
    publication_type: str = "NL",
) -> str:
    return f"""
    <div class="result">
      <h4>{issuer}</h4>
      <a href="/dispositivo/{publication_type}/{op}">{heading}</a>
      <a href="/dispositivo/{publication_type}/{op}">{summary}</a>
      <span>{op} sábado 01.08.2026</span>
    </div>
    """


class _Response:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self) -> None:
        return None


class _Session:
    def __init__(self, pages: dict[tuple[str, int], str]):
        self.pages = pages
        self.requests: list[tuple[str, int]] = []

    def get(self, url, *, params, timeout):
        key = (str(params["tipoPublicacion"]), int(params["start"]))
        self.requests.append(key)
        return _Response(self.pages[key])


class ElPeruanoSearchPaginationTests(unittest.TestCase):
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

        records, total, explicit_empty = parse_search_html(
            html,
            edition="regular",
            captured_at="2026-08-23T05:00:00+00:00",
        )
        self.assertEqual(total, 2)
        self.assertFalse(explicit_empty)
        self.assertEqual(len(records), 2)

        numbered = next(item for item in records if item["id"] == "elperuano:2539375-4")
        self.assertEqual(numbered["document_type"], "RESOLUCIÓN SUPREMA")
        self.assertEqual(numbered["number"], "248-2026-PCM")
        self.assertEqual(numbered["publication_date"], "2026-08-01")
        self.assertEqual(numbered["issuer"], "PRESIDENCIA DEL CONSEJO DE MINISTROS")
        self.assertEqual(numbered["edition"], "regular")
        self.assertTrue(str(numbered["title"]).startswith("Aceptan renuncia"))

        unnumbered = next(item for item in records if item["id"] == "elperuano:2539300-1")
        self.assertEqual(unnumbered["document_type"], "ACUERDO del Pleno")
        self.assertIsNone(unnumbered["number"])
        self.assertEqual(unnumbered["issuer"], "JURADO NACIONAL DE ELECCIONES")

    def test_publication_type_paginates_in_twenty_record_pages(self) -> None:
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
                ("NL", 0): "<div>21 dispositivos encontrados</div>" + first_page_items,
                ("NL", 20): "<div>21 dispositivos encontrados</div>" + second_page_item,
            }
        )

        records = fetch_publication_type(
            session,
            date(2026, 8, 1),
            "NL",
            "regular",
            page_delay_seconds=0,
        )
        self.assertEqual(len(records), 21)
        self.assertEqual(session.requests, [("NL", 0), ("NL", 20)])
        self.assertTrue(all(item["edition"] == "regular" for item in records))

    def test_source_overcount_is_accepted_only_after_explicit_exhaustion(self) -> None:
        first_page = (
            "<div>3 dispositivos encontrados</div>"
            + result_html(
                "2443018-1",
                "RESOLUCIÓN MINISTERIAL N° D000244-2025-MIDIS",
                "Aprueban el Cuadro para Asignación de Personal Provisional",
                issuer="DESARROLLO E INCLUSIÓN SOCIAL",
                publication_type="EX",
            )
            + result_html(
                "2443019-1",
                "RESOLUCIÓN MINISTERIAL N° D000245-2025-MIDIS",
                "Modifican la Sección Segunda del Reglamento de Organización y Funciones",
                issuer="DESARROLLO E INCLUSIÓN SOCIAL",
                publication_type="EX",
            )
        )
        empty_page = (
            "<div>3 dispositivos encontrados</div>"
            "<div>No hay resultados para mostrar.</div>"
        )
        session = _Session({("EX", 0): first_page, ("EX", 20): empty_page})

        with self.assertLogs(level="WARNING") as logs:
            records = fetch_publication_type(
                session,
                date(2025, 9, 27),
                "EX",
                "extraordinary",
                page_delay_seconds=0,
            )

        self.assertEqual(
            [item["id"] for item in records],
            ["elperuano:2443018-1", "elperuano:2443019-1"],
        )
        self.assertEqual(session.requests, [("EX", 0), ("EX", 20)])
        self.assertIn("informó 3 dispositivos EX", "\n".join(logs.output))
        self.assertIn("solo enlazó 2 OP únicos", "\n".join(logs.output))

    def test_visible_device_that_parser_cannot_normalize_fails(self) -> None:
        malformed_visible_device = """
        <div>1 dispositivos encontrados</div>
        <div class="result">
          <a href="/dispositivo/EX/2443999-1">RESOLUCIÓN MINISTERIAL N° 999-2025-TR</a>
          <span>2443999-1</span>
        </div>
        """
        session = _Session({("EX", 0): malformed_visible_device})

        with self.assertRaisesRegex(SearchCollectorError, "no normalizó exactamente"):
            fetch_publication_type(
                session,
                date(2025, 9, 27),
                "EX",
                "extraordinary",
                page_delay_seconds=0,
            )

        self.assertEqual(session.requests, [("EX", 0)])

    def test_ambiguous_blank_page_does_not_excuse_total_mismatch(self) -> None:
        first_page = (
            "<div>3 dispositivos encontrados</div>"
            + result_html(
                "2443018-1",
                "RESOLUCIÓN MINISTERIAL N° D000244-2025-MIDIS",
                "Aprueban CAP Provisional",
                publication_type="EX",
            )
            + result_html(
                "2443019-1",
                "RESOLUCIÓN MINISTERIAL N° D000245-2025-MIDIS",
                "Modifican Reglamento de Organización y Funciones",
                publication_type="EX",
            )
        )
        session = _Session(
            {
                ("EX", 0): first_page,
                ("EX", 20): "<div>3 dispositivos encontrados</div><div>Cargando…</div>",
            }
        )

        with self.assertRaises(SearchCollectorError):
            fetch_publication_type(
                session,
                date(2025, 9, 27),
                "EX",
                "extraordinary",
                page_delay_seconds=0,
            )

    def test_fetch_day_combines_regular_and_extraordinary(self) -> None:
        regular = result_html(
            "2539001-1",
            "LEY N° 40001",
            "Ley que modifica disposiciones sobre teletrabajo",
            issuer="CONGRESO DE LA REPÚBLICA",
            publication_type="NL",
        )
        extraordinary = result_html(
            "2539002-1",
            "DECRETO SUPREMO N° 010-2026-TR",
            "Aprueban medidas extraordinarias sobre relaciones laborales",
            publication_type="EX",
        )
        session = _Session(
            {
                ("NL", 0): "<div>1 dispositivos encontrados</div>" + regular,
                ("EX", 0): "<div>1 dispositivos encontrados</div>" + extraordinary,
            }
        )

        records = fetch_day(session, date(2026, 8, 1), page_delay_seconds=0)
        self.assertEqual(len(records), 2)
        self.assertEqual(session.requests, [("NL", 0), ("EX", 0)])
        editions = {item["id"]: item["edition"] for item in records}
        self.assertEqual(editions["elperuano:2539001-1"], "regular")
        self.assertEqual(editions["elperuano:2539002-1"], "extraordinary")


if __name__ == "__main__":
    unittest.main()
