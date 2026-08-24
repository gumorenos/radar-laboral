from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping

CLASSIFIER_VERSION = 3


def _normalize(value: object | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text.lower()).strip()


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
        "remuneracion minima", "remuneraciones", "salario", "gratificacion",
        "compensacion por tiempo de servicios", " cts ", "asignacion familiar",
        "participacion en las utilidades", "utilidades de los trabajadores",
    ),
    "Jornada y descansos": (
        "jornada de trabajo", "jornada laboral", "horas extras", "sobretiempo",
        "descanso semanal", "descanso remunerado", "vacaciones",
    ),
    "Contratación laboral": (
        "contrato de trabajo", "contratacion laboral", "periodo de prueba",
        "modalidades formativas laborales", "modalidad formativa laboral",
    ),
    "Desvinculación": (
        "despido", "cese colectivo", "indemnizacion por despido",
        "extincion del contrato de trabajo",
    ),
    "Seguridad y salud en el trabajo": (
        "seguridad y salud en el trabajo", "accidente de trabajo",
        "enfermedad ocupacional", "comite de seguridad y salud",
    ),
    "Inspección laboral": (
        "inspeccion del trabajo", "sistema de inspeccion del trabajo",
        "ley general de inspeccion del trabajo", "funcion inspectiva",
        "funciones inspectivas", "fiscalizacion laboral", "infracciones sociolaborales",
        "tribunal de fiscalizacion laboral", "actuaciones inspectivas",
    ),
    "Relaciones colectivas": (
        "negociacion colectiva", "convencion colectiva", "sindicato", "sindical",
        "huelga", "relaciones colectivas de trabajo",
    ),
    "Tercerización e intermediación": (
        "tercerizacion", "intermediacion laboral", "empresa tercerizadora",
    ),
    "Teletrabajo": ("teletrabajo", "teletrabajador"),
    "Hostigamiento y acoso": ("hostigamiento sexual", "acoso laboral"),
    "Igualdad y no discriminación": (
        "igualdad salarial", "discriminacion laboral", "igual remuneracion",
    ),
    "Licencias y protección familiar": (
        "licencia por maternidad", "licencia por paternidad", "licencia laboral",
        "descanso prenatal", "descanso postnatal", "lactancia materna",
    ),
    "Trabajadores extranjeros": ("trabajador extranjero", "trabajadores extranjeros"),
    "Planilla y registros": ("planilla electronica", "t-registro", "plame"),
    "Protección de datos laborales": (
        "datos personales de los trabajadores", "datos personales del trabajador",
    ),
}

GENERIC_LABOR_TERMS = (
    "trabajador", "trabajadores", "empleador", "empleadores", "empleo",
    "laboral", "relacion de trabajo", "relaciones laborales",
)

GENERAL_SCOPE_TYPES = (
    "ley",
    "decreto supremo",
    "decreto legislativo",
    "decreto de urgencia",
)


def classify_labor(record: Mapping[str, object]) -> dict[str, str | int | None]:
    title = _normalize(record.get("title"))
    summary = _normalize(record.get("summary"))
    issuer = _normalize(record.get("issuer"))
    document_type = _normalize(record.get("document_type"))
    haystack = f" {title} {summary} "

    issuer_is_labor = any(pattern in issuer for pattern in LABOR_ISSUERS)
    is_administrative = any(pattern in title for pattern in ADMINISTRATIVE_PATTERNS)
    has_generic_labor_term = any(term in haystack for term in GENERIC_LABOR_TERMS)
    is_general_scope = any(kind in document_type for kind in GENERAL_SCOPE_TYPES)

    topics: list[str] = []
    for topic, patterns in TOPIC_PATTERNS.items():
        if any(pattern in haystack for pattern in patterns):
            topics.append(topic)

    reasons: list[str] = []
    if issuer_is_labor:
        reasons.append("entidad laboral")
    if topics:
        reasons.append("materia laboral específica")
    if has_generic_labor_term:
        reasons.append("terminología laboral general")
    if is_administrative:
        reasons.append("acto administrativo de personal/gestión")
    if is_general_scope:
        reasons.append("norma de alcance general")

    if is_administrative:
        relevance = "not_labor"
    elif topics:
        relevance = "relevant"
    elif issuer_is_labor:
        relevance = "review"
    elif has_generic_labor_term and is_general_scope:
        relevance = "review"
    else:
        relevance = "not_labor"

    if relevance == "not_labor" and not reasons:
        reasons.append("sin señales laborales suficientes")
    elif relevance == "not_labor" and has_generic_labor_term and not issuer_is_labor:
        reasons.append("señal laboral genérica insuficiente")

    return {
        "labor_relevance": relevance,
        "topic": ", ".join(topics) if topics else None,
        "relevance_reason": "; ".join(dict.fromkeys(reasons)),
        "classification_version": CLASSIFIER_VERSION,
    }
