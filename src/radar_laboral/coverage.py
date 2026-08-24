from __future__ import annotations

from datetime import date, timedelta

from .db import connect, utc_now

DEFAULT_SOURCE = "El Peruano"
MAX_SUMMARY_DAYS = 3660

SCHEMA = """
CREATE TABLE IF NOT EXISTS source_coverage_days (
    source TEXT NOT NULL,
    coverage_date TEXT NOT NULL,
    record_count INTEGER NOT NULL DEFAULT 0,
    relevant_count INTEGER NOT NULL DEFAULT 0,
    review_count INTEGER NOT NULL DEFAULT 0,
    is_complete INTEGER NOT NULL DEFAULT 0,
    checked_at TEXT NOT NULL,
    PRIMARY KEY (source, coverage_date)
);

CREATE INDEX IF NOT EXISTS idx_source_coverage_complete_date
    ON source_coverage_days(source, is_complete, coverage_date);
"""


def init_coverage() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def mark_coverage_day(
    day: date,
    *,
    record_count: int,
    relevant_count: int = 0,
    review_count: int = 0,
    is_complete: bool,
    source: str = DEFAULT_SOURCE,
) -> None:
    """Record a successful source check for one day.

    A current-day check can be stored with ``is_complete=False`` because the
    official source may still publish additional documents later that day.
    Once a date has been marked complete, a later successful check never
    downgrades it back to incomplete.
    """
    init_coverage()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO source_coverage_days (
                source, coverage_date, record_count, relevant_count,
                review_count, is_complete, checked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, coverage_date) DO UPDATE SET
                record_count = excluded.record_count,
                relevant_count = excluded.relevant_count,
                review_count = excluded.review_count,
                is_complete = CASE
                    WHEN source_coverage_days.is_complete = 1 OR excluded.is_complete = 1
                    THEN 1 ELSE 0 END,
                checked_at = excluded.checked_at
            """,
            (
                source,
                day.isoformat(),
                max(0, int(record_count)),
                max(0, int(relevant_count)),
                max(0, int(review_count)),
                int(bool(is_complete)),
                utc_now(),
            ),
        )


def is_day_complete(day: date, *, source: str = DEFAULT_SOURCE) -> bool:
    init_coverage()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT is_complete
            FROM source_coverage_days
            WHERE source = ? AND coverage_date = ?
            """,
            (source, day.isoformat()),
        ).fetchone()
    return bool(row and row["is_complete"])


def complete_coverage_days(
    start_date: date,
    end_date: date,
    *,
    source: str = DEFAULT_SOURCE,
) -> set[date]:
    """Return complete days in a range with one indexed SQLite query."""
    if end_date < start_date:
        raise ValueError("La fecha final no puede ser anterior a la fecha inicial")

    init_coverage()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT coverage_date
            FROM source_coverage_days
            WHERE source = ? AND is_complete = 1
              AND coverage_date BETWEEN ? AND ?
            ORDER BY coverage_date
            """,
            (source, start_date.isoformat(), end_date.isoformat()),
        ).fetchall()
    return {date.fromisoformat(str(row["coverage_date"])) for row in rows}


def _missing_ranges(days: list[date]) -> list[dict[str, object]]:
    if not days:
        return []

    ranges: list[dict[str, object]] = []
    start = previous = days[0]
    for current in days[1:]:
        if current == previous + timedelta(days=1):
            previous = current
            continue
        ranges.append(
            {
                "start": start.isoformat(),
                "end": previous.isoformat(),
                "days": (previous - start).days + 1,
            }
        )
        start = previous = current
    ranges.append(
        {
            "start": start.isoformat(),
            "end": previous.isoformat(),
            "days": (previous - start).days + 1,
        }
    )
    return ranges


def coverage_summary(
    today: date,
    *,
    target_days: int = 365,
    source: str = DEFAULT_SOURCE,
) -> dict[str, object]:
    """Summarize verified historical coverage ending yesterday.

    The current day is deliberately excluded from the completion percentage:
    El Peruano can publish additional norms later during the same day.
    """
    init_coverage()
    safe_days = max(1, min(int(target_days), MAX_SUMMARY_DAYS))
    window_end = today - timedelta(days=1)
    window_start = window_end - timedelta(days=safe_days - 1)

    verified = complete_coverage_days(window_start, window_end, source=source)
    with connect() as conn:
        today_row = conn.execute(
            """
            SELECT record_count, relevant_count, review_count, is_complete, checked_at
            FROM source_coverage_days
            WHERE source = ? AND coverage_date = ?
            """,
            (source, today.isoformat()),
        ).fetchone()

    missing: list[date] = []
    current = window_start
    while current <= window_end:
        if current not in verified:
            missing.append(current)
        current += timedelta(days=1)

    verified_days = safe_days - len(missing)
    ranges = _missing_ranges(missing)
    today_check = None
    if today_row is not None:
        today_check = {
            "record_count": int(today_row["record_count"] or 0),
            "relevant_count": int(today_row["relevant_count"] or 0),
            "review_count": int(today_row["review_count"] or 0),
            "is_complete": bool(today_row["is_complete"]),
            "checked_at": str(today_row["checked_at"]),
        }

    return {
        "source": source,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "target_days": safe_days,
        "verified_days": verified_days,
        "missing_days": len(missing),
        "coverage_percent": round((verified_days / safe_days) * 100, 1),
        "first_missing": missing[0].isoformat() if missing else None,
        "last_missing": missing[-1].isoformat() if missing else None,
        "missing_ranges": ranges,
        "today_checked": today_check is not None,
        "today_check": today_check,
    }
