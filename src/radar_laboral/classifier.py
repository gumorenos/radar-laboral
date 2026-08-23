from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping


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
    "nombran ",
    "nombrar ",
    "aceptan renuncia",
    "aceptar renuncia",
    "dan por concluida",
    "dar por concluida",
    "encargan ",
    "encargar ",
    "autorizan viaje",
    "autorizacion de viaje",
    "conforman grupo de trabajo",
    "conforman comision",
    "delegan facultades",
    "designacion de asesor",
    "designacion de funcionario",
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
        "inspeccion del trabajo", "fiscalizacion laboral", "infracciones sociolaborales",
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


def classify_labor(record: Mapping[str, object]) -> dict[str, str | None]:
    title = _normalize(record.get("title"))
    summary = _normalize(record.get("summary"))
    issuer = _normalize(record.get("issuer"))
    document_type = _normalize(record.get("document_type"))
    haystack = f" {title} {summary} "

    score = 0
    reasons: list[str] = []
    topics: list[str] = []

    if any(pattern in issuer for pattern in LABOR_ISSUERS):
        score += 2
        reasons.append("entidad laboral")

    for topic, patterns in TOPIC_PATTERNS.items():
        if any(pattern in haystack for pattern in patterns):
            topics.append(topic)

    if topics:
        # Una materia laboral específica basta para considerar el documento relevante.
        # Varias coincidencias refuerzan la señal, pero el score queda acotado.
        score += min(8, 4 * len(topics))
        reasons.append("materia laboral específica")

    if any(term in haystack for term in GENERIC_LABOR_TERMS):
        score += 1
        reasons.append("terminología laboral general")

    if any(pattern in title for pattern in ADMINISTRATIVE_PATTERNS):
        score -= 4
        reasons.append("acto administrativo de personal/gestión")

    if any(kind in document_type for kind in ("ley", "decreto supremo", "decreto legislativo")) and topics:
        score += 1
        reasons.append("norma de alcance general")

    if score >= 4:
        relevance = "relevant"
    elif score >= 1:
        relevance = "review"
    else:
        relevance = "not_labor"

    return {
        "labor_relevance": relevance,
        "topic": ", ".join(topics) if topics else None,
        "relevance_reason": "; ".join(dict.fromkeys(reasons)) or "sin señales laborales suficientes",
    }
