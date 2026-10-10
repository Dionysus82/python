"""Hong Kong date formatting and the fixed demonstration clock."""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.config import get_settings

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def hk_zone() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def demo_today() -> date:
    raw = get_settings().demo_today
    year, month, day = (int(part) for part in raw.split("-"))
    return date(year, month, day)


def coerce_date(value: date | datetime | str | None) -> date | None:
    """Accept a date, a timestamp, an ISO date, or an already formatted DD MMM YYYY string."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(hk_zone()).date()
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text or text == "—":
            return None
        parts = text.split()
        if len(parts) >= 4 and parts[-1] == "HKT":
            parts = parts[:3]
        if len(parts) == 3 and parts[1] in MONTHS and parts[0].isdigit() and parts[2].isdigit():
            return date(int(parts[2]), MONTHS.index(parts[1]) + 1, int(parts[0]))
        head = text[:10]
        if len(head) == 10 and head[4] == "-" and head[7] == "-":
            try:
                year, month, day = (int(part) for part in head.split("-"))
            except ValueError:
                return None
            return date(year, month, day)
    return None


def format_date(value: date | datetime | str | None) -> str:
    parsed = coerce_date(value)
    if parsed is None:
        if isinstance(value, str) and value.strip() and value.strip() != "—":
            return value.strip()
        return "—"
    return f"{parsed.day:02d} {MONTHS[parsed.month - 1]} {parsed.year}"


def format_timestamp(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    local = value.astimezone(hk_zone())
    return f"{format_date(local.date())} {local.strftime('%H:%M')} HKT"


def parse_date(raw: str) -> date:
    year, month, day = (int(part) for part in raw.split("-"))
    return date(year, month, day)


def month_ends(start: date, end: date) -> list[date]:
    """Inclusive month-end dates from start's month through end's month."""
    from calendar import monthrange

    cursor = date(start.year, start.month, 1)
    found: list[date] = []
    while (cursor.year, cursor.month) <= (end.year, end.month):
        last = monthrange(cursor.year, cursor.month)[1]
        found.append(date(cursor.year, cursor.month, last))
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return found


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def fixed_calculated_at() -> datetime:
    """Timestamp stored on seeded demonstration calculations."""
    return datetime(2026, 10, 10, 1, 0, tzinfo=hk_zone())
