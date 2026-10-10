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


def format_date(value: date | datetime | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        value = value.astimezone(hk_zone()).date()
    return f"{value.day:02d} {MONTHS[value.month - 1]} {value.year}"


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
