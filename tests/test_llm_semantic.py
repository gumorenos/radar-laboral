from __future__ import annotations

import unittest

from radar_laboral.llm_semantic import OpenAICompatibleSemanticScorer


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _Session:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response(self.payload)


class LLMSemanticScorerTests(unittest.TestCase):
    def test_relevant_decision_maps_to_high_semantic_score(self) -> None:
        session = _Session(
            {
                "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
                "choices": [
                    {
                        "message": {
                            "content": '{"labor_relevance":"relevant","confidence":0.8,"reason":"laboral","evidence":["CTS"]}'
                        }
                    }
                ]
            }
        )
        scorer = OpenAICompatibleSemanticScorer(
            model="test-model", api_key="secret", session=session
        )
        self.assertAlmostEqual(scorer.score("Norma sobre CTS"), 0.9)
        self.assertEqual(scorer.last_decision.relevance, "relevant")
        self.assertNotIn("secret", str(session.calls[0][1]["json"]))
        self.assertEqual(session.calls[0][1]["json"]["temperature"], 0)
        telemetry = scorer.telemetry()
        self.assertEqual(telemetry["calls"], 1)
        self.assertEqual(telemetry["prompt_tokens"], 120)
        self.assertEqual(telemetry["completion_tokens"], 30)
        self.assertEqual(telemetry["total_tokens"], 150)
        self.assertGreaterEqual(telemetry["elapsed_ms"], 0)

    def test_not_labor_maps_to_low_score(self) -> None:
        session = _Session(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"labor_relevance":"not_labor","confidence":1,"reason":"viaje","evidence":[]}'
                        }
                    }
                ]
            }
        )
        scorer = OpenAICompatibleSemanticScorer(
            model="test-model", api_key="secret", session=session
        )
        self.assertEqual(scorer.score("Autorizan viaje"), 0.0)

    def test_review_maps_to_neutral_score(self) -> None:
        session = _Session(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"labor_relevance":"review","confidence":0.7,"reason":"ambiguo","evidence":[]}'
                        }
                    }
                ]
            }
        )
        scorer = OpenAICompatibleSemanticScorer(
            model="test-model", api_key="secret", session=session
        )
        self.assertEqual(scorer.score("Texto ambiguo"), 0.5)

    def test_telemetry_estimates_cost_when_prices_are_configured(self) -> None:
        session = _Session(
            {
                "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 500_000},
                "choices": [
                    {
                        "message": {
                            "content": '{"labor_relevance":"review","confidence":0.5,"reason":"x","evidence":[]}'
                        }
                    }
                ],
            }
        )
        scorer = OpenAICompatibleSemanticScorer(
            model="test-model", api_key="secret", session=session
        )
        from unittest.mock import patch
        with patch.dict(
            "os.environ",
            {
                "RADAR_LLM_INPUT_USD_PER_MILLION": "1.0",
                "RADAR_LLM_OUTPUT_USD_PER_MILLION": "2.0",
            },
        ):
            scorer.score("x")
            self.assertAlmostEqual(
                scorer.telemetry()["estimated_cost_usd"],
                2.0,
            )

    def test_invalid_label_is_rejected(self) -> None:
        session = _Session(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"labor_relevance":"maybe","confidence":0.5,"reason":"x","evidence":[]}'
                        }
                    }
                ]
            }
        )
        scorer = OpenAICompatibleSemanticScorer(
            model="test-model", api_key="secret", session=session
        )
        with self.assertRaises(RuntimeError):
            scorer.score("x")


if __name__ == "__main__":
    unittest.main()
