from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from radar_laboral.legal_text import extract_pdf_excerpt, normalize_pdf_text, select_legal_excerpt


class FakePage:
    def __init__(self, text: str, *, broken: bool = False) -> None:
        self.text = text
        self.broken = broken

    def extract_text(self) -> str:
        if self.broken:
            raise RuntimeError("bad page")
        return self.text


class FakeReader:
    def __init__(self, path: str) -> None:
        self.pages = [
            FakePage("Cabecera de la norma"),
            FakePage("CONSIDERANDO que corresponde regular el teletrabajo"),
            FakePage("Artículo 1.- Modifíquese el reglamento aplicable"),
        ]


class LegalTextTests(unittest.TestCase):
    def test_normalizes_pdf_whitespace_without_destroying_sections(self) -> None:
        result = normalize_pdf_text("TÍTULO\x00   UNO\n\n\nCONSIDERANDO\tque corresponde")
        self.assertEqual(result, "TÍTULO UNO\nCONSIDERANDO que corresponde")

    def test_excerpt_keeps_later_legal_sections_not_only_prefix(self) -> None:
        text = (
            "CABECERA " + ("x" * 3500) + " CONSIDERANDO se regula el teletrabajo "
            + ("y" * 2200)
            + " Artículo 1.- Se modifica la jornada de trabajo y el sobretiempo."
        )
        excerpt = select_legal_excerpt(text, max_chars=5000)
        self.assertIsNotNone(excerpt)
        self.assertIn("CABECERA", excerpt)
        self.assertIn("CONSIDERANDO", excerpt)
        self.assertIn("teletrabajo", excerpt)
        self.assertLessEqual(len(excerpt), 5004)  # separators may add a few chars

    def test_empty_text_returns_none(self) -> None:
        self.assertIsNone(select_legal_excerpt("   \n\t  "))

    def test_missing_pdf_returns_none(self) -> None:
        self.assertIsNone(extract_pdf_excerpt("/does/not/exist.pdf"))

    def test_extract_reads_bounded_pages_and_selects_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.pdf"
            path.write_bytes(b"%PDF-fake")
            with patch("radar_laboral.legal_text.PdfReader", FakeReader):
                excerpt = extract_pdf_excerpt(path, max_pages=3, max_chars=3000)

        self.assertIsNotNone(excerpt)
        self.assertIn("Cabecera de la norma", excerpt)
        self.assertIn("teletrabajo", excerpt)
        self.assertIn("Artículo 1", excerpt)


if __name__ == "__main__":
    unittest.main()
