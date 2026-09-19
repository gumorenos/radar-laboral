from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from radar_laboral.classifier_gold import load_labeled_rows, write_benchmark
from radar_laboral.classifier_sample import (
    build_evidence,
    enrich_rows,
    evidence_from_csv,
    write_label_sheet,
)


class _FakeResponse:
    def __init__(
        self,
        text: str = "",
        *,
        content: bytes | None = None,
        url: str = "",
        content_type: str = "text/html",
    ) -> None:
        self.text = text
        self.content = content if content is not None else text.encode("utf-8")
        self.url = url
        self.headers = {"content-type": content_type}
        self.encoding = "utf-8"

    def raise_for_status(self) -> None:
        return None


class _FakeSession:
    def __init__(self, text: str) -> None:
        self.text = text
        self.requested: list[str] = []

    def get(self, url: str, *, timeout: float, **kwargs):
        self.requested.append(url)
        return _FakeResponse(self.text, url=url)


class ClassifierGoldWorkflowTests(unittest.TestCase):
    def sample_rows(self) -> list[dict[str, object]]:
        return [
            {
                "id": "elperuano:test-1",
                "publication_date": "2026-01-10",
                "source": "elperuano",
                "document_type": "DECRETO SUPREMO",
                "number": "001-2026-TR",
                "title": "Regula una materia laboral",
                "summary": "Resumen",
                "issuer": "Ministerio de Trabajo y Promoción del Empleo",
                "official_url": "https://example.test/1",
                "classification_text_excerpt": "Texto legal relevante",
                "pdf_path": "pdfs/test.pdf",
                "labor_relevance": "relevant",
                "relevance_reason": "materia laboral específica",
                "classification_score": 0.91,
                "rule_score": 0.91,
                "classification_method": "rules_v4",
            }
        ]

    def test_label_sheet_is_blind_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.csv"
            write_label_sheet(path, self.sample_rows())
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertIn("human_label", rows[0])
            self.assertNotIn("current_prediction", rows[0])
            self.assertNotIn("classification_score", rows[0])

    def test_enriched_label_sheet_stays_blind(self) -> None:
        rows = self.sample_rows()
        rows[0].update(
            {
                "evidence_source": "cached_pdf",
                "evidence_chars": 123,
                "evidence_text": "Texto oficial independiente del resultado del modelo",
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels-enriched.csv"
            write_label_sheet(path, rows, enriched=True)
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["evidence_source"], "cached_pdf")
            self.assertEqual(row["evidence_chars"], "123")
            self.assertNotIn("classification_text_excerpt", row)
            self.assertNotIn("current_prediction", row)
            self.assertNotIn("current_reason", row)
            self.assertNotIn("classification_method", row)

    def test_label_sheet_can_include_model_output_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.csv"
            write_label_sheet(path, self.sample_rows(), include_model_output=True)
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["current_prediction"], "relevant")
            self.assertEqual(rows[0]["classification_method"], "rules_v4")

    def test_evidence_prefers_summary(self) -> None:
        row = self.sample_rows()[0]
        source, text = build_evidence(row, session=_FakeSession("<html></html>"))
        self.assertEqual(source, "summary")
        self.assertIn("Resumen", text)

    def test_evidence_uses_cached_pdf_before_network(self) -> None:
        row = self.sample_rows()[0]
        row["summary"] = None
        session = _FakeSession("<main>Página oficial</main>")
        with patch(
            "radar_laboral.classifier_sample.extract_pdf_excerpt",
            return_value="Texto extraído del PDF oficial cacheado",
        ):
            source, text = build_evidence(row, session=session)
        self.assertEqual(source, "cached_pdf")
        self.assertIn("PDF oficial", text)
        self.assertEqual(session.requested, [])

    def test_evidence_prefers_remote_official_pdf_before_page(self) -> None:
        row = self.sample_rows()[0]
        row["summary"] = None
        row["pdf_path"] = None
        row["pdf_url"] = "https://busquedas.elperuano.pe/test.pdf"
        session = _FakeSession("")
        with patch(
            "radar_laboral.classifier_sample._remote_pdf_excerpt",
            return_value="Texto del PDF oficial remoto",
        ):
            source, text = build_evidence(row, session=session)
        self.assertEqual(source, "remote_pdf")
        self.assertIn("PDF oficial remoto", text)

    def test_evidence_uses_official_page_when_local_text_is_missing(self) -> None:
        row = self.sample_rows()[0]
        row["summary"] = None
        row["pdf_path"] = None
        session = _FakeSession(
            "<html><main><h1>Norma</h1><p>Considerando que regula relaciones laborales.</p>"
            "<p>Artículo 1. Establécese una obligación.</p></main></html>"
        )
        source, text = build_evidence(row, session=session)
        self.assertEqual(source, "official_page")
        self.assertIn("relaciones laborales", text)
        self.assertEqual(session.requested, ["https://example.test/1"])

    def test_evidence_falls_back_to_title_only(self) -> None:
        row = self.sample_rows()[0]
        row["summary"] = None
        row["pdf_path"] = None
        source, text = build_evidence(row, session=None, fetch_official=False)
        self.assertEqual(source, "title_only")
        self.assertEqual(text, "Regula una materia laboral")

    def test_unlabeled_rows_fail_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.csv"
            write_label_sheet(path, self.sample_rows())
            with self.assertRaisesRegex(ValueError, "sin human_label"):
                load_labeled_rows(path)
            self.assertEqual(load_labeled_rows(path, allow_incomplete=True), [])

    def test_labeled_csv_converts_to_benchmark_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "labels.csv"
            jsonl_path = Path(tmp) / "gold.jsonl"
            write_label_sheet(csv_path, self.sample_rows())

            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
                fieldnames = list(rows[0].keys())
            rows[0]["human_label"] = "review"
            rows[0]["human_notes"] = "Requiere revisión jurídica"
            with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

            labeled = load_labeled_rows(csv_path)
            write_benchmark(jsonl_path, labeled)
            case = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
            self.assertEqual(case["id"], "elperuano:test-1")
            self.assertEqual(case["expected_relevance"], "review")
            self.assertEqual(case["record"]["title"], "Regula una materia laboral")
            self.assertEqual(case["human_notes"], "Requiere revisión jurídica")

    def test_enriched_csv_maps_evidence_to_benchmark_excerpt(self) -> None:
        rows = self.sample_rows()
        rows[0].update(
            {
                "evidence_source": "official_page",
                "evidence_chars": 37,
                "evidence_text": "Texto oficial usado para la decisión humana",
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "labels-enriched.csv"
            jsonl_path = Path(tmp) / "gold.jsonl"
            write_label_sheet(csv_path, rows, enriched=True)
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                exported = list(csv.DictReader(handle))
                fieldnames = list(exported[0].keys())
            exported[0]["human_label"] = "relevant"
            with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(exported)

            labeled = load_labeled_rows(csv_path)
            write_benchmark(jsonl_path, labeled)
            case = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
            self.assertEqual(
                case["record"]["classification_text_excerpt"],
                "Texto oficial usado para la decisión humana",
            )
            self.assertEqual(case["evidence_source"], "official_page")
            self.assertEqual(case["evidence_chars"], 37)

    def test_evidence_from_csv_reads_prior_enrichment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prior.csv"
            path.write_text(
                "id,evidence_source,evidence_chars,evidence_text\n"
                "a,official_page,12,Texto previo\n",
                encoding="utf-8-sig",
            )
            evidence = evidence_from_csv(path)
        self.assertEqual(evidence["a"]["evidence_source"], "official_page")
        self.assertEqual(evidence["a"]["evidence_chars"], 12)
        self.assertEqual(evidence["a"]["evidence_text"], "Texto previo")

    def test_enrich_rows_can_reuse_non_title_evidence(self) -> None:
        row = self.sample_rows()[0]
        row.update(
            {
                "evidence_source": "official_page",
                "evidence_chars": 15,
                "evidence_text": "Evidencia previa",
            }
        )
        with patch("radar_laboral.classifier_sample.build_evidence") as build:
            enriched = enrich_rows(
                [row],
                fetch_official=False,
                reuse_existing=True,
            )
        build.assert_not_called()
        self.assertEqual(enriched[0]["evidence_source"], "official_page")
        self.assertEqual(enriched[0]["evidence_text"], "Evidencia previa")

    def test_invalid_human_label_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.csv"
            path.write_text(
                "id,title,human_label\n1,Norma,maybe\n",
                encoding="utf-8-sig",
            )
            with self.assertRaisesRegex(ValueError, "human_label inválido"):
                load_labeled_rows(path)


if __name__ == "__main__":
    unittest.main()
