from __future__ import annotations

import unittest

from radar_laboral.collectors.sunafil_tfl import parse_listing_html


class SunafilTflPaginationTests(unittest.TestCase):
    def test_previous_page_link_is_not_mistaken_for_next_page(self) -> None:
        html = """
        <html><body>
          <article>
            <h3><a href="/institucion/sunafil/normas-legales/1234567-001-2021-sunafil-tfl">Resolución de Sala Plena N.° 001-2021-SUNAFIL-TFL</a></h3>
            <p>Resolución histórica de prueba para validar la última página.</p>
            <time>8 de agosto de 2021</time>
            <a href="https://cdn.www.gob.pe/test.pdf">Descargar</a>
            <a href="/institucion/sunafil/normas-legales/1234567-001-2021-sunafil-tfl">Leer más</a>
          </article>
          <nav><a href="?sheet=1">1</a><a href="?sheet=2">2</a></nav>
        </body></html>
        """
        records, has_next = parse_listing_html(html, current_sheet=3)
        self.assertEqual(len(records), 1)
        self.assertFalse(has_next)

    def test_larger_sheet_link_is_a_next_page(self) -> None:
        html = """
        <html><body>
          <article>
            <h3><a href="/institucion/sunafil/normas-legales/1234567-001-2024-sunafil-tfl">Resolución de Sala Plena N.° 001-2024-SUNAFIL-TFL</a></h3>
            <p>Resolución de prueba para validar que existe otra página.</p>
            <time>15 de febrero de 2024</time>
            <a href="https://cdn.www.gob.pe/test.pdf">Descargar</a>
            <a href="/institucion/sunafil/normas-legales/1234567-001-2024-sunafil-tfl">Leer más</a>
          </article>
          <nav><a href="?sheet=1">1</a><a href="?sheet=3">3</a></nav>
        </body></html>
        """
        _, has_next = parse_listing_html(html, current_sheet=2)
        self.assertTrue(has_next)


if __name__ == "__main__":
    unittest.main()
