"""Deterministic claims from authorised records and trusted statements."""

from __future__ import annotations

import re
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import load_json
from app.domain.dates import format_date
from app.domain.money import conversion_basis, format_money, sum_hkd
from app.domain.risk_calculation import (
    ScoreInputs,
    expected_loss,
    explain_score,
    limit_status,
    loss_given_default,
    probability_of_default,
)
from app.models.tables import (
    Alert,
    CollateralValuation,
    CovenantObservation,
    Customer,
    Document,
    EarlyWarning,
    EvidenceStatement,
    Facility,
    FacilitySnapshot,
    ManagementAction,
    RatingHistory,
    Review,
    RiskMetric,
    WatchlistEntry,
)
from app.security.principal import Principal

DECIMAL_FAMILIES = {
    "utilisation_pct",
    "drawn_exposure",
    "contingent_exposure",
    "internal_credit_rating",
    "liquidity_ratio",
    "deposit_balance",
    "cash_reserves",
    "eligible_collateral",
}
STRING_FAMILIES = {"covenant_status", "annual_review_status", "watchlist_status", "repayment_status"}
SCORE_CFG = load_json("risk_score.json")


def family(metric_key: str) -> str:
    return metric_key.split(":", 1)[0]


def _comparable(metric_key: str, value: str | None):
    if value in (None, ""):
        return None
    kind = family(metric_key)
    if kind in DECIMAL_FAMILIES:
        try:
            return Decimal(value)
        except Exception:
            return None
    if kind in STRING_FAMILIES:
        return value.strip().lower()
    return None


def _citation_id() -> str:
    return uuid.uuid4().hex[:10]


def number_supported(value: str | None, text: str) -> bool:
    if not value:
        return True
    if value in text:
        return True
    try:
        number = Decimal(value)
    except Exception:
        return value.lower() in text.lower()
    patterns = []
    if number == number.to_integral():
        integer = int(number)
        patterns.append(rf"(?<!\d){integer}(?!\d)")
        patterns.append(rf"(?<!\d){integer:,}(?!\d)")
        patterns.append(rf"(?<!\d){integer:,.2f}(?!\d)")
    else:
        patterns.append(re.escape(f"{number:.2f}"))
        patterns.append(re.escape(f"{number:,.2f}"))
    return any(re.search(pattern, text) for pattern in patterns)


def validate_claims(
    session: Session,
    claims: list[dict],
    allowed: set[str],
    visible_documents: set[str],
) -> list[dict]:
    kept = []
    for claim in claims:
        if claim["claim_type"] == "missing":
            if claim.get("value"):
                continue
            kept.append(claim)
            continue
        citations = claim.get("citations") or []
        if not citations:
            continue
        valid = True
        for citation in citations:
            customer_id = citation.get("customer_id")
            if customer_id and customer_id not in allowed:
                valid = False
            document_id = citation.get("document_id")
            if document_id and document_id not in visible_documents:
                valid = False
            if citation.get("kind") == "database" and citation.get("record_table") == "facility_snapshots":
                row = session.get(FacilitySnapshot, citation.get("record_id"))
                if row is None or row.customer_id not in allowed:
                    valid = False
            if (
                citation.get("kind") == "document"
                and claim["claim_type"] != "calculation"
                and claim.get("value")
                and not number_supported(str(claim["value"]), citation.get("excerpt") or "")
            ):
                valid = False
        if valid:
            kept.append(claim)
    return kept


def _db_citation(**kwargs) -> dict:
    citation = {
        "kind": "database",
        "source_title": kwargs.get("source_system"),
        "original_filename": None,
        "document_id": None,
        "page": None,
        "sheet": None,
        "cell_range": None,
        "section": None,
        "paragraph": None,
        "authoring_function": None,
        "version": None,
        "viewer_route": None,
        "risk_domain": kwargs.get("risk_domain"),
        "reporting_date": kwargs.get("as_of_date"),
    }
    citation.update(kwargs)
    return citation


def _doc_citation(document: Document, statement: EvidenceStatement) -> dict:
    locator = statement.locator or {}
    return {
        "kind": "document",
        "source_title": document.title,
        "original_filename": document.original_filename,
        "document_id": document.document_id,
        "customer_id": statement.customer_id,
        "risk_domain": document.risk_domain,
        "reporting_date": document.reporting_date,
        "version": str(document.version),
        "authoring_function": document.authoring_function,
        "page": locator.get("page"),
        "sheet": locator.get("sheet"),
        "cell_range": locator.get("cell_range"),
        "section": locator.get("section") or locator.get("heading_path"),
        "paragraph": locator.get("paragraph"),
        "record_table": None,
        "record_id": None,
        "as_of_date": statement.as_of_date,
        "calculated_at": None,
        "unit": statement.unit,
        "currency": statement.currency,
        "hkd_equivalent": None,
        "source_system": document.authoring_function,
        "viewer_route": f"{document.source_viewer_route}&page={locator.get('page')}"
        if locator.get("page")
        else document.source_viewer_route,
        "excerpt": statement.text,
    }


def _latest_snapshots(session: Session, customer_id: str) -> list[FacilitySnapshot]:
    rows = session.scalars(
        select(FacilitySnapshot).where(FacilitySnapshot.customer_id == customer_id)
    ).all()
    if not rows:
        return []
    latest = max(row.as_of_date for row in rows)
    return [row for row in rows if row.as_of_date == latest]


def build_customer_claims(
    session: Session,
    principal: Principal,
    customer_id: str,
    visible_documents: set[str],
    *,
    historical: bool,
) -> list[dict]:
    customer = session.get(Customer, customer_id)
    if customer is None or customer_id not in _allowed_guard(principal, customer_id):
        return []
    snapshots = _latest_snapshots(session, customer_id)
    current_date = max((row.as_of_date for row in snapshots), default=None)
    atoms: list[dict] = []
    atoms.extend(_snapshot_atoms(session, customer, snapshots))
    atoms.extend(_rating_atoms(session, customer, historical))
    atoms.extend(_metric_atoms(session, customer, current_date, historical))
    atoms.extend(_statement_atoms(session, customer, visible_documents, principal, current_date, historical))
    atoms.extend(_register_atoms(session, customer, principal))
    atoms.extend(_calculation_atoms(session, customer, snapshots))
    return _fold(atoms)


def _allowed_guard(principal: Principal, customer_id: str) -> set[str]:
    """Defence in depth. The pipeline must already have applied the portfolio scope."""
    return {customer_id} if principal.can("customer.read") else set()


def _snapshot_atoms(session: Session, customer: Customer, snapshots: list[FacilitySnapshot]) -> list[dict]:
    facilities = {
        row.facility_id: row
        for row in session.scalars(select(Facility).where(Facility.customer_id == customer.customer_id)).all()
    }
    atoms = []
    for snapshot in snapshots:
        facility = facilities.get(snapshot.facility_id)
        name = facility.name if facility else snapshot.facility_id
        if snapshot.data_quality != "ok" or snapshot.drawn is None:
            atoms.append(
                _atom(
                    metric_key=f"drawn_unresolved:{snapshot.facility_id}",
                    as_of=snapshot.as_of_date,
                    value=None,
                    text=(
                        f"The facility subledger has not adopted a drawn amount for {snapshot.facility_id} "
                        f"({name}) as at {format_date(snapshot.as_of_date)}. "
                        "The missing amount was not treated as zero."
                    ),
                    claim_type="missing",
                    citations=[
                        _db_citation(
                            source_system=snapshot.source_system,
                            record_table="facility_snapshots",
                            record_id=snapshot.snapshot_id,
                            customer_id=customer.customer_id,
                            as_of_date=snapshot.as_of_date,
                            calculated_at=snapshot.calculated_at,
                            unit="HKD",
                            currency=snapshot.currency,
                            hkd_equivalent=None,
                            excerpt="No adopted drawn amount.",
                            risk_domain="credit",
                        )
                    ],
                    tags={"exposure", "limits", "general"},
                    customer_id=customer.customer_id,
                )
            )
            continue
        drawn_text = (
            f"Drawn exposure on {name} ({snapshot.facility_id}) is "
            f"{format_money(snapshot.drawn, snapshot.currency)} as at {format_date(snapshot.as_of_date)}."
        )
        if snapshot.currency != "HKD" and snapshot.drawn is not None and snapshot.hkd_drawn is not None:
            drawn_text += " " + conversion_basis(
                snapshot.drawn,
                snapshot.currency,
                snapshot.fx_rate,
                snapshot.fx_rate_date,
                snapshot.hkd_drawn,
                snapshot.calculated_at,
            )
        atoms.append(
            _atom(
                metric_key=f"drawn_exposure:{snapshot.facility_id}",
                as_of=snapshot.as_of_date,
                value=f"{snapshot.drawn:.2f}",
                text=drawn_text,
                claim_type="sourced_fact",
                citations=[_snapshot_citation(snapshot, drawn_text, "HKD" if snapshot.currency == "HKD" else snapshot.currency)],
                tags={"exposure", "facilities", "general"},
                customer_id=customer.customer_id,
                currency=snapshot.currency,
            )
        )
        if snapshot.contingent and snapshot.contingent > 0:
            text = (
                f"Contingent exposure on {name} ({snapshot.facility_id}) is "
                f"{format_money(snapshot.contingent, snapshot.currency)} as at {format_date(snapshot.as_of_date)}."
            )
            atoms.append(
                _atom(
                    metric_key=f"contingent_exposure:{snapshot.facility_id}",
                    as_of=snapshot.as_of_date,
                    value=f"{snapshot.contingent:.2f}",
                    text=text,
                    claim_type="sourced_fact",
                    citations=[_snapshot_citation(snapshot, text, snapshot.currency)],
                    tags={"exposure", "facilities", "collateral"},
                    customer_id=customer.customer_id,
                    currency=snapshot.currency,
                )
            )
        if snapshot.ccr and snapshot.ccr > 0:
            text = (
                f"Demonstration counterparty credit exposure on {name} ({snapshot.facility_id}) is "
                f"{format_money(snapshot.ccr, snapshot.currency)} as at {format_date(snapshot.as_of_date)}. "
                "Notional is not included in total exposure."
            )
            atoms.append(
                _atom(
                    metric_key=f"ccr_exposure:{snapshot.facility_id}",
                    as_of=snapshot.as_of_date,
                    value=f"{snapshot.ccr:.2f}",
                    text=text,
                    claim_type="sourced_fact",
                    citations=[_snapshot_citation(snapshot, text, snapshot.currency)],
                    tags={"exposure", "market"},
                    customer_id=customer.customer_id,
                    currency=snapshot.currency,
                )
            )
        if snapshot.utilisation_pct is not None:
            status = limit_status(snapshot.utilisation_pct, snapshot.data_quality)
            text = (
                f"Facility utilisation on {snapshot.facility_id} is {snapshot.utilisation_pct:.2f} percent "
                f"as at {format_date(snapshot.as_of_date)}. Limit status: {status.replace('_', ' ')}."
            )
            atoms.append(
                _atom(
                    metric_key=f"utilisation_pct:{snapshot.facility_id}",
                    as_of=snapshot.as_of_date,
                    value=f"{snapshot.utilisation_pct:.2f}",
                    text=text,
                    claim_type="sourced_fact",
                    citations=[_snapshot_citation(snapshot, text, "percent")],
                    tags={"limits", "exposure", "general"},
                    customer_id=customer.customer_id,
                    unit="percent",
                )
            )
    return atoms


def _snapshot_citation(snapshot: FacilitySnapshot, excerpt: str, unit: str) -> dict:
    return _db_citation(
        source_system=snapshot.source_system,
        record_table="facility_snapshots",
        record_id=snapshot.snapshot_id,
        customer_id=snapshot.customer_id,
        as_of_date=snapshot.as_of_date,
        calculated_at=snapshot.calculated_at,
        unit=unit,
        currency=snapshot.currency,
        hkd_equivalent=None if snapshot.hkd_drawn is None else f"{snapshot.hkd_drawn:.2f}",
        excerpt=excerpt,
        risk_domain="credit",
    )


def _rating_atoms(session: Session, customer: Customer, historical: bool) -> list[dict]:
    rows = session.scalars(
        select(RatingHistory)
        .where(RatingHistory.customer_id == customer.customer_id)
        .order_by(RatingHistory.as_of_date)
    ).all()
    if not rows:
        return []
    chosen = rows if historical else [rows[-1]]
    atoms = []
    for row in chosen:
        text = (
            f"The latest internal credit rating is {row.rating} on the Harbour Meridian demonstration scale "
            f"of 1 (strongest) to 10 (default), as at {format_date(row.as_of_date)}."
        )
        atoms.append(
            _atom(
                metric_key="internal_credit_rating",
                as_of=row.as_of_date,
                value=str(row.rating),
                text=text,
                claim_type="sourced_fact",
                citations=[
                    _db_citation(
                        source_system=row.source_system,
                        record_table="rating_history",
                        record_id=row.rating_id,
                        customer_id=customer.customer_id,
                        as_of_date=row.as_of_date,
                        calculated_at=row.calculated_at,
                        unit="rating",
                        currency=None,
                        hkd_equivalent=None,
                        excerpt=text,
                        risk_domain="credit",
                    )
                ],
                tags={"rating", "general", "change"},
                customer_id=customer.customer_id,
            )
        )
    if len(rows) >= 2:
        start, end = rows[0], rows[-1]
        movement = end.rating - start.rating
        trend = "stable"
        if movement >= int(SCORE_CFG["deterioration_notches"]):
            trend = "deteriorating"
        elif movement <= -int(SCORE_CFG["deterioration_notches"]):
            trend = "improving"
        elif movement > 0:
            trend = "slightly deteriorating"
        elif movement < 0:
            trend = "slightly improving"
        text = (
            f"Rule-based risk trend is {trend}. The internal credit rating moved from {start.rating} "
            f"on {format_date(start.as_of_date)} to {end.rating} on {format_date(end.as_of_date)}."
        )
        atoms.append(
            _atom(
                metric_key="risk_trend",
                as_of=end.as_of_date,
                value=trend,
                text=text,
                claim_type="rule",
                citations=[
                    _db_citation(
                        source_system=start.source_system,
                        record_table="rating_history",
                        record_id=start.rating_id,
                        customer_id=customer.customer_id,
                        as_of_date=start.as_of_date,
                        calculated_at=start.calculated_at,
                        unit="rating",
                        currency=None,
                        hkd_equivalent=None,
                        excerpt=f"Rating {start.rating}",
                        risk_domain="credit",
                    ),
                    _db_citation(
                        source_system=end.source_system,
                        record_table="rating_history",
                        record_id=end.rating_id,
                        customer_id=customer.customer_id,
                        as_of_date=end.as_of_date,
                        calculated_at=end.calculated_at,
                        unit="rating",
                        currency=None,
                        hkd_equivalent=None,
                        excerpt=f"Rating {end.rating}",
                        risk_domain="credit",
                    ),
                ],
                tags={"change", "rating", "general"},
                customer_id=customer.customer_id,
            )
        )
    return atoms


def _metric_atoms(session: Session, customer: Customer, current_date: date | None, historical: bool) -> list[dict]:
    rows = session.scalars(select(RiskMetric).where(RiskMetric.customer_id == customer.customer_id)).all()
    atoms = []
    interesting = {"liquidity_ratio", "deposit_balance", "cash_reserves"}
    for row in rows:
        if row.metric_key not in interesting:
            continue
        if not historical and current_date and row.as_of_date != current_date and row.metric_key != "liquidity_ratio":
            if row.as_of_date != current_date:
                continue
        if not historical and row.as_of_date != current_date:
            continue
        if row.numeric_value is None:
            continue
        if row.metric_key == "liquidity_ratio":
            text = (
                f"The demonstration liquidity ratio is {row.numeric_value} as at {format_date(row.as_of_date)}. "
                "This is not a regulatory liquidity metric."
            )
            tags = {"liquidity", "general"}
            unit = "ratio"
        elif row.metric_key == "cash_reserves":
            text = f"Cash reserves are {format_money(row.numeric_value, 'HKD')} as at {format_date(row.as_of_date)}."
            tags = {"liquidity"}
            unit = "HKD"
        else:
            continue
        atoms.append(
            _atom(
                metric_key=row.metric_key,
                as_of=row.as_of_date,
                value=f"{Decimal(row.numeric_value).quantize(Decimal('0.01'))}",
                text=text,
                claim_type="sourced_fact",
                citations=[
                    _db_citation(
                        source_system=row.source_system,
                        record_table="risk_metrics",
                        record_id=row.metric_id,
                        customer_id=customer.customer_id,
                        as_of_date=row.as_of_date,
                        calculated_at=row.calculated_at,
                        unit=unit,
                        currency=row.currency,
                        hkd_equivalent=None if row.hkd_equivalent is None else f"{row.hkd_equivalent:.2f}",
                        excerpt=text,
                        risk_domain=row.domain,
                    )
                ],
                tags=tags,
                customer_id=customer.customer_id,
            )
        )
    return atoms


def _statement_atoms(
    session: Session,
    customer: Customer,
    visible_documents: set[str],
    principal: Principal,
    current_date: date | None,
    historical: bool,
) -> list[dict]:
    rows = session.scalars(
        select(EvidenceStatement).where(EvidenceStatement.customer_id == customer.customer_id)
    ).all()
    documents = {
        row.document_id: row
        for row in session.scalars(select(Document).where(Document.document_id.in_(visible_documents or {""}))).all()
    }
    atoms = []
    for statement in rows:
        if statement.sensitivity == "aml" and not principal.can("aml.read"):
            continue
        if statement.document_id not in visible_documents:
            continue
        if statement.superseded and not historical:
            continue
        if (
            not historical
            and family(statement.metric_key) in DECIMAL_FAMILIES
            and statement.as_of_date
            and current_date
            and statement.as_of_date < current_date
        ):
            continue
        document = documents.get(statement.document_id)
        if document is None:
            continue
        text = statement.text
        if statement.stale:
            text = f"Stale evidence (as-of {format_date(statement.as_of_date)}): {statement.text}"
        tags = _tags_for(statement.metric_key)
        atoms.append(
            _atom(
                metric_key=statement.metric_key,
                as_of=statement.as_of_date,
                value=statement.numeric_value,
                text=text,
                claim_type="sourced_fact",
                citations=[_doc_citation(document, statement)],
                tags=tags,
                customer_id=customer.customer_id,
                stale=statement.stale,
                currency=statement.currency,
                unit=statement.unit,
            )
        )
    return atoms


def _tags_for(metric_key: str) -> set[str]:
    kind = family(metric_key)
    mapping = {
        "internal_credit_rating": {"rating", "general"},
        "utilisation_pct": {"limits", "exposure", "general"},
        "drawn_exposure": {"exposure", "facilities", "general"},
        "contingent_exposure": {"exposure", "collateral"},
        "liquidity_ratio": {"liquidity", "general"},
        "deposit_balance": {"liquidity"},
        "cash_reserves": {"liquidity"},
        "covenant_status": {"covenant", "general"},
        "annual_review_status": {"review", "general"},
        "early_warning": {"ewi", "general"},
        "watchlist_status": {"watchlist", "general"},
        "business_relationship": {"relationship", "facilities", "general"},
        "eligible_collateral": {"collateral", "market"},
        "fx_notional": {"market"},
        "irs_notional": {"market"},
        "aml_risk_classification": {"aml"},
        "tm_alert": {"aml"},
        "pep_indicator": {"aml"},
        "aml_periodic_review": {"aml", "review"},
        "sanctions_alert": {"aml"},
        "cdd_status": {"aml", "review"},
        "operational_incident": {"operational"},
        "repayment_status": {"liquidity", "rating"},
        "version_rule": {"change", "rating", "general"},
        "portfolio_membership": {"exposure"},
    }
    return set(mapping.get(kind, {"general"}))


def _register_atoms(session: Session, customer: Customer, principal: Principal) -> list[dict]:
    atoms = []
    for review in session.scalars(select(Review).where(Review.customer_id == customer.customer_id)).all():
        if review.sensitivity == "aml" and not principal.can("aml.read"):
            continue
        text = (
            f"The {review.review_type.replace('_', ' ')} was due on {format_date(review.due_date)} "
            f"and the status is {review.status}."
        )
        metric = "annual_review_status" if review.review_type == "annual_credit" else f"review:{review.review_type}"
        tags = {"review", "general"} if review.review_type == "annual_credit" else {"review", "aml"}
        atoms.append(
            _atom(
                metric_key=metric,
                as_of=review.due_date,
                value=review.status,
                text=text,
                claim_type="sourced_fact",
                citations=[
                    _db_citation(
                        source_system=review.source_system,
                        record_table="reviews",
                        record_id=review.review_id,
                        customer_id=customer.customer_id,
                        as_of_date=review.due_date,
                        calculated_at=None,
                        unit="status",
                        currency=None,
                        hkd_equivalent=None,
                        excerpt=text,
                        risk_domain="credit" if review.sensitivity == "standard" else "aml",
                    )
                ],
                tags=tags,
                customer_id=customer.customer_id,
            )
        )
    for action in session.scalars(
        select(ManagementAction).where(ManagementAction.customer_id == customer.customer_id)
    ).all():
        if action.sensitivity == "aml" and not principal.can("aml.read"):
            continue
        if action.status == "closed":
            continue
        text = (
            f"Outstanding action {action.action_id}: {action.description} "
            f"Owner: {action.owner_function}. Due {format_date(action.due_date)}. Status: {action.status}."
        )
        atoms.append(
            _atom(
                metric_key=f"management_action:{action.action_id}",
                as_of=action.due_date,
                value=action.status,
                text=text,
                claim_type="sourced_fact",
                citations=[
                    _db_citation(
                        source_system=action.source_system,
                        record_table="management_actions",
                        record_id=action.action_id,
                        customer_id=customer.customer_id,
                        as_of_date=action.due_date,
                        calculated_at=None,
                        unit="status",
                        currency=None,
                        hkd_equivalent=None,
                        excerpt=text,
                        risk_domain="credit",
                    )
                ],
                tags={"actions", "general"},
                customer_id=customer.customer_id,
            )
        )
    for ewi in session.scalars(select(EarlyWarning).where(EarlyWarning.customer_id == customer.customer_id)).all():
        if ewi.status != "open":
            continue
        text = (
            f"Early-warning indicator {ewi.indicator_code} is open. The threshold is {ewi.threshold} "
            f"and the observed value is {ewi.observed_value}."
        )
        atoms.append(
            _atom(
                metric_key=f"early_warning:{ewi.ewi_id}",
                as_of=ewi.triggered_on,
                value="open",
                text=text,
                claim_type="sourced_fact",
                citations=[
                    _db_citation(
                        source_system=ewi.source_system,
                        record_table="early_warning_indicators",
                        record_id=ewi.ewi_id,
                        customer_id=customer.customer_id,
                        as_of_date=ewi.triggered_on,
                        calculated_at=None,
                        unit="status",
                        currency=None,
                        hkd_equivalent=None,
                        excerpt=text,
                        risk_domain=ewi.domain,
                    )
                ],
                tags={"ewi", "general"},
                customer_id=customer.customer_id,
            )
        )
    watch = session.scalar(select(WatchlistEntry).where(WatchlistEntry.customer_id == customer.customer_id))
    if watch is not None:
        text = f"Watchlist status is {watch.status.replace('_', ' ')} as at {format_date(watch.since_date)}."
        atoms.append(
            _atom(
                metric_key="watchlist_status",
                as_of=watch.since_date,
                value=watch.status,
                text=text,
                claim_type="sourced_fact",
                citations=[
                    _db_citation(
                        source_system=watch.source_system,
                        record_table="watchlist_entries",
                        record_id=watch.entry_id,
                        customer_id=customer.customer_id,
                        as_of_date=watch.since_date,
                        calculated_at=None,
                        unit="status",
                        currency=None,
                        hkd_equivalent=None,
                        excerpt=text,
                        risk_domain="credit",
                    )
                ],
                tags={"watchlist", "general"},
                customer_id=customer.customer_id,
            )
        )
    covenant = session.scalar(
        select(CovenantObservation).where(CovenantObservation.customer_id == customer.customer_id)
    )
    if covenant is not None:
        text = (
            f"The interest coverage covenant status is {covenant.status} as at {format_date(covenant.as_of_date)}. "
            f"Actual value: {covenant.actual_value}."
        )
        atoms.append(
            _atom(
                metric_key="covenant_status",
                as_of=covenant.as_of_date,
                value=covenant.status,
                text=text,
                claim_type="sourced_fact",
                citations=[
                    _db_citation(
                        source_system=covenant.source_system,
                        record_table="covenant_observations",
                        record_id=covenant.observation_id,
                        customer_id=customer.customer_id,
                        as_of_date=covenant.as_of_date,
                        calculated_at=covenant.calculated_at,
                        unit="status",
                        currency=None,
                        hkd_equivalent=None,
                        excerpt=text,
                        risk_domain="credit",
                    )
                ],
                tags={"covenant", "general"},
                customer_id=customer.customer_id,
            )
        )
    if principal.can("aml.read"):
        for alert in session.scalars(select(Alert).where(Alert.customer_id == customer.customer_id)).all():
            text = alert.summary
            atoms.append(
                _atom(
                    metric_key=f"tm_alert:{alert.alert_id}",
                    as_of=alert.opened_on,
                    value=alert.status,
                    text=text,
                    claim_type="sourced_fact",
                    citations=[
                        _db_citation(
                            source_system=alert.source_system,
                            record_table="alerts",
                            record_id=alert.alert_id,
                            customer_id=customer.customer_id,
                            as_of_date=alert.opened_on,
                            calculated_at=None,
                            unit="status",
                            currency=None,
                            hkd_equivalent=None,
                            excerpt=text,
                            risk_domain=alert.domain,
                        )
                    ],
                    tags={"aml"},
                    customer_id=customer.customer_id,
                )
            )
    collateral = session.scalar(
        select(CollateralValuation).where(CollateralValuation.customer_id == customer.customer_id)
    )
    if collateral is not None:
        text = (
            f"Eligible collateral is {format_money(collateral.hkd_amount, 'HKD')} "
            f"as at {format_date(collateral.as_of_date)}."
        )
        atoms.append(
            _atom(
                metric_key="eligible_collateral",
                as_of=collateral.as_of_date,
                value=f"{collateral.hkd_amount:.2f}",
                text=text,
                claim_type="sourced_fact",
                citations=[
                    _db_citation(
                        source_system=collateral.source_system,
                        record_table="collateral_valuations",
                        record_id=collateral.valuation_id,
                        customer_id=customer.customer_id,
                        as_of_date=collateral.as_of_date,
                        calculated_at=collateral.calculated_at,
                        unit="HKD",
                        currency="HKD",
                        hkd_equivalent=f"{collateral.hkd_amount:.2f}",
                        excerpt=text,
                        risk_domain="collateral",
                    )
                ],
                tags={"collateral", "market"},
                customer_id=customer.customer_id,
            )
        )
    return atoms


def _calculation_atoms(session: Session, customer: Customer, snapshots: list[FacilitySnapshot]) -> list[dict]:
    atoms = []
    complete = [row for row in snapshots if row.data_quality == "ok" and row.hkd_drawn is not None]
    incomplete = [row for row in snapshots if row not in complete]
    if complete and not incomplete:
        total = sum_hkd(
            [(row.hkd_drawn or Decimal("0")) + (row.hkd_contingent or Decimal("0")) + (row.hkd_ccr or Decimal("0")) for row in complete]
        )
        undrawn = sum_hkd([row.hkd_undrawn or Decimal("0") for row in complete])
        drawn = sum_hkd([row.hkd_drawn or Decimal("0") for row in complete])
        text = (
            f"Demonstration total exposure is {format_money(total, 'HKD')} as at {format_date(complete[0].as_of_date)}. "
            f"Formula: total exposure = sum of HKD drawn + HKD contingent + HKD counterparty credit exposure. "
            f"Drawn exposure is {format_money(drawn, 'HKD')}. Undrawn commitments are {format_money(undrawn, 'HKD')} "
            "and are not included in that total. Notional amounts are not included."
        )
        atoms.append(
            _atom(
                metric_key="total_exposure",
                as_of=complete[0].as_of_date,
                value=f"{total:.2f}",
                text=text,
                claim_type="calculation",
                formula="total_exposure_hkd = sum(hkd_drawn + hkd_contingent + hkd_ccr); undrawn excluded; notionals excluded",
                citations=[_snapshot_citation(row, text, "HKD") for row in complete],
                tags={"exposure", "general"},
                customer_id=customer.customer_id,
                currency="HKD",
            )
        )
        collateral = session.scalar(
            select(CollateralValuation).where(CollateralValuation.customer_id == customer.customer_id)
        )
        if collateral is not None and drawn > 0:
            coverage = (collateral.hkd_amount / drawn).quantize(Decimal("0.01"))
            cover_text = (
                f"Collateral coverage is {coverage} calculated as eligible collateral "
                f"{format_money(collateral.hkd_amount, 'HKD')} divided by drawn exposure {format_money(drawn, 'HKD')}. "
                "Coverage above 1 does not eliminate credit, market or liquidity risk."
            )
            atoms.append(
                _atom(
                    metric_key="collateral_coverage",
                    as_of=collateral.as_of_date,
                    value=f"{coverage}",
                    text=cover_text,
                    claim_type="calculation",
                    formula="coverage = eligible_collateral_hkd / drawn_hkd",
                    citations=[
                        _snapshot_citation(complete[0], cover_text, "HKD"),
                        _db_citation(
                            source_system=collateral.source_system,
                            record_table="collateral_valuations",
                            record_id=collateral.valuation_id,
                            customer_id=customer.customer_id,
                            as_of_date=collateral.as_of_date,
                            calculated_at=collateral.calculated_at,
                            unit="HKD",
                            currency="HKD",
                            hkd_equivalent=f"{collateral.hkd_amount:.2f}",
                            excerpt=cover_text,
                            risk_domain="collateral",
                        ),
                    ],
                    tags={"collateral", "market", "general"},
                    customer_id=customer.customer_id,
                )
            )
        ratings = session.scalars(
            select(RatingHistory)
            .where(RatingHistory.customer_id == customer.customer_id)
            .order_by(RatingHistory.as_of_date)
        ).all()
        rating = ratings[-1].rating if ratings else None
        pd = probability_of_default(rating)
        lgd, lgd_formula = loss_given_default(coverage if collateral is not None and drawn > 0 else None)
        el, el_formula = expected_loss(pd, lgd, drawn, undrawn)
        if el is not None and ratings:
            el_text = (
                f"Demonstration expected loss is {format_money(el, 'HKD')}. {el_formula} {lgd_formula} "
                "This is not a regulatory capital measure and not an approved provision."
            )
            atoms.append(
                _atom(
                    metric_key="expected_loss",
                    as_of=ratings[-1].as_of_date,
                    value=f"{el:.2f}",
                    text=el_text,
                    claim_type="calculation",
                    formula=el_formula,
                    citations=[
                        _db_citation(
                            source_system=ratings[-1].source_system,
                            record_table="rating_history",
                            record_id=ratings[-1].rating_id,
                            customer_id=customer.customer_id,
                            as_of_date=ratings[-1].as_of_date,
                            calculated_at=ratings[-1].calculated_at,
                            unit="rating",
                            currency=None,
                            hkd_equivalent=None,
                            excerpt=el_text,
                            risk_domain="credit",
                        )
                    ],
                    tags={"rating"},
                    customer_id=customer.customer_id,
                    currency="HKD",
                )
            )
    elif incomplete:
        text = (
            "A demonstration total exposure was not completed because one or more facility records "
            "have unresolved source conflicts. Those records were not treated as zero."
        )
        atoms.append(
            _atom(
                metric_key="total_exposure",
                as_of=snapshots[0].as_of_date if snapshots else None,
                value=None,
                text=text,
                claim_type="missing",
                citations=[_snapshot_citation(row, text, "HKD") for row in incomplete],
                tags={"exposure", "limits", "general"},
                customer_id=customer.customer_id,
            )
        )
    score_atom = _score_atom(session, customer, snapshots)
    if score_atom is not None:
        atoms.append(score_atom)
    return atoms


def _score_atom(session: Session, customer: Customer, snapshots: list[FacilitySnapshot]) -> dict | None:
    ratings = session.scalars(
        select(RatingHistory)
        .where(RatingHistory.customer_id == customer.customer_id)
        .order_by(RatingHistory.as_of_date)
    ).all()
    utilisations = [row for row in snapshots if row.utilisation_pct is not None and row.data_quality == "ok"]
    worst = max(utilisations, key=lambda row: row.utilisation_pct or Decimal("0")) if utilisations else None
    covenant = session.scalar(
        select(CovenantObservation).where(CovenantObservation.customer_id == customer.customer_id)
    )
    ewis = session.scalars(
        select(EarlyWarning).where(EarlyWarning.customer_id == customer.customer_id, EarlyWarning.status == "open")
    ).all()
    liquidity = session.scalar(
        select(RiskMetric).where(
            RiskMetric.customer_id == customer.customer_id,
            RiskMetric.metric_key == "liquidity_ratio",
        ).order_by(RiskMetric.as_of_date.desc())
    )
    collateral = session.scalar(
        select(CollateralValuation).where(CollateralValuation.customer_id == customer.customer_id)
    )
    review = session.scalar(
        select(Review).where(
            Review.customer_id == customer.customer_id, Review.review_type == "annual_credit"
        )
    )
    watch = session.scalar(select(WatchlistEntry).where(WatchlistEntry.customer_id == customer.customer_id))
    drawn = None
    coverage = None
    complete = [row for row in snapshots if row.hkd_drawn is not None and row.data_quality == "ok"]
    if complete and all(row.hkd_drawn is not None for row in snapshots):
        drawn = sum_hkd([row.hkd_drawn for row in complete])
        if collateral and drawn > 0:
            coverage = (collateral.hkd_amount / drawn).quantize(Decimal("0.0001"))
    explanation = explain_score(
        ScoreInputs(
            rating=ratings[-1].rating if ratings else None,
            rating_record=ratings[-1].rating_id if ratings else None,
            rating_as_of=format_date(ratings[-1].as_of_date) if ratings else None,
            utilisation_pct=worst.utilisation_pct if worst else None,
            utilisation_record=worst.snapshot_id if worst else None,
            utilisation_as_of=format_date(worst.as_of_date) if worst else None,
            utilisation_quality="ok" if worst else "missing",
            covenant_status=covenant.status if covenant else None,
            covenant_record=covenant.observation_id if covenant else None,
            covenant_as_of=format_date(covenant.as_of_date) if covenant else None,
            open_ewi_count=len(ewis),
            ewi_record="early_warning_indicators",
            liquidity_ratio=liquidity.numeric_value if liquidity else None,
            liquidity_record=liquidity.metric_id if liquidity else None,
            liquidity_as_of=format_date(liquidity.as_of_date) if liquidity else None,
            collateral_coverage=coverage,
            collateral_record=collateral.valuation_id if collateral else None,
            collateral_as_of=format_date(collateral.as_of_date) if collateral else None,
            review_status=review.status if review else None,
            review_record=review.review_id if review else None,
            review_as_of=format_date(review.due_date) if review else None,
            watchlist_status=watch.status if watch else None,
            watchlist_record=watch.entry_id if watch else None,
        )
    )
    payload = explanation.as_dict()
    text = (
        f"Hackathon demonstration concern score is {payload['score']} "
        f"({payload['data_quality']}). {payload['formula']} "
        "This score was calculated by deterministic Python rules. It is not an internal credit rating."
    )
    citations = []
    if ratings:
        citations.append(
            _db_citation(
                source_system=ratings[-1].source_system,
                record_table="rating_history",
                record_id=ratings[-1].rating_id,
                customer_id=customer.customer_id,
                as_of_date=ratings[-1].as_of_date,
                calculated_at=ratings[-1].calculated_at,
                unit="rating",
                currency=None,
                hkd_equivalent=None,
                excerpt=text,
                risk_domain="model",
            )
        )
    if not citations:
        return None
    return _atom(
        metric_key="concern_score",
        as_of=ratings[-1].as_of_date if ratings else None,
        value=payload["score"],
        text=text,
        claim_type="calculation",
        formula=payload["formula"],
        citations=citations,
        tags={"rating", "general"},
        customer_id=customer.customer_id,
        extra={"score_explanation": payload},
    )


def _atom(**kwargs) -> dict:
    citations = kwargs.pop("citations")
    tags = kwargs.pop("tags")
    extra = kwargs.pop("extra", {})
    return {
        "claim_id": f"CLM-{_citation_id()}",
        "customer_id": kwargs.get("customer_id"),
        "text": kwargs["text"],
        "claim_type": kwargs["claim_type"],
        "metric_key": kwargs["metric_key"],
        "value": kwargs.get("value"),
        "unit": kwargs.get("unit"),
        "currency": kwargs.get("currency"),
        "as_of_date": kwargs.get("as_of"),
        "citations": citations,
        "stale": kwargs.get("stale", False),
        "formula": kwargs.get("formula"),
        "tags": sorted(tags),
        **extra,
    }


def _fold(atoms: list[dict]) -> list[dict]:
    grouped: dict[tuple, list[tuple]] = {}
    passthrough = []
    for atom in atoms:
        comparable = _comparable(atom["metric_key"], None if atom["value"] is None else str(atom["value"]))
        if comparable is None or atom["claim_type"] in {"missing", "calculation", "rule"}:
            passthrough.append(atom)
            continue
        grouped.setdefault((atom["metric_key"], atom["as_of_date"]), []).append((comparable, atom))
    claims = []
    for (metric_key, as_of), items in grouped.items():
        values = {item[0] for item in items}
        if len(values) == 1:
            primary = items[0][1]
            citations = []
            seen = set()
            for _, atom in items:
                for citation in atom["citations"]:
                    key = (
                        citation.get("document_id"),
                        citation.get("record_id"),
                        citation.get("page"),
                        citation.get("sheet"),
                    )
                    if key not in seen:
                        seen.add(key)
                        citations.append(citation)
            merged = dict(primary)
            merged["citations"] = citations
            claims.append(merged)
        else:
            parts = []
            citations = []
            for comparable, atom in items:
                parts.append(f"{comparable} ({atom['text']})")
                citations.extend(atom["citations"])
            claims.append(
                {
                    "claim_id": f"CLM-{_citation_id()}",
                    "customer_id": items[0][1]["customer_id"],
                    "text": (
                        f"Current trusted sources disagree on {metric_key} as at {format_date(as_of)}. "
                        "No single figure is adopted. "
                        + " | ".join(parts)
                    ),
                    "claim_type": "contradiction",
                    "metric_key": metric_key,
                    "value": None,
                    "unit": items[0][1].get("unit"),
                    "currency": items[0][1].get("currency"),
                    "as_of_date": as_of,
                    "citations": citations,
                    "stale": False,
                    "formula": None,
                    "tags": sorted(set(items[0][1]["tags"]) | {"limits", "exposure"}),
                }
            )
    claims.extend(passthrough)
    return claims


def select_claims(claims: list[dict], intents: set[str]) -> list[dict]:
    if not intents or "general" in intents or "risk_overview" in intents:
        wanted = {"general", "exposure", "rating", "limits", "review", "ewi", "covenant", "watchlist", "relationship"}
        if "aml" in intents:
            wanted.add("aml")
        if "liquidity" in intents:
            wanted.add("liquidity")
        if "market" in intents:
            wanted.add("market")
        if "collateral" in intents:
            wanted.add("collateral")
        if "change" in intents:
            wanted.add("change")
        if "actions" in intents:
            wanted.add("actions")
    else:
        wanted = set(intents)
        if "relationship" in wanted:
            wanted.update({"facilities", "exposure", "relationship"})
    selected = [claim for claim in claims if wanted & set(claim["tags"])]
    # Contradictions are always material to the metrics they describe.
    for claim in claims:
        if claim["claim_type"] == "contradiction" and claim not in selected:
            if wanted & set(claim["tags"]):
                selected.append(claim)
    return selected
