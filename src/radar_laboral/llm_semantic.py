from __future__ import annotations

import json
import os
import time
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


@dataclass(frozen=True)
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    elapsed_ms: float = 0.0


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
        self.last_usage: LLMUsage | None = None
        self.call_count = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.elapsed_ms = 0.0

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
        started = time.perf_counter()
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
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        payload = response.json()

        usage = payload.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion_tokens = int(
            usage.get("completion_tokens") or usage.get("output_tokens") or 0
        )
        total_tokens = int(
            usage.get("total_tokens") or (prompt_tokens + completion_tokens)
        )
        self.last_usage = LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            elapsed_ms=elapsed_ms,
        )
        self.call_count += 1
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_tokens += total_tokens
        self.elapsed_ms += elapsed_ms

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

    @staticmethod
    def _env_price(name: str) -> float | None:
        raw = os.getenv(name, "").strip()
        if not raw:
            return None
        try:
            value = float(raw)
        except ValueError as exc:
            raise RuntimeError(f"{name} debe ser numérico") from exc
        if value < 0:
            raise RuntimeError(f"{name} no puede ser negativo")
        return value

    def telemetry(self) -> dict[str, object]:
        input_price = self._env_price("RADAR_LLM_INPUT_USD_PER_MILLION")
        output_price = self._env_price("RADAR_LLM_OUTPUT_USD_PER_MILLION")
        estimated_cost_usd: float | None = None
        if input_price is not None and output_price is not None:
            estimated_cost_usd = (
                self.prompt_tokens * input_price
                + self.completion_tokens * output_price
            ) / 1_000_000.0

        return {
            "calls": self.call_count,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "avg_latency_ms": round(
                self.elapsed_ms / self.call_count if self.call_count else 0.0,
                3,
            ),
            "estimated_cost_usd": estimated_cost_usd,
        }

    def score(self, text: str) -> float:
        if not text.strip():
            return 0.5
        decision = self._decision(self._request(text))
        self.last_decision = decision
        if decision.relevance == "review":
            return 0.5
        direction = 1.0 if decision.relevance == "relevant" else -1.0
        return 0.5 + direction * (0.5 * decision.confidence)
