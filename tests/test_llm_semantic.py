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
