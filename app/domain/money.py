"""Currency conversion that never adds mixed currencies without a rate."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.domain.dates import fixed_calculated_at, format_date, format_timestamp

MONEY = Decimal("0.01")
RATE = Decimal("0.00000001")
CURRENCIES = ("HKD", "USD", "CNY", "EUR", "JPY")

FX_SOURCE = "Harbour Meridian Treasury Rate Card (synthetic)"
FX_METHOD = "demonstration mid-rate"
SUBLEDGER = "HMB Facility Subledger (synthetic)"
METRICS_STORE = "HMB Risk Metrics Store (synthetic)"
RATING_REGISTER = "HMB Internal Rating Register (synthetic)"
COLLATERAL_REGISTER = "HMB Collateral Register (synthetic)"
COVENANT_MONITOR = "HMB Covenant Monitor (synthetic)"
REVIEW_REGISTER = "HMB Credit Review Register (synthetic)"
ACTION_REGISTER = "HMB Management Action Register (synthetic)"
EWI_REGISTER = "HMB Early-Warning Register (synthetic)"
WATCHLIST_REGISTER = "HMB Watchlist Register (synthetic)"
ALERT_REGISTER = "HMB Financial Crime Indicator Register (synthetic)"
DEPOSIT_REGISTER = "HMB Deposit Register (synthetic)"
ASSESSMENT_REGISTER = "HMB Qualitative Assessment Register (synthetic)"


class MixedCurrencyError(ValueError):
    """Raised when amounts would be aggregated without a conversion basis."""


def to_decimal(value: object, places: Decimal = MONEY) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value.quantize(places)
    try:
        return Decimal(str(value)).quantize(places)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid amount: {value}") from exc


def convert_to_hkd(amount: Decimal, currency: str, rate: Decimal) -> Decimal:
    if currency not in CURRENCIES:
        raise MixedCurrencyError(f"Unsupported currency: {currency}")
    if currency == "HKD" and rate != Decimal("1"):
        normalised = rate.quantize(RATE)
        if normalised != Decimal("1.00000000"):
            raise MixedCurrencyError("HKD conversion rate must be 1.")
    return (amount * rate).quantize(MONEY)


def format_money(amount: Decimal | None, currency: str | None = None) -> str:
    if amount is None:
        return "—"
    quantised = amount.quantize(MONEY)
    text = f"{quantised:,.2f}"
    if currency:
        return f"{currency} {text}"
    return text


def conversion_basis(
    amount: Decimal,
    currency: str,
    rate: Decimal,
    rate_date: date,
    hkd_amount: Decimal,
    calculated_at: datetime | None = None,
) -> str:
    stamp = calculated_at or fixed_calculated_at()
    return (
        f"{format_money(amount, currency)} × {rate.quantize(RATE)} = {format_money(hkd_amount, 'HKD')}. "
        f"Rate date {format_date(rate_date)}. Source: {FX_SOURCE}. Method: {FX_METHOD}. "
        f"Calculated {format_timestamp(stamp)}."
    )


def sum_hkd(amounts: Sequence[Decimal | None]) -> Decimal:
    total = Decimal("0.00")
    for amount in amounts:
        if amount is None:
            raise MixedCurrencyError(
                "A component has no HKD equivalent. It was not treated as zero."
            )
        total += amount
    return total.quantize(MONEY)
