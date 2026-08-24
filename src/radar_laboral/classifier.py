from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from typing import Protocol

CLASSIFIER_VERSION = 4


class SemanticScorer(Protocol):
    """Optional semantic signal used only for uncertain rule-based cases.

    Implementations may use embeddings, NLI or another local model. The score
    is an evidence signal in [0, 1], not a calibrated legal probability.
    """

    name: str

    def score(self, text: str) -> float:
        ...


def _normalize(value: object | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text.lower()).strip()


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


LABOR_ISSUERS = (
    "trabajo y promocion del empleo",
    "ministerio de trabajo",
    "superintendencia nacional de fiscalizacion laboral",
    "sunafil",
    "tribunal de fiscalizacion laboral",
)

ADMINISTRATIVE_PATTERNS = (
    "designan ",
    "designar ",
    "designacion temporal",
    "designacion de asesor",
    "designacion de funcionario",
    "conclusion de la designacion",
    "conclusion de designacion",
    "nombran ",
    "nombrar ",
    "aceptan renuncia",
    "aceptan la renuncia",
    "aceptar renuncia",
    "aceptar la renuncia",
    "dan por concluida",
    "dar por concluida",
    "encargan ",
    "encargar ",
    "encargo de puesto",
    "conclusion de la encargatura",
    "autorizan viaje",
    "autorizacion de viaje",
    "conforman grupo de trabajo",
    "conforman comision",
    "delegan facultades",
    "manual de perfiles de puestos",
)

TOPIC_PATTERNS: dict[str, tuple[str, ...]] = {
    "Remuneraciones y beneficios": (
        "remuneracion minima",
        "remuneraciones",
        "salario",
        "gratificacion",
        "compensacion por tiempo de servicios",
        " cts ",
        "asignacion familiar",
        "participacion en las utilidades",
        "utilidades de los trabajadores",
    ),
    "Jornada y descansos": (
        "jornada de trabajo",
        "jornada laboral",
        "horas extras",
        "sobretiempo",
        "descanso semanal",
        "descanso remunerado",
        "vacaciones",
    ),
    "Contratación laboral": (
        "contrato de trabajo",
        "contratacion laboral",
        "periodo de prueba",
        "modalidades formativas laborales",
        "modalidad formativa laboral",
    ),
    "Desvinculación": (
        "despido",
        "cese colectivo",
        "indemnizacion por despido",
        "extincion del contrato de trabajo",
    ),
    "Seguridad y salud en el trabajo": (
        "seguridad y salud en el trabajo",
        "accidente de trabajo",
        "enfermedad ocupacional",
        "comite de seguridad y salud",
    ),
    "Inspección laboral": (
        "inspeccion del trabajo",
        "sistema de inspeccion del trabajo",
        "ley general de inspeccion del trabajo",
        "funcion inspectiva",
        "funciones inspectivas",
        "fiscalizacion laboral",
        "infracciones sociolaborales",
        "tribunal de fiscalizacion laboral",
        "actuaciones inspectivas",
    ),
    "Relaciones colectivas": (
        "negociacion colectiva",
        "convencion colectiva",
        "sindicato",
        "sindical",
        "huelga",
        "relaciones colectivas de trabajo",
    ),
    "Tercerización e intermediación": (
        "tercerizacion",
        "intermediacion laboral",
        "empresa tercerizadora",
    ),
    "Teletrabajo": ("teletrabajo", "teletrabajador"),
    "Hostigamiento y acoso": ("hostigamiento sexual", "acoso laboral"),
    "Igualdad y no discriminación": (
        "igualdad salarial",
        "discriminacion laboral",
        "igual remuneracion",
    ),
    "Licencias y protección familiar": (
        "licencia por maternidad",
        "licencia por paternidad",
        "licencia laboral",
        "descanso prenatal",
        "descanso postnatal",
        "lactancia materna",
    ),
    "Trabajadores extranjeros": ("trabajador extranjero", "trabajadores extranjeros"),
    "Planilla y registros": ("planilla electronica", "t-registro", "plame"),
    "Protección de datos laborales": (
        "datos personales de los trabajadores",
        "datos personales del trabajador",
    ),
}

# References are deliberately explicit. They are strong positive evidence but
# do not replace topic classification or the review state for ambiguous cases.
STRONG_LABOR_REFERENCES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "régimen laboral privado",
        (
            "decreto legislativo 728",
            "ley de productividad y competitividad laboral",
            "decreto supremo 003-97-tr",
        ),
    ),
    (
        "seguridad y salud en el trabajo",
        ("ley 29783", "ley de seguridad y salud en el trabajo"),
    ),
    (
        "teletrabajo",
        ("ley 31572", "ley del teletrabajo"),
    ),
    (
        "inspección del trabajo",
        ("ley 28806", "ley general de inspeccion del trabajo"),
    ),
    (
        "cts",
        ("decreto legislativo 650", "ley de compensacion por tiempo de servicios"),
    ),
    (
        "gratificaciones",
        ("ley 27735", "gratificaciones para los trabajadores del regimen de la actividad privada"),
    ),
    (
        "descansos remunerados",
        ("decreto legislativo 713", "descansos remunerados de los trabajadores"),
    ),
)

GENERIC_LABOR_TERMS = (
    "trabajador",
    "trabajadores",
    "empleador",
    "empleadores",
    "empleo",
    "laboral",
    "relacion de trabajo",
    "relaciones laborales",
)

GENERAL_SCOPE_TYPES = (
    "ley",
    "decreto supremo",
    "decreto legislativo",
    "decreto de urgencia",
)


def _semantic_text(record: Mapping[str, object]) -> str:
    values = (
        record.get("document_type"),
        record.get("number"),
        record.get("title"),
        record.get("summary"),
        record.get("issuer"),
        record.get("classification_text_excerpt"),
    )
    return "\n".join(str(value).strip() for value in values if value)


def classify_labor(
    record: Mapping[str, object],
    *,
    semantic_scorer: SemanticScorer | None = None,
) -> dict[str, object]:
    """Classify a legal document with explainable rules plus optional semantics.

    The semantic scorer never overrides a strong administrative exclusion and
    is only allowed to resolve the uncertain zone. `classification_score` is
    an evidence score, not a calibrated probability of legal relevance.
    """

    title = _normalize(record.get("title"))
    summary = _normalize(record.get("summary"))
    excerpt = _normalize(record.get("classification_text_excerpt"))
    issuer = _normalize(record.get("issuer"))
    document_type = _normalize(record.get("document_type"))
    haystack = f" {title} {summary} {excerpt} "

    issuer_is_labor = any(pattern in issuer for pattern in LABOR_ISSUERS)
    is_administrative = any(pattern in title for pattern in ADMINISTRATIVE_PATTERNS)
    has_generic_labor_term = any(term in haystack for term in GENERIC_LABOR_TERMS)
    is_general_scope = any(kind in document_type for kind in GENERAL_SCOPE_TYPES)

    topics: list[str] = []
    topic_hits: list[str] = []
    for topic, patterns in TOPIC_PATTERNS.items():
        matched = next((pattern for pattern in patterns if pattern in haystack), None)
        if matched:
            topics.append(topic)
            topic_hits.append(matched.strip())

    reference_hits: list[str] = []
    for label, patterns in STRONG_LABOR_REFERENCES:
        if any(pattern in haystack for pattern in patterns):
            reference_hits.append(label)

    positive_evidence: list[dict[str, object]] = []
    negative_evidence: list[dict[str, object]] = []

    score = 0.03
    if topics:
        topic_weight = 0.65 + min(0.10, 0.05 * (len(topics) - 1))
        score += topic_weight
        positive_evidence.append(
            {
                "code": "specific_labor_topic",
                "weight": round(topic_weight, 2),
                "detail": ", ".join(topics),
            }
        )
    if reference_hits:
        score += 0.60
        positive_evidence.append(
            {
                "code": "labor_legal_reference",
                "weight": 0.60,
                "detail": ", ".join(reference_hits),
            }
        )
    if issuer_is_labor:
        score += 0.18
        positive_evidence.append(
            {"code": "labor_issuer", "weight": 0.18, "detail": str(record.get("issuer") or "")}
        )
    if has_generic_labor_term:
        score += 0.08
        positive_evidence.append(
            {"code": "generic_labor_language", "weight": 0.08, "detail": "terminología laboral general"}
        )
    if is_general_scope:
        score += 0.06
        positive_evidence.append(
            {"code": "general_scope_rule", "weight": 0.06, "detail": str(record.get("document_type") or "")}
        )
    if is_administrative:
        score -= 0.95
        negative_evidence.append(
            {
                "code": "administrative_personnel_act",
                "weight": -0.95,
                "detail": "acto administrativo de personal/gestión",
            }
        )

    rule_score = _clamp(score)
    semantic_score: float | None = None
    semantic_model: str | None = None

    if is_administrative:
        relevance = "not_labor"
        final_score = rule_score
        method = "rules_v4"
    elif rule_score >= 0.68 and (topics or reference_hits):
        relevance = "relevant"
        final_score = rule_score
        method = "rules_v4"
    elif semantic_scorer is not None:
        try:
            semantic_score = _clamp(float(semantic_scorer.score(_semantic_text(record))))
            semantic_model = str(getattr(semantic_scorer, "name", semantic_scorer.__class__.__name__))
        except Exception:
            semantic_score = None
            semantic_model = str(getattr(semantic_scorer, "name", semantic_scorer.__class__.__name__))

        if semantic_score is None:
            final_score = rule_score
            method = "rules_v4_semantic_unavailable"
        else:
            final_score = _clamp((0.45 * rule_score) + (0.55 * semantic_score))
            method = "hybrid_v4"

        if semantic_score is not None and semantic_score >= 0.80 and final_score >= 0.55:
            relevance = "relevant"
        elif semantic_score is not None and semantic_score <= 0.20 and rule_score <= 0.20:
            relevance = "not_labor"
        elif rule_score <= 0.20 and not issuer_is_labor and not is_general_scope and not topics:
            relevance = "not_labor"
        else:
            relevance = "review"
    elif rule_score <= 0.20 and not issuer_is_labor and not is_general_scope and not topics:
        relevance = "not_labor"
        final_score = rule_score
        method = "rules_v4"
    else:
        relevance = "review"
        final_score = rule_score
        method = "rules_v4"

    reasons: list[str] = []
    if topics:
        reasons.append("materia laboral específica")
    if reference_hits:
        reasons.append("referencia normativa laboral explícita")
    if issuer_is_labor:
        reasons.append("entidad laboral")
    if has_generic_labor_term:
        reasons.append("terminología laboral general")
    if is_general_scope:
        reasons.append("norma de alcance general")
    if is_administrative:
        reasons.append("acto administrativo de personal/gestión")
    if semantic_score is not None:
        reasons.append(f"señal semántica {semantic_score:.2f} ({semantic_model})")
    if relevance == "not_labor" and not reasons:
        reasons.append("sin señales laborales suficientes")
    elif relevance == "not_labor" and has_generic_labor_term and not issuer_is_labor:
        reasons.append("señal laboral genérica insuficiente")
    if relevance == "review":
        reasons.append("evidencia insuficiente para exclusión automática")

    return {
        "labor_relevance": relevance,
        "topic": ", ".join(topics) if topics else None,
        "relevance_reason": "; ".join(dict.fromkeys(reasons)),
        "classification_version": CLASSIFIER_VERSION,
        "classification_score": round(final_score, 4),
        "rule_score": round(rule_score, 4),
        "semantic_score": round(semantic_score, 4) if semantic_score is not None else None,
        "semantic_model": semantic_model,
        "classification_method": method,
        "requires_review": relevance == "review",
        "classification_evidence": {
            "positive": positive_evidence,
            "negative": negative_evidence,
            "topic_hits": topic_hits,
            "reference_hits": reference_hits,
        },
    }
