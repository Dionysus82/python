"""Authorised structured analytics. Queries run only after the portfolio scope is known."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.service import write_audit
from app.authorisation.service import (
    allowed_customer_ids,
    deny,
    require_permission,
    visible_document_ids,
)
from app.config import load_json
from app.domain.banner import AML_CONTROL_NOTICE, AML_RESTRICTION, SYNTHETIC_BANNER
from app.domain.dates import demo_today, format_date
from app.domain.errors import AccessDeniedError
from app.domain.money import format_money, sum_hkd
from app.domain.risk_calculation import explain_score
from app.models import tables as models
from app.rag.claims import build_customer_claims
from app.security.passwords import verify_password
from app.security.principal import Principal, load_principal
from app.security.tokens import issue_token

SCORE = load_json("risk_score.json")
FRESH = load_json("freshness.json")
ZERO = Decimal("0")


def authenticate(session: Session, username: str, password: str) -> dict:
    user = session.scalar(select(models.User).where(models.User.username == username))
    if user is None or not user.active or not verify_password(password, user.password_hash):
        write_audit(
            session,
            event_type="login",
            outcome="denied",
            detail="Synthetic sign-in failed.",
            username=username,
        )
        raise AccessDeniedError("The username or password was not recognised.")
    principal = load_principal(session, username)
    assert principal is not None
    write_audit(session, event_type="login", outcome="ok", detail="Synthetic sign-in.", principal=principal)
    return {
        "token": issue_token(username),
        "username": principal.username,
        "display_name": principal.display_name,
        "role": principal.role,
        "role_label": principal.role_label,
        "line": principal.line,
        "permissions": sorted(principal.permissions),
        "portfolio_ids": sorted(principal.portfolio_ids),
        "read_only": principal.read_only,
        "banner": SYNTHETIC_BANNER,
    }


def _scope(session: Session, principal: Principal, permission: str) -> set[str]:
    require_permission(principal, permission)
    return allowed_customer_ids(session, principal)


def _guard_customer(session: Session, principal: Principal, customer_id: str, correlation_id: str) -> None:
    allowed = allowed_customer_ids(session, principal)
    if customer_id not in allowed:
        deny(
            session,
            principal,
            customer_id=customer_id,
            detail="Customer record blocked before content was read.",
            correlation_id=correlation_id,
        )


def _latest_date(session: Session, customer_id: str) -> date | None:
    return session.scalar(
        select(func.max(models.FacilitySnapshot.as_of_date)).where(
            models.FacilitySnapshot.customer_id == customer_id
        )
    )


def _latest_rows(session: Session, customer_id: str) -> list[models.FacilitySnapshot]:
    as_of = _latest_date(session, customer_id)
    if as_of is None:
        return []
    return list(
        session.scalars(
            select(models.FacilitySnapshot).where(
                models.FacilitySnapshot.customer_id == customer_id,
                models.FacilitySnapshot.as_of_date == as_of,
            )
        ).all()
    )


def _position(rows: list[models.FacilitySnapshot]) -> dict:
    usable = [row for row in rows if row.data_quality == "ok" and row.hkd_drawn is not None]
    excluded = [row.facility_id for row in rows if row not in usable]
    drawn = sum_hkd([row.hkd_drawn for row in usable]) if usable else None
    undrawn = sum_hkd([row.hkd_undrawn for row in usable]) if usable and all(row.hkd_undrawn is not None for row in usable) else None
    contingent = sum_hkd([row.hkd_contingent or ZERO for row in usable]) if usable else None
    ccr = sum_hkd([row.hkd_ccr or ZERO for row in usable]) if usable else None
    committed = sum_hkd([row.hkd_committed for row in usable]) if usable and all(row.hkd_committed is not None for row in usable) else None
    utilisation = None
    if drawn is not None and committed not in (None, ZERO):
        utilisation = (drawn / committed * Decimal("100")).quantize(Decimal("0.01"))
    total = None
    if drawn is not None:
        total = drawn + (contingent or ZERO) + (ccr or ZERO)
    currencies = sorted({row.currency for row in rows})
    return {
        "as_of_date": rows[0].as_of_date if rows else None,
        "drawn_hkd": drawn,
        "undrawn_hkd": undrawn,
        "contingent_hkd": contingent,
        "ccr_hkd": ccr,
        "committed_hkd": committed,
        "total_exposure_hkd": total,
        "utilisation_pct": utilisation,
        "currencies": currencies,
        "excluded_facilities": excluded,
        "fx_source": rows[0].fx_source if rows else None,
        "fx_method": rows[0].fx_method if rows else None,
        "source_system": rows[0].source_system if rows else None,
        "calculated_at": rows[0].calculated_at if rows else None,
        "data_quality": "incomplete" if excluded else "ok",
    }


def _ratings(session: Session, customer_id: str) -> list[models.RatingHistory]:
    return list(
        session.scalars(
            select(models.RatingHistory)
            .where(models.RatingHistory.customer_id == customer_id)
            .order_by(models.RatingHistory.as_of_date)
        ).all()
    )


def _trend(ratings: list[models.RatingHistory]) -> str:
    if len(ratings) < 2:
        return "Insufficient history"
    delta = ratings[-1].rating - ratings[0].rating
    notches = int(SCORE["deterioration_notches"])
    if delta >= notches:
        return f"Deteriorating ({ratings[0].rating} to {ratings[-1].rating})"
    if delta <= -1:
        return f"Improving ({ratings[0].rating} to {ratings[-1].rating})"
    if delta > 0:
        return f"Slightly deteriorating ({ratings[0].rating} to {ratings[-1].rating})"
    return f"Stable ({ratings[-1].rating})"


def _mask_aml(principal: Principal, value: str) -> str:
    return value if principal.can("aml.read") else "Restricted"


def search_customers(session: Session, principal: Principal, filters: dict) -> list[dict]:
    allowed = _scope(session, principal, "customer.search")
    correlation_id = uuid.uuid4().hex
    statement = select(models.Customer).where(models.Customer.customer_id.in_(allowed or {""}))
    text = (filters.get("q") or "").strip().casefold()
    rows = session.scalars(statement.order_by(models.Customer.legal_name)).all()
    visible = visible_document_ids(session, principal, allowed)
    results = []
    for customer in rows:
        if not _matches(session, customer, filters, text, principal):
            continue
        ratings = _ratings(session, customer.customer_id)
        position = _position(_latest_rows(session, customer.customer_id))
        reviews = session.scalars(
            select(models.Review).where(
                models.Review.customer_id == customer.customer_id,
                models.Review.review_type == "annual_credit",
            )
        ).all()
        latest_review = max(reviews, key=lambda item: item.due_date) if reviews else None
        doc_ids = set(
            session.scalars(
                select(models.DocumentCustomer.document_id).where(
                    models.DocumentCustomer.customer_id == customer.customer_id
                )
            ).all()
        )
        results.append(
            {
                "legal_name": customer.legal_name,
                "customer_id": customer.customer_id,
                "group_id": customer.group_id,
                "industry": customer.industry,
                "jurisdiction": customer.jurisdiction,
                "relationship_manager": customer.relationship_manager,
                "internal_credit_rating": ratings[-1].rating if ratings else None,
                "aml_risk_classification": _mask_aml(principal, customer.aml_risk_classification),
                "total_exposure_hkd": position["total_exposure_hkd"],
                "undrawn_commitment_hkd": position["undrawn_hkd"],
                "limit_utilisation_pct": position["utilisation_pct"],
                "risk_trend": _trend(ratings),
                "watchlist_status": customer.watchlist_status,
                "data_freshness": _freshness_label(customer.data_freshness_date),
                "trusted_document_count": len(doc_ids & visible),
                "latest_review_date": latest_review.completed_date if latest_review and latest_review.completed_date else None,
                "latest_review_status": latest_review.status if latest_review else "missing",
                "data_quality": position["data_quality"],
                "as_of_date": position["as_of_date"],
                "currency": "HKD",
                "unit": "HKD",
                "source_system": position["source_system"],
                "calculation_basis": "Sum of stored HKD equivalents for facilities with data quality ok. Unresolved facilities are excluded, not treated as zero.",
            }
        )
    write_audit(
        session,
        event_type="customer_search",
        outcome="ok",
        detail=f"Search returned {len(results)} authorised customers.",
        principal=principal,
        correlation_id=correlation_id,
        aml_access=principal.can("aml.read") and bool(filters.get("aml_risk_classification")),
    )
    return results


def _matches(session: Session, customer: models.Customer, filters: dict, text: str, principal: Principal) -> bool:
    if filters.get("customer_id") and filters["customer_id"] != customer.customer_id:
        return False
    if filters.get("group_id") and filters["group_id"].casefold() not in customer.group_id.casefold():
        return False
    if filters.get("industry") and filters["industry"].casefold() not in customer.industry.casefold():
        return False
    if filters.get("jurisdiction") and filters["jurisdiction"].casefold() not in customer.jurisdiction.casefold():
        return False
    if filters.get("place_of_incorporation") and filters["place_of_incorporation"].casefold() not in customer.place_of_incorporation.casefold():
        return False
    if filters.get("relationship_manager") and filters["relationship_manager"].casefold() not in customer.relationship_manager.casefold():
        return False
    if filters.get("customer_risk_classification") and filters["customer_risk_classification"] != customer.customer_risk_classification:
        return False
    if filters.get("watchlist_status") and filters["watchlist_status"] != customer.watchlist_status:
        return False
    if filters.get("aml_risk_classification"):
        if not principal.can("aml.read"):
            return False
        if filters["aml_risk_classification"] != customer.aml_risk_classification:
            return False
    ratings = _ratings(session, customer.customer_id)
    if filters.get("internal_risk_rating") and (not ratings or str(ratings[-1].rating) != str(filters["internal_risk_rating"])):
        return False
    if filters.get("facility_type") or filters.get("product") or filters.get("limit_status"):
        facilities = session.scalars(select(models.Facility).where(models.Facility.customer_id == customer.customer_id)).all()
        if filters.get("facility_type") and not any(filters["facility_type"] == item.facility_type for item in facilities):
            return False
        if filters.get("product") and not any(filters["product"].casefold() in item.product_code.casefold() or filters["product"].casefold() in item.name.casefold() for item in facilities):
            return False
        if filters.get("limit_status"):
            rows = _latest_rows(session, customer.customer_id)
            if not any(_limit_word(row) == filters["limit_status"] for row in rows):
                return False
    if filters.get("early_warning") in {"open", "triggered"}:
        count = session.scalar(
            select(func.count()).select_from(models.EarlyWarning).where(
                models.EarlyWarning.customer_id == customer.customer_id,
                models.EarlyWarning.status == "open",
            )
        )
        if not count:
            return False
    if text:
        group = session.get(models.CustomerGroup, customer.group_id)
        haystack = " ".join(
            [
                customer.legal_name,
                customer.customer_id,
                customer.group_id,
                group.name if group else "",
                customer.industry,
                customer.jurisdiction,
                customer.place_of_incorporation,
                customer.relationship_manager,
                customer.business_summary,
                customer.watchlist_status,
                customer.customer_risk_classification,
            ]
        ).casefold()
        if text not in haystack and not all(part in haystack for part in text.split()):
            return False
    return True


def _limit_word(row: models.FacilitySnapshot) -> str:
    if row.data_quality != "ok" or row.utilisation_pct is None:
        return "unresolved"
    if row.utilisation_pct > Decimal(str(SCORE["breach_utilisation_pct"])):
        return "breach"
    if row.utilisation_pct >= Decimal(str(SCORE["near_breach_utilisation_pct"])):
        return "near_breach"
    return "within_limit"


def _freshness_label(as_of: date | None) -> str:
    if as_of is None:
        return "Missing as-of date"
    age = (demo_today() - as_of).days
    limit = int(FRESH["metric_days"])
    if age <= limit:
        return f"Current ({format_date(as_of)}, {age} days)"
    return f"Stale ({format_date(as_of)}, {age} days)"


def customer_360(session: Session, principal: Principal, customer_id: str) -> dict:
    allowed = _scope(session, principal, "customer.read")
    correlation_id = uuid.uuid4().hex
    if customer_id not in allowed:
        deny(session, principal, customer_id=customer_id, detail="Customer 360 blocked before retrieval.", correlation_id=correlation_id)
    customer = session.get(models.Customer, customer_id)
    if customer is None:
        deny(session, principal, customer_id=customer_id, detail="Customer 360 blocked before retrieval.", correlation_id=correlation_id)
    group = session.get(models.CustomerGroup, customer.group_id)
    owner_rows = session.scalars(select(models.BeneficialOwner).where(models.BeneficialOwner.customer_id == customer_id)).all()
    owners: list[dict]
    if not principal.can("aml.read"):
        owners = [
            {
                "name": "Restricted",
                "ownership_pct": "Restricted",
                "pep_indicator": "Restricted",
                "fictional_notice": owner.fictional_notice,
            }
            for owner in owner_rows
        ]
    else:
        owners = [
            {
                "name": owner.name,
                "ownership_pct": owner.ownership_pct,
                "pep_indicator": owner.pep_indicator,
                "fictional_notice": owner.fictional_notice,
            }
            for owner in owner_rows
        ]
    members = session.scalars(select(models.Customer).where(models.Customer.group_id == customer.group_id)).all()
    visible_members = [
        {"customer_id": member.customer_id, "legal_name": member.legal_name, "in_portfolio": member.customer_id in allowed}
        for member in members
    ]
    products = session.execute(
        select(models.Product.product_code, models.Product.name, models.Product.category)
        .join(models.CustomerProduct, models.CustomerProduct.product_code == models.Product.product_code)
        .where(models.CustomerProduct.customer_id == customer_id)
    ).all()
    facilities = _facility_rows(session, customer_id)
    position = _position(_latest_rows(session, customer_id))
    ratings = _ratings(session, customer_id)
    metrics = _metric_histories(session, customer_id, principal)
    collateral = _collateral(session, customer_id)
    covenants = _covenants(session, customer_id)
    ewis = session.scalars(select(models.EarlyWarning).where(models.EarlyWarning.customer_id == customer_id)).all()
    actions = session.scalars(select(models.ManagementAction).where(models.ManagementAction.customer_id == customer_id)).all()
    reviews = session.scalars(select(models.Review).where(models.Review.customer_id == customer_id)).all()
    events = session.scalars(select(models.RiskEvent).where(models.RiskEvent.customer_id == customer_id)).all()
    legal = session.scalars(select(models.LegalMatter).where(models.LegalMatter.customer_id == customer_id)).all()
    qualitative = session.scalars(
        select(models.QualitativeAssessment).where(models.QualitativeAssessment.customer_id == customer_id)
    ).all()
    alerts: list[models.Alert] = []
    if principal.can("aml.read"):
        alerts = list(session.scalars(select(models.Alert).where(models.Alert.customer_id == customer_id)).all())
    visible = visible_document_ids(session, principal, allowed)
    documents = _customer_documents(session, customer_id, visible)
    issues = session.scalars(
        select(models.DataQualityIssue).where(models.DataQualityIssue.customer_id == customer_id)
    ).all()
    claims = build_customer_claims(session, principal, customer_id, visible, historical=False)
    score = next((claim.get("score_explanation") for claim in claims if claim.get("score_explanation")), None)
    if score is None:
        score = explain_score(_empty_inputs()).as_dict()
    write_audit(
        session,
        event_type="customer_view",
        outcome="ok",
        detail="Customer 360 viewed.",
        principal=principal,
        customer_id=customer_id,
        correlation_id=correlation_id,
        aml_access=principal.can("aml.read"),
    )
    return {
        "banner": SYNTHETIC_BANNER,
        "profile": {
            "customer_id": customer.customer_id,
            "legal_name": customer.legal_name,
            "synthetic_lei": customer.synthetic_lei,
            "group_id": customer.group_id,
            "group_name": group.name if group else None,
            "industry": customer.industry,
            "jurisdiction": customer.jurisdiction,
            "place_of_incorporation": customer.place_of_incorporation,
            "relationship_manager": customer.relationship_manager,
            "onboarding_status": customer.onboarding_status,
            "customer_risk_classification": customer.customer_risk_classification,
            "aml_risk_classification": _mask_aml(principal, customer.aml_risk_classification),
            "watchlist_status": customer.watchlist_status,
            "business_summary": customer.business_summary,
            "registered_address": customer.registered_address,
            "incorporation_date": customer.incorporation_date,
            "data_freshness": _freshness_label(customer.data_freshness_date),
            "profile": customer.profile,
        },
        "beneficial_owners": owners,
        "group_members": visible_members,
        "products": [{"code": code, "name": name, "category": category} for code, name, category in products],
        "facilities": facilities,
        "position": position,
        "ratings": [
            {
                "as_of_date": row.as_of_date,
                "rating": row.rating,
                "probability_of_default": row.probability_of_default,
                "source_system": row.source_system,
                "unit": "rating notch",
                "currency": "n/a",
                "calculation_basis": row.scale_note,
                "data_quality": "ok",
                "calculated_at": row.calculated_at,
            }
            for row in ratings
        ],
        "risk_trend": _trend(ratings),
        "histories": metrics,
        "collateral": collateral,
        "covenants": covenants,
        "early_warnings": [_ewi(row) for row in ewis],
        "actions": [_action(row) for row in actions],
        "reviews": [_review(row) for row in reviews],
        "events": [_event(row) for row in events if principal.can("aml.read") or row.sensitivity != "aml"],
        "legal_matters": [_legal(row) for row in legal],
        "qualitative": [
            {
                "domain": row.domain,
                "severity": row.severity,
                "statement": row.statement if principal.can("aml.read") or row.sensitivity != "aml" else AML_RESTRICTION,
                "as_of_date": row.as_of_date,
                "source_system": row.source_system,
                "data_quality": row.data_quality,
            }
            for row in qualitative
        ],
        "alerts": [_alert(row) for row in alerts],
        "aml_notice": AML_CONTROL_NOTICE if principal.can("aml.read") else AML_RESTRICTION,
        "documents": documents,
        "data_quality_issues": [_issue(row) for row in issues],
        "concern_score": score,
        "consolidated_assessment": _assessment_lines(claims),
    }


def _empty_inputs():
    from app.domain.risk_calculation import ScoreInputs

    return ScoreInputs()


def _assessment_lines(claims: list[dict]) -> list[dict]:
    kept = []
    for claim in claims:
        if claim["claim_type"] == "calculation" and claim["metric_key"] in {"total_exposure", "concern_score", "expected_loss", "collateral_coverage"}:
            kept.append({"type": claim["claim_type"], "text": claim["text"], "metric_key": claim["metric_key"]})
        elif claim["claim_type"] in {"contradiction", "missing", "rule"}:
            kept.append({"type": claim["claim_type"], "text": claim["text"], "metric_key": claim["metric_key"]})
    return kept


def _facility_rows(session: Session, customer_id: str) -> list[dict]:
    facilities = {
        row.facility_id: row
        for row in session.scalars(select(models.Facility).where(models.Facility.customer_id == customer_id)).all()
    }
    rows = []
    for snapshot in _latest_rows(session, customer_id):
        facility = facilities.get(snapshot.facility_id)
        rows.append(
            {
                "facility_id": snapshot.facility_id,
                "name": facility.name if facility else snapshot.facility_id,
                "facility_type": facility.facility_type if facility else None,
                "product_code": facility.product_code if facility else None,
                "currency": snapshot.currency,
                "committed_limit": snapshot.committed_limit,
                "drawn": snapshot.drawn,
                "undrawn": snapshot.undrawn,
                "contingent": snapshot.contingent,
                "counterparty_credit_exposure": snapshot.ccr,
                "notional": snapshot.notional,
                "hkd_committed": snapshot.hkd_committed,
                "hkd_drawn": snapshot.hkd_drawn,
                "hkd_undrawn": snapshot.hkd_undrawn,
                "hkd_contingent": snapshot.hkd_contingent,
                "hkd_ccr": snapshot.hkd_ccr,
                "utilisation_pct": snapshot.utilisation_pct,
                "limit_status": _limit_word(snapshot),
                "fx_rate": snapshot.fx_rate,
                "fx_rate_date": snapshot.fx_rate_date,
                "fx_source": snapshot.fx_source,
                "fx_method": snapshot.fx_method,
                "as_of_date": snapshot.as_of_date,
                "data_quality": snapshot.data_quality,
                "source_system": snapshot.source_system,
                "calculated_at": snapshot.calculated_at,
                "calculation_basis": "HKD equivalent = original amount × stored demonstration mid-rate. Notional is shown separately and is not added to exposure.",
                "unit": snapshot.currency,
            }
        )
    return rows


def _metric_histories(session: Session, customer_id: str, principal: Principal) -> dict:
    charts: dict[str, list] = {
        "drawn_exposure": [],
        "utilisation_pct": [],
        "deposits": [],
        "liquidity_ratio": [],
        "cash_reserves": [],
        "internal_rating": [],
    }
    snapshots = session.scalars(
        select(models.FacilitySnapshot)
        .where(models.FacilitySnapshot.customer_id == customer_id)
        .order_by(models.FacilitySnapshot.as_of_date)
    ).all()
    by_date: dict[date, list] = defaultdict(list)
    for row in snapshots:
        by_date[row.as_of_date].append(row)
    for as_of, rows in by_date.items():
        usable = [row for row in rows if row.hkd_drawn is not None and row.data_quality == "ok"]
        drawn_total = sum_hkd([row.hkd_drawn for row in usable]) if usable else None
        utilisation = None
        if usable and all(row.hkd_committed not in (None, ZERO) for row in usable) and drawn_total is not None:
            committed_total = sum_hkd([row.hkd_committed for row in usable])
            if committed_total not in (None, ZERO):
                utilisation = (drawn_total / committed_total * Decimal("100")).quantize(Decimal("0.01"))
        charts["drawn_exposure"].append(
            {
                "as_of_date": as_of,
                "value": drawn_total,
                "source_system": rows[0].source_system,
                "currency": "HKD",
                "unit": "HKD",
                "calculation_basis": "Sum of stored HKD drawn amounts with data quality ok.",
                "data_quality": "ok" if len(usable) == len(rows) else "incomplete",
            }
        )
        charts["utilisation_pct"].append(
            {
                "as_of_date": as_of,
                "value": utilisation,
                "source_system": rows[0].source_system,
                "currency": "n/a",
                "unit": "percent",
                "calculation_basis": "Sum of stored HKD drawn amounts divided by sum of stored HKD committed limits, for facilities with data quality ok.",
                "data_quality": "ok" if utilisation is not None else "incomplete",
            }
        )
    deposits = session.scalars(
        select(models.DepositBalance)
        .where(models.DepositBalance.customer_id == customer_id)
        .order_by(models.DepositBalance.as_of_date)
    ).all()
    for balance in deposits:
        charts["deposits"].append(
            {
                "as_of_date": balance.as_of_date,
                "value": balance.hkd_amount,
                "source_system": balance.source_system,
                "currency": "HKD",
                "unit": "HKD",
                "calculation_basis": f"{format_money(balance.amount, balance.currency)} × {balance.fx_rate} ({balance.fx_method})",
                "data_quality": "ok",
            }
        )
    metrics = session.scalars(
        select(models.RiskMetric)
        .where(models.RiskMetric.customer_id == customer_id)
        .order_by(models.RiskMetric.as_of_date)
    ).all()
    for metric in metrics:
        if metric.sensitivity == "aml" and not principal.can("aml.read"):
            continue
        target = charts.get(metric.metric_key)
        if target is None:
            charts.setdefault(metric.metric_key, [])
            target = charts[metric.metric_key]
        target.append(
            {
                "as_of_date": metric.as_of_date,
                "value": metric.numeric_value,
                "source_system": metric.source_system,
                "currency": metric.currency or "n/a",
                "unit": metric.unit,
                "calculation_basis": metric.calculation_basis,
                "data_quality": metric.data_quality,
            }
        )
    for rating in _ratings(session, customer_id):
        charts["internal_rating"].append(
            {
                "as_of_date": rating.as_of_date,
                "value": rating.rating,
                "source_system": rating.source_system,
                "currency": "n/a",
                "unit": "rating notch",
                "calculation_basis": rating.scale_note,
                "data_quality": "ok",
            }
        )
    return charts


def _collateral(session: Session, customer_id: str) -> list[dict]:
    items = {
        row.collateral_id: row
        for row in session.scalars(select(models.CollateralItem).where(models.CollateralItem.customer_id == customer_id)).all()
    }
    valuations = session.scalars(
        select(models.CollateralValuation).where(models.CollateralValuation.customer_id == customer_id)
    ).all()
    payload = []
    for row in valuations:
        item = items.get(row.collateral_id)
        payload.append(
            {
                "collateral_id": row.collateral_id,
                "type": item.collateral_type if item else None,
                "description": item.description if item else None,
                "eligible": row.eligible,
                "amount": row.amount,
                "currency": row.currency,
                "hkd_amount": row.hkd_amount,
                "fx_rate": row.fx_rate,
                "fx_rate_date": row.fx_rate_date,
                "fx_source": row.fx_source,
                "fx_method": row.fx_method,
                "as_of_date": row.as_of_date,
                "source_system": row.source_system,
                "calculated_at": row.calculated_at,
                "data_quality": "ok",
                "unit": row.currency,
                "calculation_basis": "Eligible collateral is a mitigant. It is not deducted from exposure and it does not eliminate risk.",
            }
        )
    return payload


def _covenants(session: Session, customer_id: str) -> list[dict]:
    covenants = {
        row.covenant_id: row
        for row in session.scalars(select(models.Covenant).where(models.Covenant.customer_id == customer_id)).all()
    }
    observations = session.scalars(
        select(models.CovenantObservation).where(models.CovenantObservation.customer_id == customer_id)
    ).all()
    payload = []
    for row in observations:
        covenant = covenants.get(row.covenant_id)
        payload.append(
            {
                "covenant_id": row.covenant_id,
                "name": covenant.name if covenant else row.covenant_id,
                "operator": covenant.operator if covenant else None,
                "threshold": covenant.threshold if covenant else None,
                "actual_value": row.actual_value,
                "unit": covenant.unit if covenant else None,
                "status": row.status,
                "as_of_date": row.as_of_date,
                "source_system": row.source_system,
                "data_quality": row.data_quality,
                "calculated_at": row.calculated_at,
                "currency": "n/a",
                "calculation_basis": "Status is the value stored by the covenant monitor. A missing actual is not treated as met.",
            }
        )
    return payload


def _ewi(row: models.EarlyWarning) -> dict:
    return {
        "ewi_id": row.ewi_id,
        "code": row.indicator_code,
        "description": row.description,
        "triggered_on": row.triggered_on,
        "status": row.status,
        "threshold": row.threshold,
        "observed_value": row.observed_value,
        "domain": row.domain,
        "source_system": row.source_system,
    }


def _action(row: models.ManagementAction) -> dict:
    overdue = row.status == "open" and row.due_date < demo_today()
    return {
        "action_id": row.action_id,
        "description": row.description,
        "owner_function": row.owner_function,
        "due_date": row.due_date,
        "status": "overdue" if overdue and row.status == "open" else row.status,
        "source_system": row.source_system,
    }


def _review(row: models.Review) -> dict:
    return {
        "review_id": row.review_id,
        "review_type": row.review_type,
        "due_date": row.due_date,
        "completed_date": row.completed_date,
        "status": row.status,
        "source_system": row.source_system,
        "sensitivity": row.sensitivity,
    }


def _event(row: models.RiskEvent) -> dict:
    return {
        "event_id": row.event_id,
        "domain": row.domain,
        "event_date": row.event_date,
        "severity": row.severity,
        "summary": row.summary,
        "status": row.status,
        "source_system": row.source_system,
    }


def _legal(row: models.LegalMatter) -> dict:
    return {
        "matter_id": row.matter_id,
        "summary": row.summary,
        "status": row.status,
        "as_of_date": row.as_of_date,
        "source_system": row.source_system,
    }


def _alert(row: models.Alert) -> dict:
    return {
        "alert_id": row.alert_id,
        "domain": row.domain,
        "alert_type": row.alert_type,
        "severity": row.severity,
        "status": row.status,
        "summary": row.summary,
        "opened_on": row.opened_on,
        "human_review_required": row.human_review_required,
        "source_system": row.source_system,
        "notice": AML_CONTROL_NOTICE,
    }


def _issue(row: models.DataQualityIssue) -> dict:
    return {
        "issue_id": row.issue_id,
        "issue_type": row.issue_type,
        "severity": row.severity,
        "summary": row.summary,
        "as_of_date": row.as_of_date,
        "status": row.status,
        "document_id": row.document_id,
    }


def _customer_documents(session: Session, customer_id: str, visible: set[str]) -> list[dict]:
    ids = session.scalars(
        select(models.DocumentCustomer.document_id).where(models.DocumentCustomer.customer_id == customer_id)
    ).all()
    documents = session.scalars(
        select(models.Document).where(models.Document.document_id.in_(set(ids) & visible or {""}))
    ).all()
    return [_document_summary(row) for row in sorted(documents, key=lambda item: item.reporting_date, reverse=True)]


def _document_summary(row: models.Document) -> dict:
    age = (demo_today() - row.reporting_date).days
    threshold = _document_threshold(row.document_type)
    return {
        "document_id": row.document_id,
        "title": row.title,
        "document_type": row.document_type,
        "original_filename": row.original_filename,
        "risk_domain": row.risk_domain,
        "reporting_date": row.reporting_date,
        "version": row.version,
        "superseded": row.superseded,
        "authoring_function": row.authoring_function,
        "confidentiality": row.confidentiality,
        "ingestion_status": row.ingestion_status,
        "freshness": "Stale" if age > threshold else "Current",
        "age_days": age,
        "viewer_route": f"/source?document_id={row.document_id}",
        "prompt_injection_suspected": row.prompt_injection_suspected,
        "incomplete": row.incomplete,
    }


def _document_threshold(document_type: str) -> int:
    mapping = {
        "annual_credit_review": FRESH["credit_review_days"],
        "interim_credit_review": FRESH["interim_review_days"],
        "liquidity_assessment": FRESH["liquidity_assessment_days"],
        "aml_periodic_review": FRESH["aml_periodic_review_days"],
        "market_risk_report": FRESH["market_report_days"],
        "cdd_summary": FRESH["cdd_days"],
    }
    return int(mapping.get(document_type, FRESH["default_document_days"]))


def group_360(session: Session, principal: Principal, group_id: str) -> dict:
    allowed = _scope(session, principal, "customer.read")
    group = session.scalar(select(models.CustomerGroup).where(models.CustomerGroup.group_id == group_id))
    if group is None:
        name_match = session.scalars(select(models.CustomerGroup)).all()
        group = next((item for item in name_match if item.name.casefold() == group_id.casefold()), None)
    if group is None:
        deny(session, principal, customer_id=None, detail="Group was not resolved inside the authorised book.", correlation_id=uuid.uuid4().hex)
    members = session.scalars(select(models.Customer).where(models.Customer.group_id == group.group_id)).all()
    visible = [member for member in members if member.customer_id in allowed]
    if not visible:
        deny(
            session,
            principal,
            customer_id=members[0].customer_id if members else None,
            detail="Group has no entity in the authorised portfolio.",
            correlation_id=uuid.uuid4().hex,
        )
    entities: list[dict] = []
    by_currency: dict[str, Decimal] = defaultdict(lambda: ZERO)
    hkd_parts = []
    for member in visible:
        rows = _latest_rows(session, member.customer_id)
        position = _position(rows)
        for row in rows:
            if row.data_quality == "ok" and row.drawn is not None:
                by_currency[row.currency] += row.drawn
        if position["drawn_hkd"] is not None:
            hkd_parts.append(position["drawn_hkd"])
        entities.append(
            {
                "customer_id": member.customer_id,
                "legal_name": member.legal_name,
                "jurisdiction": member.jurisdiction,
                "portfolio_id": member.portfolio_id,
                "position": position,
                "facilities": _facility_rows(session, member.customer_id),
            }
        )
    write_audit(
        session,
        event_type="group_view",
        outcome="ok",
        detail=f"Group {group.group_id} viewed.",
        principal=principal,
        correlation_id=uuid.uuid4().hex,
    )
    return {
        "banner": SYNTHETIC_BANNER,
        "group_id": group.group_id,
        "name": group.name,
        "headquarters_jurisdiction": group.headquarters_jurisdiction,
        "primary_industry": group.primary_industry,
        "entities_in_portfolio": entities,
        "entities_outside_portfolio": len(members) - len(visible),
        "original_currency_drawn": {currency: amount for currency, amount in sorted(by_currency.items())},
        "drawn_hkd": sum_hkd(hkd_parts) if hkd_parts else None,
        "calculation_basis": "HKD total = sum of stored HKD equivalents. Original-currency amounts are not added across currencies.",
        "currency": "HKD",
        "unit": "HKD",
        "as_of_date": entities[0]["position"]["as_of_date"] if entities else None,
        "source_system": "HMB Facility Subledger (synthetic)",
        "data_quality": "incomplete" if any(item["position"]["data_quality"] != "ok" for item in entities) else "ok",
    }


def list_groups(session: Session, principal: Principal) -> list[dict]:
    allowed = _scope(session, principal, "customer.read")
    customers = session.scalars(select(models.Customer).where(models.Customer.customer_id.in_(allowed or {""}))).all()
    grouped: dict[str, list] = defaultdict(list)
    for customer in customers:
        grouped[customer.group_id].append(customer)
    payload = []
    for group_id, members in sorted(grouped.items()):
        group = session.get(models.CustomerGroup, group_id)
        drawn_parts = []
        for member in members:
            position = _position(_latest_rows(session, member.customer_id))
            if position["drawn_hkd"] is not None:
                drawn_parts.append(position["drawn_hkd"])
        payload.append(
            {
                "group_id": group_id,
                "name": group.name if group else group_id,
                "entity_count": len(members),
                "drawn_hkd": sum_hkd(drawn_parts) if drawn_parts else None,
                "currency": "HKD",
                "unit": "HKD",
                "calculation_basis": "Sum of authorised entity HKD drawn amounts.",
            }
        )
    return payload


def dashboard(session: Session, principal: Principal) -> dict:
    allowed = _scope(session, principal, "portfolio.read")
    customers = session.scalars(select(models.Customer).where(models.Customer.customer_id.in_(allowed or {""}))).all()
    exposures = []
    deteriorating = []
    rising = []
    breaches = []
    near = []
    high_risk = []
    industry_totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    jurisdiction_totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    rating_counts: dict[str, int] = defaultdict(int)
    class_counts: dict[str, int] = defaultdict(int)
    book_by_date: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for customer in customers:
        rows = _latest_rows(session, customer.customer_id)
        position = _position(rows)
        ratings = _ratings(session, customer.customer_id)
        exposures.append((customer, position))
        class_counts[customer.customer_risk_classification] += 1
        if ratings:
            rating_counts[str(ratings[-1].rating)] += 1
        if position["total_exposure_hkd"] is not None:
            industry_totals[customer.industry] += position["total_exposure_hkd"]
            jurisdiction_totals[customer.jurisdiction] += position["total_exposure_hkd"]
        if len(ratings) >= 2 and ratings[-1].rating - ratings[0].rating >= int(SCORE["deterioration_notches"]):
            deteriorating.append({"customer_id": customer.customer_id, "legal_name": customer.legal_name, "trend": _trend(ratings)})
        history = session.scalars(
            select(models.FacilitySnapshot)
            .where(models.FacilitySnapshot.customer_id == customer.customer_id)
            .order_by(models.FacilitySnapshot.as_of_date)
        ).all()
        first: dict[str, models.FacilitySnapshot] = {}
        for row in history:
            first.setdefault(row.facility_id, row)
            if row.data_quality == "ok" and row.hkd_drawn is not None:
                book_by_date[row.as_of_date] += row.hkd_drawn
        for row in rows:
            opening = first.get(row.facility_id)
            if (
                opening
                and opening.utilisation_pct is not None
                and row.utilisation_pct is not None
                and row.utilisation_pct - opening.utilisation_pct >= Decimal("15")
            ):
                rising.append(
                    {
                        "customer_id": customer.customer_id,
                        "legal_name": customer.legal_name,
                        "facility_id": row.facility_id,
                        "from_pct": opening.utilisation_pct,
                        "to_pct": row.utilisation_pct,
                        "label": "Utilisation rising",
                    }
                )
            status = _limit_word(row)
            if status == "breach":
                breaches.append(_breach_row(customer, row))
            elif status == "near_breach":
                near.append(_breach_row(customer, row))
        if customer.customer_risk_classification == "High":
            high_risk.append({"customer_id": customer.customer_id, "legal_name": customer.legal_name, "classification": "High"})
    covenant_breaches = session.scalars(
        select(models.CovenantObservation).where(
            models.CovenantObservation.customer_id.in_(allowed or {""}),
            models.CovenantObservation.status == "breach",
        )
    ).all()
    overdue_reviews = session.scalars(
        select(models.Review).where(
            models.Review.customer_id.in_(allowed or {""}),
            models.Review.review_type == "annual_credit",
            models.Review.status == "overdue",
        )
    ).all()
    actions = session.scalars(
        select(models.ManagementAction).where(
            models.ManagementAction.customer_id.in_(allowed or {""}),
            models.ManagementAction.status == "open",
        )
    ).all()
    outstanding = [_action(row) for row in actions]
    ewis = session.scalars(
        select(models.EarlyWarning).where(
            models.EarlyWarning.customer_id.in_(allowed or {""}),
            models.EarlyWarning.status == "open",
        )
    ).all()
    visible = visible_document_ids(session, principal, allowed)
    documents = session.scalars(select(models.Document).where(models.Document.document_id.in_(visible or {""}))).all()
    stale_docs = [item for item in (_document_summary(row) for row in documents) if item["freshness"] == "Stale"]
    failures = session.scalars(
        select(models.Document).where(models.Document.ingestion_status.in_(["failed", "quarantined"]))
    ).all()
    # Quarantine records have no customer link that passed visibility. Show counts only, not filenames of hidden customers.
    failure_count = len(failures)
    domain_counts: dict[str, int] = defaultdict(int)
    for document in documents:
        domain_counts[document.risk_domain] += 1
    ranked = sorted(
        (
            {
                "customer_id": customer.customer_id,
                "legal_name": customer.legal_name,
                "group_id": customer.group_id,
                "total_exposure_hkd": position["total_exposure_hkd"],
            }
            for customer, position in exposures
            if position["total_exposure_hkd"] is not None
        ),
        key=lambda item: item["total_exposure_hkd"],
        reverse=True,
    )
    group_totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for customer, position in exposures:
        if position["drawn_hkd"] is not None:
            group_totals[customer.group_id] += position["drawn_hkd"]
    book = sum_hkd([item["total_exposure_hkd"] for item in ranked]) if ranked else ZERO
    write_audit(session, event_type="dashboard_view", outcome="ok", detail="Management dashboard viewed.", principal=principal)
    return {
        "banner": SYNTHETIC_BANNER,
        "as_of_date": format_date(demo_today()),
        "aggregate_exposure_hkd": book,
        "currency": "HKD",
        "unit": "HKD",
        "source_system": "HMB Facility Subledger (synthetic)",
        "calculation_basis": "Sum of authorised customer total exposure in stored HKD equivalents. Customers with unresolved facility amounts are omitted from the sum.",
        "data_quality": "ok",
        "top_customers": ranked[:8],
        "top_groups": [
            {"group_id": key, "drawn_hkd": value}
            for key, value in sorted(group_totals.items(), key=lambda item: item[1], reverse=True)[:8]
        ],
        "deteriorating_ratings": deteriorating,
        "rising_utilisation": rising,
        "limit_breaches": breaches,
        "near_breaches": near,
        "covenant_breaches": [
            {"customer_id": row.customer_id, "covenant_id": row.covenant_id, "status": "Breach", "as_of_date": row.as_of_date}
            for row in covenant_breaches
        ],
        "overdue_annual_reviews": [
            {"customer_id": row.customer_id, "due_date": row.due_date, "status": "Overdue"}
            for row in overdue_reviews
        ],
        "outstanding_actions": [row for row in outstanding if row["status"] in {"open", "overdue"}],
        "stale_documents": stale_docs[:25],
        "ingestion_failure_count": failure_count,
        "high_risk_classifications": high_risk,
        "early_warnings": [_ewi(row) for row in ewis],
        "risk_domain_distribution": dict(sorted(domain_counts.items())),
        "customer_count": len(customers),
        "open_ewi_count": len(ewis),
        "overdue_review_count": len(overdue_reviews),
        "industry_hkd": dict(sorted(industry_totals.items(), key=lambda item: item[1], reverse=True)),
        "jurisdiction_hkd": dict(sorted(jurisdiction_totals.items(), key=lambda item: item[1], reverse=True)),
        "rating_distribution": dict(sorted(rating_counts.items(), key=lambda item: int(item[0]))),
        "classification_distribution": dict(sorted(class_counts.items())),
        "exposure_history": [
            {
                "as_of_date": as_of,
                "value": amount,
                "currency": "HKD",
                "unit": "HKD",
                "source_system": "HMB Facility Subledger (synthetic)",
                "calculation_basis": "Sum of authorised HKD drawn amounts with data quality ok. Missing amounts are excluded, not treated as zero.",
                "data_quality": "ok",
            }
            for as_of, amount in sorted(book_by_date.items())
        ],
    }


def _breach_row(customer: models.Customer, row: models.FacilitySnapshot) -> dict:
    return {
        "customer_id": customer.customer_id,
        "legal_name": customer.legal_name,
        "facility_id": row.facility_id,
        "utilisation_pct": row.utilisation_pct,
        "limit_status": _limit_word(row),
        "as_of_date": row.as_of_date,
        "currency": row.currency,
        "source_system": row.source_system,
    }


def portfolio_view(session: Session, principal: Principal) -> dict:
    board = dashboard(session, principal)
    allowed = allowed_customer_ids(session, principal)
    rows = []
    customers = session.scalars(select(models.Customer).where(models.Customer.customer_id.in_(allowed or {""}))).all()
    for customer in customers:
        position = _position(_latest_rows(session, customer.customer_id))
        ratings = _ratings(session, customer.customer_id)
        rows.append(
            {
                "customer_id": customer.customer_id,
                "legal_name": customer.legal_name,
                "portfolio_id": customer.portfolio_id,
                "industry": customer.industry,
                "jurisdiction": customer.jurisdiction,
                "rating": ratings[-1].rating if ratings else None,
                "trend": _trend(ratings),
                "total_exposure_hkd": position["total_exposure_hkd"],
                "utilisation_pct": position["utilisation_pct"],
                "watchlist_status": customer.watchlist_status,
                "customer_risk_classification": customer.customer_risk_classification,
                "data_quality": position["data_quality"],
                "as_of_date": position["as_of_date"],
                "currency": "HKD",
                "unit": "HKD",
                "source_system": position["source_system"],
                "calculation_basis": position["calculation_basis"] if "calculation_basis" in position else "Stored HKD equivalents.",
            }
        )
    industry: dict[str, Decimal] = defaultdict(lambda: ZERO)
    country: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for row in rows:
        if row["total_exposure_hkd"] is None:
            continue
        industry[row["industry"]] += row["total_exposure_hkd"]
        country[row["jurisdiction"]] += row["total_exposure_hkd"]
    return {
        "banner": SYNTHETIC_BANNER,
        "customers": sorted(rows, key=lambda item: item["total_exposure_hkd"] or ZERO, reverse=True),
        "industry_hkd": dict(industry),
        "jurisdiction_hkd": dict(country),
        "aggregate_exposure_hkd": board["aggregate_exposure_hkd"],
        "currency": "HKD",
        "unit": "HKD",
        "source_system": board["source_system"],
        "calculation_basis": board["calculation_basis"],
        "data_quality": "Demonstration portfolio within the caller's entitlements.",
        "as_of_note": "Latest facility snapshot per customer. Mixed currencies are shown only after stored conversion to HKD.",
    }


def facilities_view(session: Session, principal: Principal) -> list[dict]:
    allowed = _scope(session, principal, "customer.read")
    payload = []
    customers = session.scalars(select(models.Customer).where(models.Customer.customer_id.in_(allowed or {""}))).all()
    for customer in customers:
        for facility in _facility_rows(session, customer.customer_id):
            payload.append({"legal_name": customer.legal_name, **facility})
    return payload


def covenants_view(session: Session, principal: Principal) -> list[dict]:
    allowed = _scope(session, principal, "customer.read")
    payload = []
    customers = session.scalars(select(models.Customer).where(models.Customer.customer_id.in_(allowed or {""}))).all()
    for customer in customers:
        for row in _covenants(session, customer.customer_id):
            payload.append({"legal_name": customer.legal_name, "customer_id": customer.customer_id, **row})
        for facility in _facility_rows(session, customer.customer_id):
            if facility["limit_status"] in {"breach", "near_breach", "unresolved"}:
                payload.append(
                    {
                        "legal_name": customer.legal_name,
                        "customer_id": customer.customer_id,
                        "name": f"Limit {facility['facility_id']}",
                        "status": facility["limit_status"],
                        "actual_value": facility["utilisation_pct"],
                        "unit": "percent",
                        "as_of_date": facility["as_of_date"],
                        "source_system": facility["source_system"],
                        "data_quality": facility["data_quality"],
                        "currency": facility["currency"],
                        "calculation_basis": facility["calculation_basis"],
                    }
                )
    return payload


def collateral_view(session: Session, principal: Principal) -> list[dict]:
    allowed = _scope(session, principal, "customer.read")
    payload = []
    for customer in session.scalars(select(models.Customer).where(models.Customer.customer_id.in_(allowed or {""}))).all():
        position = _position(_latest_rows(session, customer.customer_id))
        for item in _collateral(session, customer.customer_id):
            coverage = None
            if position["drawn_hkd"] not in (None, ZERO):
                coverage = (item["hkd_amount"] / position["drawn_hkd"]).quantize(Decimal("0.01"))
            payload.append(
                {
                    "legal_name": customer.legal_name,
                    "customer_id": customer.customer_id,
                    "drawn_hkd": position["drawn_hkd"],
                    "coverage": coverage,
                    "coverage_label": "Below 1.00" if coverage is not None and coverage < 1 else "At least 1.00" if coverage is not None else "Not calculated",
                    **item,
                }
            )
    return payload


def ewi_view(session: Session, principal: Principal) -> list[dict]:
    allowed = _scope(session, principal, "customer.read")
    rows = session.scalars(
        select(models.EarlyWarning).where(models.EarlyWarning.customer_id.in_(allowed or {""}))
    ).all()
    payload = []
    for row in rows:
        customer = session.get(models.Customer, row.customer_id)
        payload.append({"legal_name": customer.legal_name if customer else row.customer_id, "customer_id": row.customer_id, **_ewi(row)})
    return payload


def aml_view(session: Session, principal: Principal) -> dict:
    correlation_id = uuid.uuid4().hex
    if not principal.can("aml.read"):
        write_audit(
            session,
            event_type="access_denied",
            outcome="denied",
            detail="AML view requested without permission.",
            principal=principal,
            correlation_id=correlation_id,
            aml_access=True,
        )
        return {"restricted": True, "message": AML_RESTRICTION, "banner": SYNTHETIC_BANNER, "rows": []}
    allowed = _scope(session, principal, "customer.read")
    customers = session.scalars(select(models.Customer).where(models.Customer.customer_id.in_(allowed or {""}))).all()
    rows = []
    for customer in customers:
        alerts = session.scalars(select(models.Alert).where(models.Alert.customer_id == customer.customer_id)).all()
        reviews = session.scalars(
            select(models.Review).where(
                models.Review.customer_id == customer.customer_id,
                models.Review.sensitivity == "aml",
            )
        ).all()
        if customer.aml_risk_classification == "Low" and not alerts and not reviews:
            continue
        rows.append(
            {
                "customer_id": customer.customer_id,
                "legal_name": customer.legal_name,
                "aml_risk_classification": customer.aml_risk_classification,
                "alerts": [_alert(row) for row in alerts],
                "reviews": [_review(row) for row in reviews],
                "notice": AML_CONTROL_NOTICE,
            }
        )
    write_audit(
        session,
        event_type="aml_view",
        outcome="ok",
        detail="AML indicator view opened.",
        principal=principal,
        correlation_id=correlation_id,
        aml_access=True,
    )
    return {"restricted": False, "message": AML_CONTROL_NOTICE, "banner": SYNTHETIC_BANNER, "rows": rows}


def documents_view(session: Session, principal: Principal) -> list[dict]:
    allowed = _scope(session, principal, "document.read")
    visible = visible_document_ids(session, principal, allowed)
    rows = session.scalars(select(models.Document).where(models.Document.document_id.in_(visible or {""}))).all()
    return [_document_summary(row) for row in sorted(rows, key=lambda item: (item.reporting_date, item.title), reverse=True)]


def data_quality_view(session: Session, principal: Principal) -> dict:
    _scope(session, principal, "data_quality.read")
    allowed = allowed_customer_ids(session, principal)
    issues = session.scalars(select(models.DataQualityIssue)).all()
    visible_issues = [row for row in issues if row.customer_id is None or row.customer_id in allowed]
    conflicts = session.scalars(
        select(models.FacilitySnapshot).where(
            models.FacilitySnapshot.customer_id.in_(allowed or {""}),
            models.FacilitySnapshot.data_quality != "ok",
        )
    ).all()
    documents = documents_view(session, principal) if principal.can("document.read") else []
    return {
        "banner": SYNTHETIC_BANNER,
        "issues": [_issue(row) for row in visible_issues],
        "unresolved_snapshots": [
            {
                "customer_id": row.customer_id,
                "facility_id": row.facility_id,
                "as_of_date": row.as_of_date,
                "data_quality": row.data_quality,
                "source_system": row.source_system,
            }
            for row in conflicts
            if row.as_of_date == _latest_date(session, row.customer_id)
        ],
        "stale_documents": [row for row in documents if row["freshness"] == "Stale"],
        "ingestion_exceptions": [
            {
                "document_id": row.document_id,
                "title": row.title,
                "status": row.ingestion_status,
                "reason": row.quarantine_reason,
            }
            for row in session.scalars(select(models.Document).where(models.Document.ingestion_status != "indexed")).all()
            if row.document_id in visible_document_ids(session, principal, allowed)
            or (
                row.ingestion_status == "quarantined"
                and (row.portfolio_id is None or row.portfolio_id in principal.portfolio_ids)
            )
        ],
    }


def governance_view(session: Session, principal: Principal) -> dict:
    require_permission(principal, "governance.read")
    meta = {row.key: row.value for row in session.scalars(select(models.DatasetMeta)).all()}
    controls = session.scalars(select(models.ControlState)).all()
    return {
        "banner": SYNTHETIC_BANNER,
        "intended_purpose": meta.get("intended_purpose"),
        "system_owner": meta.get("system_owner"),
        "risk_owner": meta.get("risk_owner"),
        "periodic_review_date": meta.get("periodic_review_date"),
        "independent_validation": meta.get("independent_validation"),
        "training_data_declaration": meta.get("training_data_declaration"),
        "residual_risks": meta.get("residual_risks"),
        "models": [
            {
                "model_id": row.model_id,
                "provider": row.provider,
                "purpose": row.purpose,
                "creates_numeric_scores": row.creates_numeric_scores,
                "status": row.status,
                "version": row.version,
            }
            for row in session.scalars(select(models.ModelRegistry)).all()
        ],
        "prompts": [
            {"prompt_id": row.prompt_id, "version": row.version, "purpose": row.purpose}
            for row in session.scalars(select(models.PromptRegistry)).all()
        ],
        "prohibited_uses": [
            {"code": row.code, "statement": row.statement}
            for row in session.scalars(select(models.ProhibitedUse)).all()
        ],
        "third_parties": [
            {"name": row.name, "role": row.role, "data_shared": row.data_shared, "enabled": row.enabled, "review_status": row.review_status}
            for row in session.scalars(select(models.ThirdParty)).all()
        ],
        "controls": [
            {"key": row.key, "value": row.value, "updated_by": row.updated_by, "updated_at": row.updated_at, "note": row.note}
            for row in controls
        ],
        "incidents": [
            {"incident_id": row.incident_id, "opened_on": row.opened_on, "summary": row.summary, "status": row.status, "severity": row.severity}
            for row in session.scalars(select(models.AiIncident)).all()
        ],
        "taxonomy": [
            {"code": row.code, "name": row.name, "description": row.description, "owner_function": row.owner_function}
            for row in session.scalars(select(models.RiskTaxon).order_by(models.RiskTaxon.name)).all()
        ],
    }


def audit_view(session: Session, principal: Principal, limit: int = 200) -> list[dict]:
    require_permission(principal, "audit.read")
    rows = session.scalars(select(models.AuditEvent).order_by(models.AuditEvent.created_at.desc()).limit(limit)).all()
    write_audit(session, event_type="audit_view", outcome="ok", detail="Audit activity viewed.", principal=principal)
    return [
        {
            "audit_id": row.audit_id,
            "created_at": row.created_at,
            "event_type": row.event_type,
            "username": row.username,
            "role": row.role,
            "customer_id": row.customer_id,
            "document_id": row.document_id,
            "outcome": row.outcome,
            "aml_access": row.aml_access,
            "correlation_id": row.correlation_id,
            "detail": row.detail,
        }
        for row in rows
    ]


def admin_view(session: Session, principal: Principal) -> dict:
    if not (principal.can("admin.users") or principal.can("model.admin") or principal.can("admin.demo_mode")):
        raise AccessDeniedError("Administration is outside this role.")
    users = []
    if principal.can("admin.users"):
        for user in session.scalars(select(models.User).order_by(models.User.username)).all():
            portfolios = session.scalars(
                select(models.UserPortfolio.portfolio_id).where(models.UserPortfolio.user_id == user.user_id)
            ).all()
            users.append(
                {
                    "username": user.username,
                    "display_name": user.display_name,
                    "role": user.role,
                    "active": user.active,
                    "portfolios": list(portfolios),
                    "fictional_notice": user.fictional_notice,
                }
            )
    controls = [
        {"key": row.key, "value": row.value, "note": row.note, "updated_at": row.updated_at}
        for row in session.scalars(select(models.ControlState)).all()
    ]
    return {"banner": SYNTHETIC_BANNER, "users": users, "controls": controls}


def set_control(session: Session, principal: Principal, key: str, enabled: bool) -> dict:
    if key == "ai_kill_switch":
        require_permission(principal, "model.admin")
    elif key == "demo_mode":
        require_permission(principal, "admin.demo_mode")
    else:
        raise AccessDeniedError("That control is not configurable.")
    row = session.get(models.ControlState, key)
    if row is None:
        raise AccessDeniedError("That control is not configurable.")
    row.value = "true" if enabled else "false"
    row.updated_by = principal.username
    from app.domain.dates import utcnow

    row.updated_at = utcnow()
    write_audit(
        session,
        event_type="control_change",
        outcome="ok",
        detail=f"{key} set to {row.value}.",
        principal=principal,
    )
    return {"key": key, "value": row.value}
