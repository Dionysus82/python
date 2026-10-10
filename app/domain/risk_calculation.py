"""Deterministic demonstration risk calculations.

The language model is not permitted to create or alter these numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app.config import load_json
from app.domain.dates import fixed_calculated_at, format_timestamp
from app.domain.money import to_decimal

ZERO = Decimal("0")
HUNDRED = Decimal("100")
ONE = Decimal("1")


@dataclass
class Component:
    key: str
    label: str
    weight: Decimal
    raw_value: str | None
    score: Decimal | None
    formula: str
    inputs: dict[str, str]
    missing: bool
    source_record: str | None
    as_of: str | None
    data_quality: str


@dataclass
class ScoreExplanation:
    name: str
    version: str
    score: Decimal | None
    label: str
    components: list[Component]
    missing_inputs: list[str]
    formula: str
    calculated_at: datetime
    data_quality: str
    hackathon_notice: str = (
        "Hackathon demonstration only. This is not an internal credit rating "
        "and it is not an approved risk assessment."
    )

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "score": None if self.score is None else f"{self.score:.2f}",
            "label": self.label,
            "formula": self.formula,
            "calculated_at": format_timestamp(self.calculated_at),
            "data_quality": self.data_quality,
            "missing_inputs": self.missing_inputs,
            "hackathon_notice": self.hackathon_notice,
            "components": [
                {
                    "key": item.key,
                    "label": item.label,
                    "weight": f"{item.weight:.2f}",
                    "raw_value": item.raw_value,
                    "score": None if item.score is None else f"{item.score:.2f}",
                    "formula": item.formula,
                    "inputs": item.inputs,
                    "missing": item.missing,
                    "source_record": item.source_record,
                    "as_of": item.as_of,
                    "data_quality": item.data_quality,
                }
                for item in self.components
            ],
        }


@dataclass
class ScoreInputs:
    rating: int | None = None
    rating_record: str | None = None
    rating_as_of: str | None = None
    utilisation_pct: Decimal | None = None
    utilisation_record: str | None = None
    utilisation_as_of: str | None = None
    utilisation_quality: str = "ok"
    covenant_status: str | None = None
    covenant_record: str | None = None
    covenant_as_of: str | None = None
    open_ewi_count: int | None = None
    ewi_record: str | None = None
    liquidity_ratio: Decimal | None = None
    liquidity_record: str | None = None
    liquidity_as_of: str | None = None
    collateral_coverage: Decimal | None = None
    collateral_record: str | None = None
    collateral_as_of: str | None = None
    review_status: str | None = None
    review_record: str | None = None
    review_as_of: str | None = None
    watchlist_status: str | None = None
    watchlist_record: str | None = None
    calculated_at: datetime | None = None
    notes: list[str] = field(default_factory=list)


def _config() -> dict:
    return load_json("risk_score.json")  # type: ignore[return-value]


def _clamp(value: Decimal, low: Decimal = ZERO, high: Decimal = HUNDRED) -> Decimal:
    return max(low, min(high, value))


def probability_of_default(rating: int | None) -> Decimal | None:
    if rating is None:
        return None
    mapping = _config()["pd_by_rating"]
    raw = mapping.get(str(rating))
    if raw is None:
        return None
    return Decimal(raw)


def loss_given_default(coverage: Decimal | None) -> tuple[Decimal | None, str]:
    cfg = _config()
    if coverage is None:
        return None, "LGD was not calculated because collateral coverage is missing. Missing is not zero."
    base = Decimal(str(cfg["lgd_base"]))
    adjustment = Decimal(str(cfg["lgd_coverage_adjustment"]))
    floor = Decimal(str(cfg["lgd_floor"]))
    cap = Decimal(str(cfg["lgd_cap"]))
    extra = max(ZERO, coverage - ONE)
    lgd = min(cap, max(floor, base - extra * adjustment))
    formula = (
        f"LGD = min({cap}, max({floor}, {base} - max(0, coverage - 1) × {adjustment})); "
        f"coverage={coverage}"
    )
    return lgd.quantize(Decimal("0.0001")), formula


def expected_loss(
    pd: Decimal | None,
    lgd: Decimal | None,
    drawn: Decimal | None,
    undrawn: Decimal | None,
) -> tuple[Decimal | None, str]:
    cfg = _config()
    ccf = Decimal(str(cfg["ccf_undrawn"]))
    if pd is None or lgd is None or drawn is None or undrawn is None:
        return None, (
            "Expected loss was not calculated because PD, LGD, drawn exposure or "
            "undrawn commitment is missing. Missing values were not treated as zero."
        )
    ead = (drawn + ccf * undrawn).quantize(Decimal("0.01"))
    el = (pd * lgd * ead).quantize(Decimal("0.01"))
    formula = (
        f"EAD = drawn + {ccf} × undrawn = {ead}; "
        f"EL = PD × LGD × EAD = {pd} × {lgd} × {ead} = {el}. "
        "Demonstration calculation only. Not a regulatory capital measure."
    )
    return el, formula


def explain_score(inputs: ScoreInputs) -> ScoreExplanation:
    cfg = _config()
    weights = {key: Decimal(str(value)) for key, value in cfg["weights"].items()}
    components: list[Component] = []

    rating_score = None
    if inputs.rating is not None:
        span = Decimal(cfg["rating_max"] - cfg["rating_min"])
        rating_score = (Decimal(inputs.rating - cfg["rating_min"]) / span * HUNDRED).quantize(
            Decimal("0.01")
        )
    components.append(
        Component(
            key="credit_rating",
            label="Internal credit rating",
            weight=weights["credit_rating"],
            raw_value=None if inputs.rating is None else str(inputs.rating),
            score=rating_score,
            formula="(rating - 1) / 9 × 100, where 1 is strongest and 10 is default",
            inputs={"rating": "missing" if inputs.rating is None else str(inputs.rating)},
            missing=inputs.rating is None,
            source_record=inputs.rating_record,
            as_of=inputs.rating_as_of,
            data_quality="missing" if inputs.rating is None else "ok",
        )
    )

    util_score = None
    util_missing = inputs.utilisation_pct is None or inputs.utilisation_quality != "ok"
    if not util_missing and inputs.utilisation_pct is not None:
        util_score = _clamp(inputs.utilisation_pct).quantize(Decimal("0.01"))
    components.append(
        Component(
            key="utilisation",
            label="Highest facility utilisation",
            weight=weights["utilisation"],
            raw_value=None if inputs.utilisation_pct is None else f"{inputs.utilisation_pct}",
            score=util_score,
            formula="min(utilisation percent, 100). Unresolved conflicts are missing, not averaged.",
            inputs={
                "utilisation_pct": "missing" if inputs.utilisation_pct is None else str(inputs.utilisation_pct),
                "data_quality": inputs.utilisation_quality,
            },
            missing=util_missing,
            source_record=inputs.utilisation_record,
            as_of=inputs.utilisation_as_of,
            data_quality=inputs.utilisation_quality if not util_missing else "missing_or_conflict",
        )
    )

    covenant_score = None
    covenant_missing = inputs.covenant_status is None
    if inputs.covenant_status == "breach":
        covenant_score = HUNDRED
    elif inputs.covenant_status == "met":
        covenant_score = ZERO
    elif inputs.covenant_status == "watch":
        covenant_score = Decimal("40")
    components.append(
        Component(
            key="covenant",
            label="Covenant status",
            weight=weights["covenant"],
            raw_value=inputs.covenant_status,
            score=covenant_score,
            formula="breach=100, watch=40, met=0. No observation means missing, not met.",
            inputs={"status": inputs.covenant_status or "missing"},
            missing=covenant_missing or covenant_score is None,
            source_record=inputs.covenant_record,
            as_of=inputs.covenant_as_of,
            data_quality="missing" if covenant_score is None else "ok",
        )
    )

    ewi_score = None
    if inputs.open_ewi_count is not None:
        ewi_score = (min(Decimal(inputs.open_ewi_count), Decimal(3)) / Decimal(3) * HUNDRED).quantize(
            Decimal("0.01")
        )
    components.append(
        Component(
            key="early_warning",
            label="Open early-warning indicators",
            weight=weights["early_warning"],
            raw_value=None if inputs.open_ewi_count is None else str(inputs.open_ewi_count),
            score=ewi_score,
            formula="min(open count, 3) / 3 × 100. A missing register is not treated as zero indicators.",
            inputs={"open_count": "missing" if inputs.open_ewi_count is None else str(inputs.open_ewi_count)},
            missing=inputs.open_ewi_count is None,
            source_record=inputs.ewi_record,
            as_of=None,
            data_quality="missing" if inputs.open_ewi_count is None else "ok",
        )
    )

    liquidity_score = None
    reference = Decimal(str(cfg["liquidity_reference_ratio"]))
    if inputs.liquidity_ratio is not None:
        liquidity_score = _clamp(
            (reference - inputs.liquidity_ratio) / reference * HUNDRED
        ).quantize(Decimal("0.01"))
    components.append(
        Component(
            key="liquidity",
            label="Liquidity ratio",
            weight=weights["liquidity"],
            raw_value=None if inputs.liquidity_ratio is None else str(inputs.liquidity_ratio),
            score=liquidity_score,
            formula=f"clamp((({reference} - ratio) / {reference}) × 100, 0, 100)",
            inputs={"liquidity_ratio": "missing" if inputs.liquidity_ratio is None else str(inputs.liquidity_ratio)},
            missing=inputs.liquidity_ratio is None,
            source_record=inputs.liquidity_record,
            as_of=inputs.liquidity_as_of,
            data_quality="missing" if inputs.liquidity_ratio is None else "ok",
        )
    )

    collateral_score = None
    if inputs.collateral_coverage is not None:
        collateral_score = _clamp((ONE - inputs.collateral_coverage) * HUNDRED).quantize(Decimal("0.01"))
    components.append(
        Component(
            key="collateral_gap",
            label="Collateral coverage gap",
            weight=weights["collateral_gap"],
            raw_value=None if inputs.collateral_coverage is None else str(inputs.collateral_coverage),
            score=collateral_score,
            formula="clamp((1 - eligible collateral / drawn) × 100, 0, 100). Coverage above 1 scores 0 and does not cancel other risks.",
            inputs={
                "coverage": "missing" if inputs.collateral_coverage is None else str(inputs.collateral_coverage)
            },
            missing=inputs.collateral_coverage is None,
            source_record=inputs.collateral_record,
            as_of=inputs.collateral_as_of,
            data_quality="missing" if inputs.collateral_coverage is None else "ok",
        )
    )

    review_score = None
    if inputs.review_status == "overdue":
        review_score = HUNDRED
    elif inputs.review_status in {"completed", "current"}:
        review_score = ZERO
    components.append(
        Component(
            key="overdue_review",
            label="Annual credit review",
            weight=weights["overdue_review"],
            raw_value=inputs.review_status,
            score=review_score,
            formula="overdue=100, current=0. No review record is missing, not current.",
            inputs={"status": inputs.review_status or "missing"},
            missing=review_score is None,
            source_record=inputs.review_record,
            as_of=inputs.review_as_of,
            data_quality="missing" if review_score is None else "ok",
        )
    )

    watch_score = None
    if inputs.watchlist_status == "not_listed":
        watch_score = ZERO
    elif inputs.watchlist_status in {"watch", "enhanced_monitoring"}:
        watch_score = HUNDRED
    components.append(
        Component(
            key="watchlist",
            label="Watchlist status",
            weight=weights["watchlist"],
            raw_value=inputs.watchlist_status,
            score=watch_score,
            formula="enhanced monitoring or watch=100, not listed=0. No record is missing.",
            inputs={"status": inputs.watchlist_status or "missing"},
            missing=watch_score is None,
            source_record=inputs.watchlist_record,
            as_of=None,
            data_quality="missing" if watch_score is None else "ok",
        )
    )

    present = [item for item in components if item.score is not None]
    missing = [item.label for item in components if item.score is None]
    if not present:
        score = None
        quality = "insufficient_inputs"
        formula = "Score withheld because every component was missing."
    else:
        weight_sum = sum((item.weight for item in present), ZERO)
        score = sum((item.weight / weight_sum * (item.score or ZERO) for item in present), ZERO).quantize(
            Decimal("0.01")
        )
        quality = "partial_inputs" if missing else "complete_inputs"
        formula = (
            "Renormalise the configured weights of available components so they sum to 1, "
            "then calculate the weighted sum. Missing components are excluded, not scored as zero. "
            f"Configured weights version {cfg['version']}."
        )
    return ScoreExplanation(
        name=cfg["name"],
        version=cfg["version"],
        score=score,
        label="Hackathon demonstration concern score",
        components=components,
        missing_inputs=missing,
        formula=formula,
        calculated_at=inputs.calculated_at or fixed_calculated_at(),
        data_quality=quality,
    )


def utilisation_percent(drawn: Decimal | None, limit: Decimal | None) -> Decimal | None:
    drawn_q = to_decimal(drawn)
    limit_q = to_decimal(limit)
    if drawn_q is None or limit_q is None or limit_q == ZERO:
        return None
    return (drawn_q / limit_q * HUNDRED).quantize(Decimal("0.01"))


def limit_status(utilisation: Decimal | None, quality: str) -> str:
    if quality != "ok" or utilisation is None:
        return "unresolved_conflict" if quality == "conflict_unresolved" else "unknown"
    cfg = _config()
    if utilisation > Decimal(str(cfg["breach_utilisation_pct"])):
        return "breach"
    if utilisation >= Decimal(str(cfg["near_breach_utilisation_pct"])):
        return "near_breach"
    return "within_limit"
