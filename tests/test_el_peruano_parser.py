from __future__ import annotations

import unittest

from radar_laboral.collectors.el_peruano import parse_daily_html


SAMPLE_HTML = """
<div class="norma">
  <h4>TRABAJO Y PROMOCIÓN DEL EMPLEO</h4>
  <h5>
    <a href="https://busquedas.elperuano.pe/dispositivo/NL/2546299-1">
      RESOLUCIÓN MINISTERIAL N° 251-2026-TR
    </a>
  </h5>
  <div>Fecha: 22/08/2026</div>
  <p>Designan Asesor del Despacho Viceministerial de Promoción del Empleo y Capacitación Laboral I</p>
  <a href="/dispositivo/NL/2546299-1/pdf">Descarga individual</a>
  <a href="/cuadernillo/NL/20260822">Todo el cuadernillo</a>
</div>
"""

UNNUMBERED_HTML = """
<div class="norma">
  <h4>JURADO NACIONAL DE ELECCIONES</h4>
  <h5>
    <a href="https://busquedas.elperuano.pe/dispositivo/NL/2539300-1">
      ACUERDO del Pleno
    </a>
  </h5>
  <div>Fecha: 01/08/2026</div>
  <p>Modifican el cronograma electoral aprobado mediante Acuerdo</p>
  <a href="/dispositivo/NL/2539300-1/pdf">Descarga individual</a>
  <a href="/cuadernillo/NL/20260801">Todo el cuadernillo</a>
</div>
"""


class ElPeruanoParserTests(unittest.TestCase):
    def test_parses_daily_device(self) -> None:
        records = parse_daily_html(
            SAMPLE_HTML,
            captured_at="2026-08-23T00:00:00+00:00",
        )

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["id"], "elperuano:2546299-1")
        self.assertEqual(record["source"], "El Peruano")
        self.assertEqual(record["issuer"], "TRABAJO Y PROMOCIÓN DEL EMPLEO")
        self.assertEqual(record["document_type"], "RESOLUCIÓN MINISTERIAL")
        self.assertEqual(record["number"], "251-2026-TR")
        self.assertEqual(record["publication_date"], "2026-08-22")
        self.assertTrue(str(record["title"]).startswith("Designan Asesor"))
        self.assertEqual(
            record["official_url"],
            "https://busquedas.elperuano.pe/dispositivo/NL/2546299-1",
        )
        self.assertEqual(
            record["pdf_url"],
            "https://busquedas.elperuano.pe/dispositivo/NL/2546299-1/pdf",
        )

    def test_preserves_unnumbered_device(self) -> None:
        records = parse_daily_html(
            UNNUMBERED_HTML,
            captured_at="2026-08-23T00:00:00+00:00",
        )
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["id"], "elperuano:2539300-1")
        self.assertEqual(record["document_type"], "ACUERDO del Pleno")
        self.assertIsNone(record["number"])
        self.assertEqual(record["issuer"], "JURADO NACIONAL DE ELECCIONES")
        self.assertTrue(str(record["title"]).startswith("Modifican el cronograma"))


if __name__ == "__main__":
    unittest.main()
