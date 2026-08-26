from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping

from .db import connect, get_norm, utc_now
from .hr_impact import HR_IMPACT_VERSION, assess_hr_impact

SCHEMA = """
CREATE TABLE IF NOT EXISTS norm_hr_impact (
    norm_id TEXT PRIMARY KEY,
    input_fingerprint TEXT NOT NULL,
    scope TEXT NOT NULL,
    level TEXT NOT NULL,
    reason TEXT NOT NULL,
    action_recommended TEXT NOT NULL,
    requires_review INTEGER NOT NULL DEFAULT 0,
    impact_version INTEGER NOT NULL,
    evidence TEXT NOT NULL,
    assessed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_norm_hr_impact_level
    ON norm_hr_impact(level);
CREATE INDEX IF NOT EXISTS idx_norm_hr_impact_scope
    ON norm_hr_impact(scope);
"""

FINGERPRINT_FIELDS = (
    "labor_relevance",
    "topic",
    "title",
    "summary",
    "classification_text_excerpt",
    "classification_version",
)


def init_hr_impact_store() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def _fingerprint(record: Mapping[str, object]) -> str:
    payload = {field: record.get(field) for field in FINGERPRINT_FIELDS}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _evidence_json(impact: Mapping[str, object]) -> str:
    return json.dumps(
        impact.get("hr_impact_evidence") or [],
        ensure_ascii=False,
        sort_keys=True,
    )


def _persist(norm_id: str, fingerprint: str, impact: Mapping[str, object]) -> dict[str, object]:
    assessed_at = utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO norm_hr_impact (
                norm_id, input_fingerprint, scope, level, reason,
                action_recommended, requires_review, impact_version,
                evidence, assessed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(norm_id) DO UPDATE SET
                input_fingerprint = excluded.input_fingerprint,
                scope = excluded.scope,
                level = excluded.level,
                reason = excluded.reason,
                action_recommended = excluded.action_recommended,
                requires_review = excluded.requires_review,
                impact_version = excluded.impact_version,
                evidence = excluded.evidence,
                assessed_at = excluded.assessed_at
            """,
            (
                norm_id,
                fingerprint,
                str(impact["hr_impact_scope"]),
                str(impact["hr_impact_level"]),
                str(impact["hr_impact_reason"]),
                str(impact["hr_action_recommended"]),
                int(bool(impact["hr_impact_requires_review"])),
                int(impact["hr_impact_version"]),
                _evidence_json(impact),
                assessed_at,
            ),
        )
    return {
        **impact,
        "norm_id": norm_id,
        "input_fingerprint": fingerprint,
        "assessed_at": assessed_at,
    }


def assess_and_store(record: Mapping[str, object]) -> dict[str, object]:
    norm_id = str(record.get("id") or "").strip()
    if not norm_id:
        raise ValueError("La norma debe tener id para persistir su impacto")
    init_hr_impact_store()
    fingerprint = _fingerprint(record)
    impact = assess_hr_impact(record)
    return _persist(norm_id, fingerprint, impact)


def _row_to_dict(row) -> dict[str, object]:
    return {
        "norm_id": str(row["norm_id"]),
        "input_fingerprint": str(row["input_fingerprint"]),
        "hr_impact_scope": str(row["scope"]),
        "hr_impact_level": str(row["level"]),
        "hr_impact_reason": str(row["reason"]),
        "hr_action_recommended": str(row["action_recommended"]),
        "hr_impact_requires_review": bool(row["requires_review"]),
        "hr_impact_version": int(row["impact_version"]),
        "hr_impact_evidence": json.loads(str(row["evidence"] or "[]")),
        "assessed_at": str(row["assessed_at"]),
    }


def _impact_for_record(record: Mapping[str, object]) -> dict[str, object] | None:
    """Return cached impact for one already-loaded norm, refreshing only when stale."""
    if str(record.get("labor_relevance") or "") == "not_labor":
        return None

    norm_id = str(record.get("id") or "").strip()
    if not norm_id:
        return None
    fingerprint = _fingerprint(record)

    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM norm_hr_impact WHERE norm_id = ?",
            (norm_id,),
        ).fetchone()

    if (
        row is None
        or int(row["impact_version"] or 0) < HR_IMPACT_VERSION
        or str(row["input_fingerprint"] or "") != fingerprint
    ):
        impact = assess_hr_impact(record)
        return _persist(norm_id, fingerprint, impact)
    return _row_to_dict(row)


def get_hr_impact(norm_id: str) -> dict[str, object] | None:
    """Return cached impact, refreshing it when classifier inputs changed."""
    init_hr_impact_store()
    norm = get_norm(norm_id)
    if norm is None:
        return None
    return _impact_for_record(dict(norm))


def impacts_for_records(records: Iterable[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    """Return impacts for visible rows without re-reading each norm from SQLite."""
    init_hr_impact_store()
    result: dict[str, dict[str, object]] = {}
    for raw_record in records:
        record = dict(raw_record)
        impact = _impact_for_record(record)
        if impact is not None:
            result[str(record["id"])] = impact
    return result
