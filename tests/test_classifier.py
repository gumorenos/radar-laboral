from __future__ import annotations

import unittest

from radar_laboral.classifier import CLASSIFIER_VERSION, classify_labor


class LaborClassifierTests(unittest.TestCase):
    def test_substantive_labor_rule_is_relevant_even_outside_mtpe(self) -> None:
        result = classify_labor({
            "issuer": "PODER EJECUTIVO",
            "document_type": "DECRETO SUPREMO",
            "title": "Modifican disposiciones sobre teletrabajo y jornada laboral de los trabajadores",
        })

        self.assertEqual(result["labor_relevance"], "relevant")
        self.assertIn("Teletrabajo", result["topic"] or "")
        self.assertIn("Jornada y descansos", result["topic"] or "")
        self.assertEqual(result["classification_version"], CLASSIFIER_VERSION)

    def test_mtpe_personnel_appointment_is_not_labor_rule(self) -> None:
        result = classify_labor({
            "issuer": "TRABAJO Y PROMOCIÓN DEL EMPLEO",
            "document_type": "RESOLUCIÓN MINISTERIAL",
            "title": "Designan Asesor del Despacho Viceministerial de Promoción del Empleo y Capacitación Laboral I",
        })

        self.assertEqual(result["labor_relevance"], "not_labor")
        self.assertIn("acto administrativo", result["relevance_reason"] or "")

    def test_generic_labor_word_outside_labor_authority_is_not_enough(self) -> None:
        result = classify_labor({
            "issuer": "OTRA ENTIDAD",
            "document_type": "RESOLUCIÓN",
            "title": "Aprueban medidas relacionadas con trabajadores de la entidad",
        })

        self.assertEqual(result["labor_relevance"], "not_labor")
        self.assertIn("señal laboral genérica insuficiente", result["relevance_reason"] or "")

    def test_general_scope_rule_with_generic_labor_signal_goes_to_review(self) -> None:
        result = classify_labor({
            "issuer": "PODER EJECUTIVO",
            "document_type": "DECRETO SUPREMO",
            "title": "Aprueban medidas aplicables a trabajadores del sector privado",
        })

        self.assertEqual(result["labor_relevance"], "review")

    def test_labor_authority_document_without_specific_topic_goes_to_review(self) -> None:
        result = classify_labor({
            "issuer": "TRABAJO Y PROMOCIÓN DEL EMPLEO",
            "document_type": "RESOLUCIÓN MINISTERIAL",
            "title": "Aprueban lineamientos institucionales para el año 2026",
        })

        self.assertEqual(result["labor_relevance"], "review")

    def test_specific_payroll_rule_is_relevant(self) -> None:
        result = classify_labor({
            "issuer": "ECONOMÍA Y FINANZAS",
            "document_type": "RESOLUCIÓN",
            "title": "Modifican disposiciones aplicables a la Planilla Electrónica y T-Registro",
        })

        self.assertEqual(result["labor_relevance"], "relevant")
        self.assertIn("Planilla y registros", result["topic"] or "")


if __name__ == "__main__":
    unittest.main()
