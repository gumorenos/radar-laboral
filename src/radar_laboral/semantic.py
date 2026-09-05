from __future__ import annotations

import math
from collections.abc import Sequence

DEFAULT_E5_MODEL = "intfloat/multilingual-e5-small"
DEFAULT_LOCAL_MODELS = (
    "intfloat/multilingual-e5-small",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)

POSITIVE_ANCHORS = (
    "derecho laboral peruano: contratación de trabajadores, contratos de trabajo y periodo de prueba",
    "derecho laboral peruano: remuneraciones, CTS, gratificaciones, vacaciones, jornada y horas extras",
    "derecho laboral peruano: despido, cese, indemnización y extinción del vínculo laboral",
    "derecho laboral peruano: seguridad y salud en el trabajo, accidentes y enfermedades ocupacionales",
    "derecho laboral peruano: SUNAFIL, inspección del trabajo, infracciones sociolaborales y multas",
    "derecho laboral peruano: negociación colectiva, sindicatos, huelga y relaciones colectivas",
    "derecho laboral peruano: teletrabajo, hostigamiento sexual, igualdad salarial y no discriminación",
    "derecho laboral peruano: tercerización, intermediación laboral, trabajadores extranjeros y licencias",
    "derecho laboral peruano: planilla electrónica, T-Registro y PLAME",
)

NEGATIVE_ANCHORS = (
    "acto administrativo interno que designa, nombra o acepta la renuncia de un funcionario público",
    "resolución administrativa que autoriza un viaje, encarga un puesto o delega facultades",
    "norma de presupuesto público, transferencia financiera o contratación pública sin regulación laboral",
    "acto de organización interna, estructura institucional, comisión o grupo de trabajo",
    "norma sectorial no laboral sobre permisos, infraestructura, comercio, ambiente o administración general",
)


class SentenceTransformerAnchorScorer:
    """Similarity-based semantic signal using a sentence-transformers model.

    The model is optional and is intended for experiments/offline evaluation.
    It is not part of the default Raspberry image. The returned score is an
    evidence signal in [0, 1], not a calibrated legal probability.
    """

    def __init__(
        self,
        model_name: str,
        *,
        positive_anchors: Sequence[str] = POSITIVE_ANCHORS,
        negative_anchors: Sequence[str] = NEGATIVE_ANCHORS,
        device: str = "cpu",
        query_prefix: str = "",
        passage_prefix: str = "",
        margin_scale: float = 8.0,
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "Instale radar-laboral[semantic] para usar el clasificador semántico"
            ) from exc

        self.name = model_name
        self.model = SentenceTransformer(model_name, device=device)
        self.query_prefix = query_prefix
        self.passage_prefix = passage_prefix
        self.margin_scale = float(margin_scale)
        self._positive = tuple(positive_anchors)
        self._negative = tuple(negative_anchors)
        anchor_texts = [f"{self.passage_prefix}{text}" for text in (*self._positive, *self._negative)]
        embeddings = self.model.encode(
            anchor_texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        split = len(self._positive)
        self._positive_embeddings = embeddings[:split]
        self._negative_embeddings = embeddings[split:]

    @staticmethod
    def _sigmoid(value: float) -> float:
        return 1.0 / (1.0 + math.exp(-value))

    def score(self, text: str) -> float:
        if not text.strip():
            return 0.5
        query_embedding = self.model.encode(
            [f"{self.query_prefix}{text}"],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )[0]
        positive_similarity = float((self._positive_embeddings @ query_embedding).max())
        negative_similarity = float((self._negative_embeddings @ query_embedding).max())
        margin = positive_similarity - negative_similarity
        return self._sigmoid(self.margin_scale * margin)


class E5SentenceTransformerScorer(SentenceTransformerAnchorScorer):
    """Multilingual E5 scorer preserving the query/passage convention."""

    def __init__(
        self,
        model_name: str = DEFAULT_E5_MODEL,
        *,
        positive_anchors: Sequence[str] = POSITIVE_ANCHORS,
        negative_anchors: Sequence[str] = NEGATIVE_ANCHORS,
        device: str = "cpu",
    ) -> None:
        super().__init__(
            model_name,
            positive_anchors=positive_anchors,
            negative_anchors=negative_anchors,
            device=device,
            query_prefix="query: ",
            passage_prefix="passage: ",
        )


def local_scorer(model_name: str, *, device: str = "cpu") -> SentenceTransformerAnchorScorer:
    """Build a model-aware scorer for offline experiments."""
    if "e5" in model_name.lower():
        return E5SentenceTransformerScorer(model_name=model_name, device=device)
    return SentenceTransformerAnchorScorer(model_name=model_name, device=device)
