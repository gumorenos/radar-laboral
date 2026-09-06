from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import requests

VALID_RELEVANCE = {"relevant", "review", "not_labor"}

SYSTEM_PROMPT = """Eres un clasificador conservador de normativa laboral peruana.
Clasifica el texto únicamente para decidir si debe rastrearse en un radar de normativa laboral para RR.HH.
No determines vigencia ni brindes asesoría legal.
Usa relevant cuando hay materia laboral sustantiva clara; review cuando puede ser laboral pero falta evidencia suficiente; not_labor cuando no regula materia laboral.
Los actos internos de designación, viajes, encargaturas o delegación de facultades sin efecto normativo laboral deben ser not_labor.
Devuelve exclusivamente JSON según el esquema solicitado."""

SCHEMA = {
    "name": "labor_relevance",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "labor_relevance": {"type": "string", "enum": ["relevant", "review", "not_labor"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "reason": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        },
        "required": ["labor_relevance", "confidence", "reason", "evidence"],
        "additionalProperties": False,
    },
}


@dataclass(frozen=True)
class LLMDecision:
    relevance: str
    confidence: float
    reason: str
    evidence: tuple[str, ...]


class OpenAICompatibleSemanticScorer:
    """Optional API scorer for uncertain cases using an OpenAI-compatible endpoint.

    No API is contacted unless ``score`` is called. Credentials are read from
    environment variables and are never persisted by Radar Laboral.
    """

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 30.0,
        session: requests.Session | None = None,
    ) -> None:
        self.model = model
        self.name = f"llm:{model}"
        self.api_key = (api_key or os.getenv("RADAR_LLM_API_KEY", "")).strip()
        if not self.api_key:
            raise RuntimeError("Falta RADAR_LLM_API_KEY para usar clasificación LLM")
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self.session = session or requests.Session()
        self.last_decision: LLMDecision | None = None

    @classmethod
    def from_env(cls) -> "OpenAICompatibleSemanticScorer":
        model = os.getenv("RADAR_LLM_MODEL", "").strip()
        if not model:
            raise RuntimeError("Falta RADAR_LLM_MODEL para usar clasificación LLM")
        return cls(
            model=model,
            base_url=os.getenv("RADAR_LLM_BASE_URL", "https://api.openai.com/v1"),
        )

    def _request(self, text: str) -> dict[str, Any]:
        response = self.session.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text[:12000]},
                ],
                "response_format": {"type": "json_schema", "json_schema": SCHEMA},
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Respuesta LLM sin choices[0].message.content") from exc
        if isinstance(content, dict):
            return content
        try:
            return json.loads(content)
        except (TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Respuesta LLM no es JSON válido") from exc

    @staticmethod
    def _decision(payload: dict[str, Any]) -> LLMDecision:
        relevance = str(payload.get("labor_relevance", ""))
        if relevance not in VALID_RELEVANCE:
            raise RuntimeError(f"labor_relevance inválido del LLM: {relevance}")
        confidence = max(0.0, min(1.0, float(payload.get("confidence", 0.0))))
        reason = str(payload.get("reason", "")).strip()
        evidence_raw = payload.get("evidence") or []
        evidence = tuple(str(item).strip() for item in evidence_raw if str(item).strip())[:5]
        return LLMDecision(relevance, confidence, reason, evidence)

    def score(self, text: str) -> float:
        if not text.strip():
            return 0.5
        decision = self._decision(self._request(text))
        self.last_decision = decision
        if decision.relevance == "review":
            return 0.5
        direction = 1.0 if decision.relevance == "relevant" else -1.0
        return 0.5 + direction * (0.5 * decision.confidence)
