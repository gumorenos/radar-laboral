from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping

HR_IMPACT_VERSION = 1


def _normalize(value: object | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text.lower()).strip()


PROJECT_SIGNALS = (
    "proyecto de decreto",
    "proyecto de ley",
    "proyecto normativo",
    "publicacion del proyecto",
    "publicar el proyecto",
    "prepublicacion",
)

POLICY_SIGNALS = (
    "politica nacional",
    "estrategia nacional",
    "sistema de informacion del mercado laboral",
    "laboratorio de innovacion laboral",
    "grupo de trabajo",
    "mesa de trabajo",
    "comision multisectorial",
    "servicio de orientacion",
    "observatorio",
)

# These signals are intentionally stronger than generic phrases such as
# "establecen medidas". Impact triage must not infer a direct employer
# obligation merely because an authority announces administrative measures.
DIRECT_CHANGE_SIGNALS = (
    "modifica el reglamento",
    "modifican el reglamento",
    "aprueba el reglamento",
    "aprueban el reglamento",
    "regula ",
    "regulan ",
    "prohibe ",
    "prohiben ",
    "infracciones",
    "obligacion",
    "obligaciones",
)

HIGH_DIRECT_TOPICS = {
    "Remuneraciones y beneficios",
    "Jornada y descansos",
    "Contratación laboral",
    "Desvinculación",
    "Seguridad y salud en el trabajo",
    "Relaciones colectivas",
    "Tercerización e intermediación",
    "Teletrabajo",
    "Hostigamiento y acoso",
    "Igualdad y no discriminación",
    "Licencias y protección familiar",
    "Trabajadores extranjeros",
    "Planilla y registros",
}

MEDIUM_DIRECT_TOPICS = {
    "Inspección laboral",
    "Protección de datos laborales",
}

TOPIC_ACTIONS = {
    "Remuneraciones y beneficios": "Revisar conceptos de pago, beneficios y parametrización de planilla; validar fecha de aplicación y población afectada.",
    "Jornada y descansos": "Revisar jornadas, horarios, control de asistencia, sobretiempo y reglas de descanso o vacaciones aplicables.",
    "Contratación laboral": "Revisar modelos contractuales, altas y documentación de contratación para identificar cambios necesarios.",
    "Desvinculación": "Revisar causales, procedimiento, documentación y controles de desvinculación antes de ejecutar ceses afectados.",
    "Seguridad y salud en el trabajo": "Revisar el sistema de SST, procedimientos, registros, capacitación y responsabilidades potencialmente alcanzadas.",
    "Inspección laboral": "Revisar matriz de cumplimiento y evidencia documental ante fiscalización; identificar criterios o infracciones modificados.",
    "Relaciones colectivas": "Revisar procedimientos y documentación de relaciones colectivas, negociación y gestión sindical que puedan resultar alcanzados.",
    "Tercerización e intermediación": "Revisar contratos con terceros, desplazamiento de personal y controles sobre empresas principales, tercerizadoras o intermediadoras.",
    "Teletrabajo": "Revisar política, acuerdos, compensaciones, equipos, seguridad y controles asociados al teletrabajo.",
    "Hostigamiento y acoso": "Revisar protocolo, comité o delegado, canales, capacitación, medidas de protección y plazos internos.",
    "Igualdad y no discriminación": "Revisar categorías y funciones, política remunerativa, criterios objetivos y controles de no discriminación.",
    "Licencias y protección familiar": "Revisar políticas de licencias, documentación, plazos y tratamiento en asistencia y planilla.",
    "Trabajadores extranjeros": "Revisar contratos, calidad migratoria habilitante, registros y documentación de trabajadores extranjeros.",
    "Planilla y registros": "Revisar T-Registro/PLAME, datos maestros, formularios, parametrización y fechas de declaración aplicables.",
    "Protección de datos laborales": "Revisar tratamiento de datos laborales, accesos, información entregada al trabajador y controles de conservación/seguridad aplicables.",
}


def _topics(record: Mapping[str, object]) -> list[str]:
    raw = str(record.get("topic") or "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _first_action(topics: list[str]) -> str:
    for topic in topics:
        action = TOPIC_ACTIONS.get(topic)
        if action:
            return action
    return "Revisar la fuente oficial y confirmar alcance, vigencia, población afectada y cambios operativos antes de modificar procesos de RR.HH."


def assess_hr_impact(record: Mapping[str, object]) -> dict[str, object]:
    """Return an auditable operational HR-impact triage.

    This is analytical triage, not a statement of legal effect. It deliberately
    remains separate from `labor_relevance`: a document may clearly belong to
    labor law while having only indirect or low operational impact for HR.
    """

    relevance = str(record.get("labor_relevance") or "")
    title = _normalize(record.get("title"))
    summary = _normalize(record.get("summary"))
    excerpt = _normalize(record.get("classification_text_excerpt"))
    haystack = f" {title} {summary} {excerpt} "
    topics = _topics(record)

    project_hits = [signal for signal in PROJECT_SIGNALS if signal in haystack]
    policy_hits = [signal for signal in POLICY_SIGNALS if signal in haystack]
    direct_hits = [signal for signal in DIRECT_CHANGE_SIGNALS if signal in haystack]

    evidence: list[dict[str, object]] = []
    if topics:
        evidence.append({"code": "labor_topics", "detail": topics})
    if project_hits:
        evidence.append({"code": "project_signal", "detail": project_hits})
    if policy_hits:
        evidence.append({"code": "policy_signal", "detail": policy_hits})
    if direct_hits:
        evidence.append({"code": "direct_change_signal", "detail": direct_hits})

    if relevance == "not_labor":
        return {
            "hr_impact_scope": "none",
            "hr_impact_level": "none",
            "hr_impact_reason": "Documento clasificado como no laboral; no se asigna impacto operativo de RR.HH.",
            "hr_action_recommended": "Sin acción de RR.HH. por clasificación automática; revisar solo si existe contexto adicional.",
            "hr_impact_requires_review": False,
            "hr_impact_version": HR_IMPACT_VERSION,
            "hr_impact_evidence": evidence,
        }

    if project_hits:
        return {
            "hr_impact_scope": "potential",
            "hr_impact_level": "medium",
            "hr_impact_reason": "Iniciativa o proyecto de materia laboral: puede generar cambios futuros, pero no debe tratarse como obligación vigente por esta señal.",
            "hr_action_recommended": "Monitorear aprobación, texto final y fecha de vigencia; no cambiar procesos únicamente por el proyecto.",
            "hr_impact_requires_review": True,
            "hr_impact_version": HR_IMPACT_VERSION,
            "hr_impact_evidence": evidence,
        }

    if relevance == "review":
        return {
            "hr_impact_scope": "unclear",
            "hr_impact_level": "low",
            "hr_impact_reason": "La relevancia laboral aún requiere revisión; el impacto operativo no debe elevarse automáticamente.",
            "hr_action_recommended": "Revisar la fuente oficial para confirmar materia laboral, alcance y vigencia antes de definir una acción operativa.",
            "hr_impact_requires_review": True,
            "hr_impact_version": HR_IMPACT_VERSION,
            "hr_impact_evidence": evidence,
        }

    if policy_hits:
        return {
            "hr_impact_scope": "indirect",
            "hr_impact_level": "low",
            "hr_impact_reason": "Documento de política, estrategia, sistema o coordinación laboral; su materia es laboral pero no muestra por sí sola un cambio operativo directo para RR.HH.",
            "hr_action_recommended": "Monitorear desarrollos posteriores y revisar si genera normas, procedimientos o requerimientos específicos para empleadores.",
            "hr_impact_requires_review": False,
            "hr_impact_version": HR_IMPACT_VERSION,
            "hr_impact_evidence": evidence,
        }

    high_topics = [topic for topic in topics if topic in HIGH_DIRECT_TOPICS]
    medium_topics = [topic for topic in topics if topic in MEDIUM_DIRECT_TOPICS]

    if high_topics:
        level = "high"
        scope = "direct"
        reason = "Materia laboral con incidencia potencial directa en procesos, obligaciones o controles de RR.HH."
    elif medium_topics:
        level = "high" if direct_hits else "medium"
        scope = "direct" if direct_hits else "indirect"
        reason = (
            "Materia laboral de fiscalización/datos con señal de cambio normativo directo."
            if direct_hits
            else "Materia laboral de fiscalización o datos con impacto operativo principalmente de seguimiento y cumplimiento."
        )
    elif direct_hits:
        level = "medium"
        scope = "direct"
        reason = "La norma contiene señales de cambio u obligación, aunque el tema de RR.HH. no está suficientemente tipificado."
    else:
        level = "low"
        scope = "indirect"
        reason = "Materia laboral clara sin una señal suficiente de cambio operativo directo en los temas tipificados."

    action = _first_action(topics)
    return {
        "hr_impact_scope": scope,
        "hr_impact_level": level,
        "hr_impact_reason": reason,
        "hr_action_recommended": action,
        "hr_impact_requires_review": False,
        "hr_impact_version": HR_IMPACT_VERSION,
        "hr_impact_evidence": evidence,
    }
