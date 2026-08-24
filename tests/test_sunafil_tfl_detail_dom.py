from __future__ import annotations

import unittest

from radar_laboral.collectors.sunafil_tfl import parse_detail_html


class SunafilTflDetailDomTests(unittest.TestCase):
    def test_complete_rule_content_beats_truncated_paragraph_and_metadata(self) -> None:
        html = """
        <html><head>
          <meta name="description" content="ESTABLECER como precedentes administrativos de observancia...">
        </head><body>
          <main>
            <h2>Resolución de Sala Plena N.° 001-2025-SUNAFIL-TFL</h2>
            <p>10 de marzo de 2025</p>
            <div class="description rule-content">
              <p>ESTABLECER como precedentes administrativos de observancia...</p>
              <div>
                Declarar FUNDADO EN PARTE el recurso de revisión. ESTABLECER como
                precedentes administrativos de observancia obligatoria los criterios
                establecidos en los fundamentos 6.15, 6.16 y 6.17 de la presente resolución.
              </div>
              <div><span>JU20250309</span><span>PDF</span><span>957.1 KB</span><a href="https://cdn.www.gob.pe/uploads/document/file/7758954/control.pdf">Descargar</a></div>
            </div>
            <button class="js-share" data-contents="Fallback completo que no debe ganar si existe rule-content">Compartir</button>
          </main>
        </body></html>
        """
        record = parse_detail_html(
            html,
            "https://www.gob.pe/institucion/sunafil/normas-legales/6556395-001-2025-sunafil-tfl",
            captured_at="2026-08-24T05:00:00+00:00",
        )

        self.assertIn("observancia obligatoria", record["summary"])
        self.assertNotIn("JU20250309", record["summary"])
        self.assertEqual(
            record["binding_level"],
            "precedente administrativo de observancia obligatoria",
        )

    def test_share_data_contents_is_safe_fallback_when_rule_content_is_missing(self) -> None:
        html = """
        <html><body><main>
          <h2>Resolución de Sala Plena N.° 008-2023-SUNAFIL-TFL</h2>
          <p>9 de mayo de 2023</p>
          <p>Establecer criterios administrativos de observancia...</p>
          <button class="js-share"
            data-contents="Establecer criterios administrativos interpretativos e integradores de observancia obligatoria para todos los órganos resolutivos.">Compartir</button>
          <a href="https://cdn.www.gob.pe/control.pdf">Descargar</a>
        </main></body></html>
        """
        record = parse_detail_html(
            html,
            "https://www.gob.pe/institucion/sunafil/normas-legales/7000000-008-2023-sunafil-tfl",
        )
        self.assertIn("observancia obligatoria", record["summary"])
        self.assertEqual(record["binding_level"], "criterio de observancia obligatoria")


if __name__ == "__main__":
    unittest.main()
