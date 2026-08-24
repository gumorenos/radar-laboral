from __future__ import annotations

import unittest

from radar_laboral.classifier import CLASSIFIER_VERSION, classify_labor


class FakeSemanticScorer:
    def __init__(self, value: float, *, name: str = "fake-semantic") -> None:
        self.value = value
        self.name = name
        self.calls: list[str] = []

    def score(self, text: str) -> float:
        self.calls.append(text)
        return self.value


class BrokenSemanticScorer:
    name = "broken-semantic"

    def score(self, text: str) -> float:
        raise RuntimeError("model unavailable")


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
        self.assertEqual(result["classification_version"], 4)
        self.assertGreaterEqual(result["classification_score"], 0.68)
        self.assertEqual(result["classification_method"], "rules_v4")

    def test_mtpe_personnel_appointment_is_not_labor_rule(self) -> None:
        result = classify_labor({
            "issuer": "TRABAJO Y PROMOCIÓN DEL EMPLEO",
            "document_type": "RESOLUCIÓN MINISTERIAL",
            "title": "Designan Asesor del Despacho Viceministerial de Promoción del Empleo y Capacitación Laboral I",
        })

        self.assertEqual(result["labor_relevance"], "not_labor")
        self.assertIn("acto administrativo", result["relevance_reason"] or "")
        negative = result["classification_evidence"]["negative"]
        self.assertTrue(any(item["code"] == "administrative_personnel_act" for item in negative))

    def test_administrative_exclusion_cannot_be_overridden_by_semantics(self) -> None:
        scorer = FakeSemanticScorer(0.99)
        result = classify_labor(
            {
                "issuer": "TRABAJO Y PROMOCIÓN DEL EMPLEO",
                "document_type": "RESOLUCIÓN MINISTERIAL",
                "title": "Designan Directora de Seguridad y Salud en el Trabajo",
            },
            semantic_scorer=scorer,
        )

        self.assertEqual(result["labor_relevance"], "not_labor")
        self.assertEqual(scorer.calls, [])
        self.assertIsNone(result["semantic_score"])

    def test_conclusion_of_temporary_designation_stays_non_labor_despite_sst_words(self) -> None:
        result = classify_labor({
            "issuer": "TRABAJO Y PROMOCIÓN DEL EMPLEO",
            "document_type": "RESOLUCIÓN MINISTERIAL",
            "title": (
                "Disponen la conclusión de la designación temporal de Directora de la Dirección "
                "de Seguridad y Salud en el Trabajo"
            ),
        })

        self.assertEqual(result["labor_relevance"], "not_labor")
        self.assertIn("Seguridad y salud en el trabajo", result["topic"] or "")
        self.assertIn("acto administrativo", result["relevance_reason"] or "")

    def test_acceptance_of_resignation_with_article_is_non_labor(self) -> None:
        result = classify_labor({
            "issuer": "TRABAJO Y PROMOCIÓN DEL EMPLEO",
            "document_type": "RESOLUCIÓN MINISTERIAL",
            "title": "Aceptan la renuncia de Director General de Trabajo",
        })
        self.assertEqual(result["labor_relevance"], "not_labor")

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
        self.assertTrue(result["requires_review"])
        self.assertIn("evidencia insuficiente", result["relevance_reason"] or "")

    def test_labor_authority_document_without_specific_topic_goes_to_review(self) -> None:
        result = classify_labor({
            "issuer": "TRABAJO Y PROMOCIÓN DEL EMPLEO",
            "document_type": "RESOLUCIÓN MINISTERIAL",
            "title": "Aprueban lineamientos institucionales para el año 2026",
        })

        self.assertEqual(result["labor_relevance"], "review")

    def test_semantic_signal_can_promote_uncertain_case_but_is_auditable(self) -> None:
        scorer = FakeSemanticScorer(0.91)
        result = classify_labor(
            {
                "issuer": "TRABAJO Y PROMOCIÓN DEL EMPLEO",
                "document_type": "RESOLUCIÓN MINISTERIAL",
                "title": "Aprueban criterios técnicos sobre derechos de las personas que prestan servicios",
            },
            semantic_scorer=scorer,
        )

        self.assertEqual(result["labor_relevance"], "relevant")
        self.assertEqual(result["classification_method"], "hybrid_v4")
        self.assertEqual(result["semantic_score"], 0.91)
        self.assertEqual(result["semantic_model"], "fake-semantic")
        self.assertEqual(len(scorer.calls), 1)
        self.assertIn("señal semántica", result["relevance_reason"] or "")

    def test_low_semantic_signal_can_exclude_only_weak_rule_case(self) -> None:
        scorer = FakeSemanticScorer(0.05)
        result = classify_labor(
            {
                "issuer": "OTRA ENTIDAD",
                "document_type": "RESOLUCIÓN",
                "title": "Aprueban disposiciones generales para la entidad",
            },
            semantic_scorer=scorer,
        )
        self.assertEqual(result["labor_relevance"], "not_labor")
        self.assertEqual(result["classification_method"], "hybrid_v4")

    def test_semantic_backend_failure_falls_back_to_conservative_rules(self) -> None:
        result = classify_labor(
            {
                "issuer": "TRABAJO Y PROMOCIÓN DEL EMPLEO",
                "document_type": "RESOLUCIÓN MINISTERIAL",
                "title": "Aprueban lineamientos institucionales para el año 2026",
            },
            semantic_scorer=BrokenSemanticScorer(),
        )
        self.assertEqual(result["labor_relevance"], "review")
        self.assertEqual(result["classification_method"], "rules_v4_semantic_unavailable")
        self.assertIsNone(result["semantic_score"])

    def test_function_inspectiva_is_specific_labor_inspection_topic(self) -> None:
        result = classify_labor({
            "issuer": "TRABAJO Y PROMOCIÓN DEL EMPLEO",
            "document_type": "RESOLUCIÓN MINISTERIAL",
            "title": (
                "Establecen medidas para garantizar el adecuado ejercicio de la función inspectiva "
                "en el Sistema de Inspección del Trabajo"
            ),
        })

        self.assertEqual(result["labor_relevance"], "relevant")
        self.assertIn("Inspección laboral", result["topic"] or "")
        self.assertEqual(result["classification_version"], 4)

    def test_specific_payroll_rule_is_relevant(self) -> None:
        result = classify_labor({
            "issuer": "ECONOMÍA Y FINANZAS",
            "document_type": "RESOLUCIÓN",
            "title": "Modifican disposiciones aplicables a la Planilla Electrónica y T-Registro",
        })

        self.assertEqual(result["labor_relevance"], "relevant")
        self.assertIn("Planilla y registros", result["topic"] or "")

    def test_strong_legal_reference_can_identify_labor_without_keyword_topic(self) -> None:
        result = classify_labor({
            "issuer": "PODER EJECUTIVO",
            "document_type": "DECRETO SUPREMO",
            "title": "Modifican disposiciones del Decreto Legislativo 728",
        })
        self.assertEqual(result["labor_relevance"], "relevant")
        evidence = result["classification_evidence"]
        self.assertIn("régimen laboral privado", evidence["reference_hits"])

    def test_pdf_excerpt_is_part_of_classification_haystack(self) -> None:
        result = classify_labor({
            "issuer": "OTRA ENTIDAD",
            "document_type": "RESOLUCIÓN",
            "title": "Aprueban disposiciones complementarias",
            "classification_text_excerpt": "Las disposiciones regulan el teletrabajo y las horas extras.",
        })
        self.assertEqual(result["labor_relevance"], "relevant")
        self.assertIn("Teletrabajo", result["topic"] or "")


if __name__ == "__main__":
    unittest.main()
