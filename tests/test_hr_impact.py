from __future__ import annotations

import json
import unittest
from pathlib import Path

from radar_laboral.hr_impact import HR_IMPACT_VERSION, assess_hr_impact


IMPACT_BENCHMARK = (
    Path(__file__).resolve().parents[1] / "benchmarks" / "hr_impact_official_v1.jsonl"
)


class HrImpactTests(unittest.TestCase):
    def test_non_labor_document_has_no_hr_impact(self) -> None:
        result = assess_hr_impact(
            {
                "labor_relevance": "not_labor",
                "title": "Designan Asesor del Despacho Ministerial",
                "topic": None,
            }
        )
        self.assertEqual(result["hr_impact_scope"], "none")
        self.assertEqual(result["hr_impact_level"], "none")
        self.assertFalse(result["hr_impact_requires_review"])

    def test_labor_review_stays_low_and_unclear(self) -> None:
        result = assess_hr_impact(
            {
                "labor_relevance": "review",
                "title": "Aprueban lineamientos institucionales para el sector trabajo",
                "topic": None,
            }
        )
        self.assertEqual(result["hr_impact_scope"], "unclear")
        self.assertEqual(result["hr_impact_level"], "low")
        self.assertTrue(result["hr_impact_requires_review"])

    def test_telework_regulation_is_direct_high_impact(self) -> None:
        result = assess_hr_impact(
            {
                "labor_relevance": "relevant",
                "title": "Decreto Supremo que modifica el Reglamento de la Ley del Teletrabajo",
                "topic": "Teletrabajo",
            }
        )
        self.assertEqual(result["hr_impact_scope"], "direct")
        self.assertEqual(result["hr_impact_level"], "high")
        self.assertIn("política", result["hr_action_recommended"].lower())
        self.assertEqual(result["hr_impact_version"], HR_IMPACT_VERSION)

    def test_equal_pay_rule_is_direct_high_impact(self) -> None:
        result = assess_hr_impact(
            {
                "labor_relevance": "relevant",
                "title": "Aprueban Reglamento de la Ley que prohíbe la discriminación remunerativa",
                "topic": "Igualdad y no discriminación, Remuneraciones y beneficios",
                "classification_text_excerpt": (
                    "Todo empleador debe establecer cuadros de categorías y funciones bajo el principio "
                    "de igual remuneración por trabajo de igual valor."
                ),
            }
        )
        self.assertEqual(result["hr_impact_scope"], "direct")
        self.assertEqual(result["hr_impact_level"], "high")
        self.assertIn("categorías", result["hr_action_recommended"].lower())

    def test_plame_change_is_direct_high_impact(self) -> None:
        result = assess_hr_impact(
            {
                "labor_relevance": "relevant",
                "title": "Aprueban Formulario Virtual N° 0601 - PLAME Web",
                "topic": "Planilla y registros",
                "classification_text_excerpt": (
                    "La información del T-REGISTRO se utiliza obligatoriamente para la elaboración de la PLAME."
                ),
            }
        )
        self.assertEqual(result["hr_impact_scope"], "direct")
        self.assertEqual(result["hr_impact_level"], "high")
        self.assertIn("t-registro", result["hr_action_recommended"].lower())

    def test_simel_is_labor_relevant_but_indirect_low_impact(self) -> None:
        result = assess_hr_impact(
            {
                "labor_relevance": "relevant",
                "title": (
                    "Decreto Supremo que modifica el Sistema de Información del Mercado Laboral "
                    "y el Laboratorio de Innovación Laboral"
                ),
                "topic": "Planilla y registros, Protección de datos laborales",
                "classification_text_excerpt": (
                    "La Planilla Electrónica es fuente de información del SIMEL y se observa la normativa "
                    "sobre protección de datos personales."
                ),
            }
        )
        self.assertEqual(result["hr_impact_scope"], "indirect")
        self.assertEqual(result["hr_impact_level"], "low")
        self.assertFalse(result["hr_impact_requires_review"])

    def test_inspection_continuity_measures_are_not_mistaken_for_direct_employer_change(self) -> None:
        result = assess_hr_impact(
            {
                "labor_relevance": "relevant",
                "title": (
                    "Establecen medidas para garantizar el adecuado ejercicio de la función inspectiva "
                    "en el Sistema de Inspección del Trabajo"
                ),
                "topic": "Inspección laboral",
            }
        )
        self.assertEqual(result["hr_impact_scope"], "indirect")
        self.assertEqual(result["hr_impact_level"], "medium")

    def test_inspection_regulation_change_can_be_direct_high_impact(self) -> None:
        result = assess_hr_impact(
            {
                "labor_relevance": "relevant",
                "title": "Decreto Supremo que modifica el Reglamento de la Ley General de Inspección del Trabajo",
                "topic": "Inspección laboral",
                "classification_text_excerpt": "Se modifican infracciones y obligaciones exigibles a los empleadores.",
            }
        )
        self.assertEqual(result["hr_impact_scope"], "direct")
        self.assertEqual(result["hr_impact_level"], "high")
        self.assertIn("fiscalización", result["hr_action_recommended"].lower())

    def test_published_telework_project_is_potential_not_current_obligation(self) -> None:
        result = assess_hr_impact(
            {
                "labor_relevance": "relevant",
                "title": "Disponen la publicación del proyecto de Decreto Supremo que modifica el Reglamento de la Ley del Teletrabajo",
                "topic": "Teletrabajo",
            }
        )
        self.assertEqual(result["hr_impact_scope"], "potential")
        self.assertEqual(result["hr_impact_level"], "medium")
        self.assertTrue(result["hr_impact_requires_review"])
        self.assertIn("no cambiar procesos", result["hr_action_recommended"].lower())

    def test_official_impact_benchmark_matches_scope_and_level(self) -> None:
        cases = [
            json.loads(line)
            for line in IMPACT_BENCHMARK.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertGreaterEqual(len(cases), 9)
        mismatches: list[str] = []
        for case in cases:
            result = assess_hr_impact(case["record"])
            if (
                result["hr_impact_scope"] != case["expected_scope"]
                or result["hr_impact_level"] != case["expected_level"]
            ):
                mismatches.append(
                    f"{case['id']}: expected={case['expected_scope']}/{case['expected_level']} "
                    f"actual={result['hr_impact_scope']}/{result['hr_impact_level']}"
                )
        self.assertEqual(mismatches, [])


if __name__ == "__main__":
    unittest.main()
