from __future__ import annotations

from .db import connect


def _dedupe(rows):
    seen: set[tuple[str, str, str]] = set()
    result = []
    for row in rows:
        key = (str(row["id"]), str(row["relation_type"]), str(row["relation_direction"]))
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def list_related_norms(norm_id: str):
    """Return norm-to-norm relations in either stored direction.

    `relation_direction` is relative to the norm being viewed:
    - outgoing: current norm is `from_*`
    - incoming: current norm is `to_*`
    """
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT n.*, dr.relation_type, dr.note,
                   'outgoing' AS relation_direction
            FROM document_relations AS dr
            JOIN norms AS n ON n.id = dr.to_id
            WHERE dr.from_kind = 'norm'
              AND dr.from_id = ?
              AND dr.to_kind = 'norm'

            UNION ALL

            SELECT n.*, dr.relation_type, dr.note,
                   'incoming' AS relation_direction
            FROM document_relations AS dr
            JOIN norms AS n ON n.id = dr.from_id
            WHERE dr.to_kind = 'norm'
              AND dr.to_id = ?
              AND dr.from_kind = 'norm'

            ORDER BY publication_date DESC, title
            """,
            (norm_id, norm_id),
        ).fetchall()
    return _dedupe(rows)


def list_related_case_law(norm_id: str):
    """Return jurisprudence related to a norm in either stored direction."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT cl.*, dr.relation_type, dr.note,
                   'outgoing' AS relation_direction
            FROM document_relations AS dr
            JOIN case_law AS cl ON cl.id = dr.to_id
            WHERE dr.from_kind = 'norm'
              AND dr.from_id = ?
              AND dr.to_kind = 'case_law'

            UNION ALL

            SELECT cl.*, dr.relation_type, dr.note,
                   'incoming' AS relation_direction
            FROM document_relations AS dr
            JOIN case_law AS cl ON cl.id = dr.from_id
            WHERE dr.to_kind = 'norm'
              AND dr.to_id = ?
              AND dr.from_kind = 'case_law'

            ORDER BY decision_date DESC, publication_date DESC, title
            """,
            (norm_id, norm_id),
        ).fetchall()
    return _dedupe(rows)
