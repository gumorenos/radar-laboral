from __future__ import annotations

from collections.abc import Mapping

from .db import connect, utc_now

CASE_LAW_COLUMNS = (
    "id",
    "source",
    "court",
    "document_type",
    "number",
    "docket_number",
    "title",
    "summary",
    "decision_date",
    "publication_date",
    "topic",
    "binding_level",
    "official_url",
    "pdf_url",
    "pdf_path",
    "sha256",
    "captured_at",
    "updated_at",
)


def upsert_case_law(record: Mapping[str, object]) -> dict[str, object]:
    item = dict(record)
    item.setdefault("captured_at", utc_now())
    values = [item.get(column) for column in CASE_LAW_COLUMNS]
    placeholders = ", ".join("?" for _ in CASE_LAW_COLUMNS)
    columns = ", ".join(CASE_LAW_COLUMNS)
    sql = f"""
        INSERT INTO case_law ({columns})
        VALUES ({placeholders})
        ON CONFLICT(id) DO UPDATE SET
            source = excluded.source,
            court = excluded.court,
            document_type = COALESCE(excluded.document_type, case_law.document_type),
            number = COALESCE(excluded.number, case_law.number),
            docket_number = COALESCE(excluded.docket_number, case_law.docket_number),
            title = excluded.title,
            summary = COALESCE(excluded.summary, case_law.summary),
            decision_date = COALESCE(excluded.decision_date, case_law.decision_date),
            publication_date = COALESCE(excluded.publication_date, case_law.publication_date),
            topic = COALESCE(excluded.topic, case_law.topic),
            binding_level = COALESCE(excluded.binding_level, case_law.binding_level),
            official_url = excluded.official_url,
            pdf_url = COALESCE(excluded.pdf_url, case_law.pdf_url),
            pdf_path = COALESCE(excluded.pdf_path, case_law.pdf_path),
            sha256 = COALESCE(excluded.sha256, case_law.sha256),
            updated_at = COALESCE(excluded.updated_at, case_law.updated_at)
    """
    with connect() as conn:
        conn.execute(sql, values)
    return item


def get_case_law(case_id: str):
    with connect() as conn:
        return conn.execute("SELECT * FROM case_law WHERE id = ?", (case_id,)).fetchone()


def _filters(
    *,
    court: str = "",
    document_type: str = "",
    topic: str = "",
    binding_level: str = "",
    date_from: str = "",
    date_to: str = "",
) -> tuple[list[str], list[str | int]]:
    clauses: list[str] = []
    params: list[str | int] = []
    for column, value in (
        ("court", court),
        ("document_type", document_type),
        ("topic", topic),
        ("binding_level", binding_level),
    ):
        if value:
            clauses.append(f"{column} = ?")
            params.append(value)
    if date_from:
        clauses.append("COALESCE(decision_date, publication_date) >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("COALESCE(decision_date, publication_date) <= ?")
        params.append(date_to)
    return clauses, params


def search_case_law(
    query: str = "",
    *,
    court: str = "",
    document_type: str = "",
    topic: str = "",
    binding_level: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 51,
    offset: int = 0,
):
    safe_limit = max(1, min(int(limit), 1000))
    safe_offset = max(0, int(offset))
    clauses, params = _filters(
        court=court,
        document_type=document_type,
        topic=topic,
        binding_level=binding_level,
        date_from=date_from,
        date_to=date_to,
    )
    if query:
        like = f"%{query}%"
        clauses.insert(
            0,
            "(title LIKE ? OR number LIKE ? OR docket_number LIKE ? OR summary LIKE ? OR court LIKE ? OR topic LIKE ?)",
        )
        params[0:0] = [like, like, like, like, like, like]
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([safe_limit, safe_offset])
    with connect() as conn:
        return conn.execute(
            f"""
            SELECT * FROM case_law
            {where}
            ORDER BY COALESCE(decision_date, publication_date) DESC,
                     publication_date DESC,
                     captured_at DESC,
                     id
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()


def _distinct(column: str) -> list[str]:
    allowed = {"court", "document_type", "topic", "binding_level"}
    if column not in allowed:
        raise ValueError(f"Campo jurisprudencial no permitido: {column}")
    with connect() as conn:
        rows = conn.execute(
            f"SELECT DISTINCT {column} FROM case_law "
            f"WHERE {column} IS NOT NULL AND {column} <> '' ORDER BY {column}"
        ).fetchall()
    return [str(row[0]) for row in rows]


def list_case_law_filter_options() -> dict[str, list[str]]:
    return {
        "courts": _distinct("court"),
        "document_types": _distinct("document_type"),
        "topics": _distinct("topic"),
        "binding_levels": _distinct("binding_level"),
    }
