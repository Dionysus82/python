"""JSON-safe values for API responses. Dates use DD MMM YYYY."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from app.domain.dates import format_date, format_timestamp


def jsonable(value):
    if isinstance(value, Decimal):
        return f"{value:.2f}" if value == value.quantize(Decimal("0.01")) else format(value, "f")
    if isinstance(value, datetime):
        return format_timestamp(value)
    if isinstance(value, date):
        return format_date(value)
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value
