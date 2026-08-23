from __future__ import annotations

import unittest

from radar_laboral.collectors.el_peruano import _storage_key, parse_daily_html


DIRECT_PDF_HTML = """
<div class="norma">
  <h4>BANCO CENTRAL DE RESERVA</h4>
  <h5>
    <a href="https://epdoc2.elperuano.pe/EpPo/Descarga.asp?Referencias=ABC123">
      CIRCULAR N° 0020-2026-BCRP
    </a>
  </h5>
  <div>Fecha: 22/08/2026</div>
  <p>Disposiciones de encaje en moneda extranjera</p>
  <a href="https://epdoc2.elperuano.pe/EpPo/Descarga.asp?Referencias=ABC123">Descarga individual</a>
  <a href="https://busquedas.elperuano.pe/cuadernillo/NL/20260822">Todo el cuadernillo</a>
</div>
"""


class ElPeruanoDirectPdfTests(unittest.TestCase):
    def test_parses_direct_epdoc_document(self) -> None:
        records = parse_daily_html(
            DIRECT_PDF_HTML,
            captured_at="2026-08-23T00:00:00+00:00",
        )

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertTrue(str(record["id"]).startswith("elperuano:direct:"))
        self.assertEqual(record["issuer"], "BANCO CENTRAL DE RESERVA")
        self.assertEqual(record["document_type"], "CIRCULAR")
        self.assertEqual(record["number"], "0020-2026-BCRP")
        self.assertEqual(record["publication_date"], "2026-08-22")
        self.assertEqual(
            record["pdf_url"],
            "https://epdoc2.elperuano.pe/EpPo/Descarga.asp?Referencias=ABC123",
        )

    def test_storage_key_is_windows_safe(self) -> None:
        key = _storage_key("elperuano:direct:abc123")
        self.assertEqual(key, "direct-abc123")
        self.assertNotIn(":", key)


if __name__ == "__main__":
    unittest.main()
