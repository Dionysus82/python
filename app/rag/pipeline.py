"""Question answering. Authorisation runs before content retrieval."""

from __future__ import annotations

import re
import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.service import write_audit
from app.authorisation.service import (
    allowed_customer_ids,
    deny,
    name_index,
    visible_document_ids,
)
from app.citations.format import citation_detail
from app.config import load_json
from app.domain.banner import (
    AML_CONTROL_NOTICE,
    AML_RESTRICTION,
    INSUFFICIENT_EVIDENCE,
)
from app.domain.dates import format_date
from app.domain.errors import AccessDeniedError
from app.domain.money import format_money, sum_hkd
from app.models.tables import (
    CollateralValuation,
    ControlState,
    Customer,
    CustomerGroup,
    Document,
    EvidenceStatement,
    FacilitySnapshot,
    RatingHistory,
    Review,
)
from app.rag.claims import build_customer_claims, select_claims, validate_claims
from app.retrieval.search import search_authorised
from app.security.injection import find_injection, is_unsupported_allegation
from app.security.principal import Principal

SCORE = load_json("risk_score.json")
PORTFOLIO_HINTS = (
    "which customers",
    "which high-risk",
    "which limits",
    "limits are close",
    "stale credit",
    "weak collateral",
    "deteriorating rating",
)
HISTORICAL_HINTS = ("what changed", "previous", "since the", "history", "compared with", "supersed")
AML_HINTS = ("aml", "financial-crime", "financial crime", "sanctions", "pep", "transaction-monitoring", "transaction monitoring")


def ask(
    session: Session,
    principal: Principal,
    question: str,
    *,
    focus_customer_id: str | None = None,
) -> dict:
    correlation_id = uuid.uuid4().hex
    if not principal.can("ask.use"):
        deny(
            session,
            principal,
            customer_id=None,
            detail="Question rejected before retrieval because the role cannot ask.",
            correlation_id=correlation_id,
        )
    allowed = allowed_customer_ids(session, principal)
    injection = find_injection(question)
    if injection:
        write_audit(
            session,
            event_type="prompt_injection_detected",
            outcome="logged",
            detail="Instruction-like user text was logged and was not followed.",
            principal=principal,
            correlation_id=correlation_id,
        )
    matched = _match_customers(session, question, focus_customer_id)
    blocked = [item for item in matched if item["customer_id"] not in allowed]
    if blocked:
        deny(
            session,
            principal,
            customer_id=blocked[0]["customer_id"],
            detail="Named customer is outside the authorised portfolio. Retrieval was not started.",
            correlation_id=correlation_id,
        )
    intents = _intents(question)
    historical = any(hint in question.lower() for hint in HISTORICAL_HINTS)
    if injection and not matched and not _is_portfolio(question):
        return _abstain(
            question,
            correlation_id,
            "The request was treated as untrusted instruction text and was not followed. "
            + INSUFFICIENT_EVIDENCE,
            intents,
        )
    if is_unsupported_allegation(question):
        if not _allegation_supported(session, matched, allowed):
            write_audit(
                session,
                event_type="ask_question",
                outcome="abstained",
                detail="Unsupported allegation.",
                principal=principal,
                customer_id=matched[0]["customer_id"] if matched else None,
                correlation_id=correlation_id,
            )
            return _abstain(question, correlation_id, INSUFFICIENT_EVIDENCE, intents)
    group = _match_group(session, question)
    if group is not None:
        return _group_answer(session, principal, question, group, allowed, correlation_id, intents)
    if _is_portfolio(question) and not matched:
        return _portfolio_answer(session, principal, question, allowed, correlation_id, intents)
    if not matched:
        return _abstain(
            question,
            correlation_id,
            "Name a customer, counterparty or group, or ask a portfolio question. " + INSUFFICIENT_EVIDENCE,
            intents,
        )
    if "aml" in intents and not principal.can("aml.read") and intents <= {"aml", "general"}:
        write_audit(
            session,
            event_type="access_denied",
            outcome="denied",
            detail="AML indicators were requested without permission.",
            principal=principal,
            customer_id=matched[0]["customer_id"],
            correlation_id=correlation_id,
            aml_access=True,
        )
        return _package(
            question,
            correlation_id,
            AML_RESTRICTION,
            [],
            intents,
            [item["customer_id"] for item in matched],
            abstained=False,
            control_notice=AML_RESTRICTION,
        )
    visible = visible_document_ids(session, principal, allowed)
    claims: list[dict] = []
    evidence_ids: list[str] = []
    version_rule = None
    for item in matched:
        customer_claims = build_customer_claims(
            session,
            principal,
            item["customer_id"],
            visible,
            historical=historical,
        )
        claims.extend(select_claims(customer_claims, intents))
        if session.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.superseded.is_(True), Document.document_id.in_(visible or {""}))
        ):
            version_rule = (
                "Version rule: a current-state question uses the latest reporting date among documents "
                "that are not superseded. A later upload does not outrank an earlier reporting date. "
                "Superseded documents remain available for history and comparison."
            )
    claims = validate_claims(session, claims, allowed, visible)
    customer_ids = [item["customer_id"] for item in matched]
    evidence = search_authorised(
        session,
        question,
        _customer_docs(session, customer_ids, visible),
        include_superseded=historical,
    )
    evidence_ids = sorted({hit["document_id"] for hit in evidence})
    if not claims:
        message = INSUFFICIENT_EVIDENCE
        abstained = True
    else:
        message = _render(claims, version_rule, "aml" in intents and principal.can("aml.read"))
        abstained = False
    if "aml" in intents and not principal.can("aml.read"):
        message = AML_RESTRICTION + "\n" + message
    write_audit(
        session,
        event_type="ask_question",
        outcome="abstained" if abstained else "answered",
        detail=question[:500],
        principal=principal,
        customer_id=customer_ids[0],
        correlation_id=correlation_id,
        aml_access="aml" in intents and principal.can("aml.read"),
    )
    kill = _kill_switch(session)
    commentary = None if kill or abstained else (
        "Model-generated interpretation: the statements above restate cited records and deterministic calculations. "
        "This text is not an approved credit rating, risk acceptance or customer decision."
    )
    return _package(
        question,
        correlation_id,
        message,
        claims,
        intents,
        customer_ids,
        abstained=abstained,
        evidence_document_ids=evidence_ids,
        version_rule=version_rule,
        control_notice=AML_CONTROL_NOTICE if "aml" in intents and principal.can("aml.read") else None,
        model_commentary=commentary,
        kill_switch=kill,
    )


def _claim_docs(claim: dict) -> set[str]:
    return {citation["document_id"] for citation in claim["citations"] if citation.get("document_id")}


def _customer_docs(session: Session, customer_ids: list[str], visible: set[str]) -> set[str]:
    from app.models.tables import DocumentCustomer

    rows = session.scalars(
        select(DocumentCustomer.document_id).where(DocumentCustomer.customer_id.in_(customer_ids))
    ).all()
    return {document_id for document_id in rows if document_id in visible}


def _match_customers(session: Session, question: str, focus_customer_id: str | None) -> list[dict]:
    folded = question.casefold()
    found = []
    for entry in sorted(name_index(session), key=lambda item: len(item["legal_name"]), reverse=True):
        if entry["legal_name"].casefold() in folded or entry["customer_id"].casefold() in folded:
            found.append(entry)
    if focus_customer_id and "this customer" in folded:
        for entry in name_index(session):
            if entry["customer_id"] == focus_customer_id and entry not in found:
                found.append(entry)
    # Prefer the most specific names and drop a shorter name contained in a matched longer name.
    specific = []
    for entry in found:
        if any(
            other["legal_name"].casefold() != entry["legal_name"].casefold()
            and entry["legal_name"].casefold() in other["legal_name"].casefold()
            and other["legal_name"].casefold() in folded
            for other in found
        ):
            continue
        specific.append(entry)
    return specific


def _match_group(session: Session, question: str) -> CustomerGroup | None:
    folded = question.casefold()
    groups = session.scalars(select(CustomerGroup)).all()
    for group in sorted(groups, key=lambda item: len(item.name), reverse=True):
        if group.name.casefold() in folded or group.group_id.casefold() in folded:
            return group
    return None


def _is_portfolio(question: str) -> bool:
    folded = question.lower()
    return any(hint in folded for hint in PORTFOLIO_HINTS)


def _hint_present(folded: str, hint: str) -> bool:
    """Match phrases as text and single words on boundaries.

    A legal name ending in "Limited" must not be read as a limit question.
    """
    if " " in hint or "-" in hint:
        return hint in folded
    return re.search(rf"\b{re.escape(hint)}s?\b", folded) is not None


def _intents(question: str) -> set[str]:
    folded = question.lower()
    intents = set()
    rules = {
        "exposure": ("exposure", "drawn", "total exposure"),
        "facilities": ("facility", "facilities", "what facilities", "products"),
        "limits": ("limit", "utilisation", "utilization", "undrawn", "close to breach", "near breach"),
        "rating": ("rating", "probability of default"),
        "liquidity": ("liquidity", "deposit", "cash reserve", "cash flow"),
        "covenant": ("covenant",),
        "collateral": ("collateral", "guarantee", "mitigant"),
        "market": ("foreign-exchange", "foreign exchange", "interest-rate", "interest rate", "market risk"),
        "aml": AML_HINTS,
        "ewi": ("early-warning", "early warning", "ewi"),
        "review": ("overdue", "annual review", "annual credit review", "stale"),
        "actions": ("outstanding action", "actions remain", "action"),
        "change": ("what changed", "previous reporting", "deteriorat"),
        "relationship": ("relationship", "summarise the bank", "summarize the bank"),
        "watchlist": ("watchlist",),
        "operational": ("operational", "cyber", "incident"),
        "compare": ("compare",),
        "risk_overview": ("main risk", "risks associated", "consolidated risk"),
    }
    for intent, hints in rules.items():
        if any(_hint_present(folded, hint) for hint in hints):
            intents.add(intent)
    if "risk_overview" in intents:
        intents.update({"rating", "limits", "liquidity", "covenant", "ewi", "review", "collateral", "exposure"})
    if "compare" in intents:
        intents.update({"rating", "liquidity", "exposure"})
    return intents or {"general"}


def _allegation_supported(session: Session, matched: list[dict], allowed: set[str]) -> bool:
    if not matched:
        return False
    ids = [item["customer_id"] for item in matched if item["customer_id"] in allowed]
    if not ids:
        return False
    texts = session.scalars(
        select(EvidenceStatement.text).where(EvidenceStatement.customer_id.in_(ids))
    ).all()
    haystack = " ".join(texts).lower()
    return any(word in haystack for word in ("convicted", "bribery", "criminal", "guilty", "prison"))


def _group_answer(session, principal, question, group, allowed, correlation_id, intents) -> dict:
    members = session.scalars(select(Customer).where(Customer.group_id == group.group_id)).all()
    visible_members = [member for member in members if member.customer_id in allowed]
    if not visible_members:
        deny(
            session,
            principal,
            customer_id=members[0].customer_id if members else None,
            detail="Group has no entity inside the authorised portfolio.",
            correlation_id=correlation_id,
        )
    claims = []
    components = []
    for member in visible_members:
        snapshots = session.scalars(
            select(FacilitySnapshot).where(FacilitySnapshot.customer_id == member.customer_id)
        ).all()
        if not snapshots:
            continue
        latest = max(row.as_of_date for row in snapshots)
        current = [row for row in snapshots if row.as_of_date == latest and row.data_quality == "ok" and row.hkd_drawn is not None]
        if not current:
            continue
        drawn = sum_hkd([row.hkd_drawn for row in current])
        original = ", ".join(
            f"{format_money(row.drawn, row.currency)} × {row.fx_rate} = {format_money(row.hkd_drawn, 'HKD')} "
            f"(rate date {format_date(row.fx_rate_date)}, source {row.fx_source}, method {row.fx_method})"
            for row in current
        )
        text = (
            f"{member.legal_name} ({member.customer_id}) drawn exposure in HKD is {format_money(drawn, 'HKD')}. "
            f"Original currency basis: {original}."
        )
        claims.append(
            {
                "claim_id": f"CLM-GRP-{member.customer_id}",
                "customer_id": member.customer_id,
                "text": text,
                "claim_type": "calculation",
                "metric_key": "group_drawn_hkd",
                "value": f"{drawn:.2f}",
                "unit": "HKD",
                "currency": "HKD",
                "as_of_date": latest,
                "citations": [
                    {
                        "kind": "database",
                        "source_system": row.source_system,
                        "record_table": "facility_snapshots",
                        "record_id": row.snapshot_id,
                        "customer_id": row.customer_id,
                        "as_of_date": row.as_of_date,
                        "calculated_at": row.calculated_at,
                        "unit": "HKD",
                        "currency": row.currency,
                        "hkd_equivalent": f"{row.hkd_drawn:.2f}",
                        "excerpt": text,
                        "source_title": row.source_system,
                        "reporting_date": row.as_of_date,
                        "document_id": None,
                        "original_filename": None,
                        "risk_domain": "credit",
                        "version": None,
                        "authoring_function": None,
                        "page": None,
                        "sheet": None,
                        "cell_range": None,
                        "section": None,
                        "paragraph": None,
                        "viewer_route": None,
                    }
                    for row in current
                ],
                "stale": False,
                "formula": "group_hkd = sum(amount × stored HKD rate). Unconverted amounts are not added together.",
                "tags": ["exposure"],
            }
        )
        components.append(drawn)
    if not components:
        return _abstain(question, correlation_id, INSUFFICIENT_EVIDENCE, intents)
    total = sum_hkd(components)
    claims.insert(
        0,
        {
            "claim_id": f"CLM-GRP-{group.group_id}",
            "customer_id": None,
            "text": (
                f"Authorised drawn exposure for {group.name} is {format_money(total, 'HKD')}. "
                "The total uses stored HKD equivalents only."
            ),
            "claim_type": "calculation",
            "metric_key": "group_total_hkd",
            "value": f"{total:.2f}",
            "unit": "HKD",
            "currency": "HKD",
            "as_of_date": claims[0]["as_of_date"],
            "citations": [citation for claim in claims for citation in claim["citations"]],
            "stale": False,
            "formula": "sum of authorised entity HKD drawn exposure",
            "tags": ["exposure"],
        },
    )
    notice = None
    if len(visible_members) < len(members):
        notice = "Group figures include only entities in your authorised portfolio."
    message = _render(claims, notice, False)
    write_audit(
        session,
        event_type="ask_question",
        outcome="answered",
        detail=question[:500],
        principal=principal,
        correlation_id=correlation_id,
    )
    return _package(
        question,
        correlation_id,
        message,
        claims,
        intents,
        [member.customer_id for member in visible_members],
        abstained=False,
        version_rule=notice,
    )


def _portfolio_answer(session, principal, question, allowed, correlation_id, intents) -> dict:
    folded = question.lower()
    customers = session.scalars(select(Customer).where(Customer.customer_id.in_(allowed or {""}))).all()
    claims = []
    if "deteriorating" in folded or "high exposure" in folded:
        threshold = Decimal(str(SCORE["high_exposure_hkd"]))
        notches = int(SCORE["deterioration_notches"])
        for customer in customers:
            ratings = session.scalars(
                select(RatingHistory)
                .where(RatingHistory.customer_id == customer.customer_id)
                .order_by(RatingHistory.as_of_date)
            ).all()
            if len(ratings) < 2 or ratings[-1].rating - ratings[0].rating < notches:
                continue
            snapshots = _latest(session, customer.customer_id)
            if any(row.hkd_drawn is None for row in snapshots):
                continue
            drawn = sum_hkd([row.hkd_drawn for row in snapshots])
            if drawn < threshold:
                continue
            text = (
                f"{customer.legal_name} ({customer.customer_id}) is in scope: drawn exposure "
                f"{format_money(drawn, 'HKD')} and internal credit rating moved from {ratings[0].rating} "
                f"on {format_date(ratings[0].as_of_date)} to {ratings[-1].rating} on {format_date(ratings[-1].as_of_date)}."
            )
            claims.append(_simple_claim(customer.customer_id, text, "portfolio_deteriorating", ratings[-1].rating_id, "rating_history", ratings[-1].as_of_date))
    elif "stale" in folded or "overdue" in folded:
        reviews = session.scalars(
            select(Review).where(
                Review.customer_id.in_(allowed or {""}),
                Review.review_type == "annual_credit",
                Review.status == "overdue",
            )
        ).all()
        for review in reviews:
            customer = session.get(Customer, review.customer_id)
            text = (
                f"{customer.legal_name} ({customer.customer_id}) annual credit review status is overdue. "
                f"Due date {format_date(review.due_date)}."
            )
            claims.append(_simple_claim(customer.customer_id, text, "annual_review_status", review.review_id, "reviews", review.due_date))
    elif "weak collateral" in folded or "collateral coverage" in folded:
        for customer in customers:
            if customer.customer_risk_classification != "High":
                continue
            collateral = session.scalar(
                select(CollateralValuation).where(CollateralValuation.customer_id == customer.customer_id)
            )
            snapshots = _latest(session, customer.customer_id)
            if collateral is None or any(row.hkd_drawn is None for row in snapshots):
                continue
            drawn = sum_hkd([row.hkd_drawn for row in snapshots])
            if drawn <= 0:
                continue
            coverage = collateral.hkd_amount / drawn
            if coverage >= Decimal(str(SCORE["weak_collateral_coverage"])):
                continue
            text = (
                f"{customer.legal_name} ({customer.customer_id}) has customer risk classification High and "
                f"collateral coverage {coverage.quantize(Decimal('0.01'))}, below 1.00."
            )
            claims.append(_simple_claim(customer.customer_id, text, "collateral_coverage", collateral.valuation_id, "collateral_valuations", collateral.as_of_date))
    elif "limit" in folded:
        for customer in customers:
            for row in _latest(session, customer.customer_id):
                if row.utilisation_pct is None or row.data_quality != "ok":
                    continue
                if Decimal(str(SCORE["near_breach_utilisation_pct"])) <= row.utilisation_pct <= Decimal(str(SCORE["breach_utilisation_pct"])):
                    text = (
                        f"{customer.legal_name} facility {row.facility_id} utilisation is {row.utilisation_pct:.2f} percent, "
                        "which is close to breach and not over the limit."
                    )
                    claims.append(_simple_claim(customer.customer_id, text, f"utilisation_pct:{row.facility_id}", row.snapshot_id, "facility_snapshots", row.as_of_date))
    if not claims:
        return _abstain(question, correlation_id, INSUFFICIENT_EVIDENCE, intents)
    write_audit(
        session,
        event_type="ask_question",
        outcome="answered",
        detail=question[:500],
        principal=principal,
        correlation_id=correlation_id,
    )
    return _package(question, correlation_id, _render(claims, None, False), claims, intents, sorted({c["customer_id"] for c in claims}), abstained=False)


def _latest(session: Session, customer_id: str) -> list[FacilitySnapshot]:
    rows = session.scalars(select(FacilitySnapshot).where(FacilitySnapshot.customer_id == customer_id)).all()
    if not rows:
        return []
    latest = max(row.as_of_date for row in rows)
    return [row for row in rows if row.as_of_date == latest]


def _simple_claim(customer_id, text, metric_key, record_id, table, as_of) -> dict:
    return {
        "claim_id": f"CLM-{uuid.uuid4().hex[:8]}",
        "customer_id": customer_id,
        "text": text,
        "claim_type": "rule",
        "metric_key": metric_key,
        "value": None,
        "unit": None,
        "currency": None,
        "as_of_date": as_of,
        "citations": [
            {
                "kind": "database",
                "source_system": table,
                "source_title": table,
                "record_table": table,
                "record_id": record_id,
                "customer_id": customer_id,
                "as_of_date": as_of,
                "calculated_at": None,
                "unit": None,
                "currency": None,
                "hkd_equivalent": None,
                "excerpt": text,
                "document_id": None,
                "original_filename": None,
                "risk_domain": None,
                "reporting_date": as_of,
                "version": None,
                "authoring_function": None,
                "page": None,
                "sheet": None,
                "cell_range": None,
                "section": None,
                "paragraph": None,
                "viewer_route": None,
            }
        ],
        "stale": False,
        "formula": "Portfolio screen over authorised records.",
        "tags": ["general"],
    }


def _kill_switch(session: Session) -> bool:
    row = session.get(ControlState, "ai_kill_switch")
    return bool(row and row.value == "true")


def _render(claims: list[dict], version_rule: str | None, aml: bool) -> str:
    lines = []
    for claim in claims:
        prefix = {
            "sourced_fact": "Sourced fact",
            "calculation": "Deterministic calculation",
            "rule": "Rule-based classification",
            "contradiction": "Unresolved contradiction",
            "missing": "Missing evidence",
            "model_summary": "Model-generated summary",
        }.get(claim["claim_type"], "Note")
        lines.append(f"{prefix}: {claim['text']}")
    if version_rule:
        lines.append(version_rule)
    if aml:
        lines.append(AML_CONTROL_NOTICE)
    text = "\n".join(lines)
    for banned in ("recommend filing", "should be filed", "exit the customer", "clear the alert", "approve the credit"):
        if banned in text.lower():
            text = re.sub(banned, "requires qualified human review", text, flags=re.IGNORECASE)
    return text


def _abstain(question: str, correlation_id: str, message: str, intents: set[str]) -> dict:
    return _package(question, correlation_id, message, [], intents, [], abstained=True)


def _package(
    question,
    correlation_id,
    message,
    claims,
    intents,
    customer_ids,
    *,
    abstained: bool,
    evidence_document_ids: list[str] | None = None,
    version_rule: str | None = None,
    control_notice: str | None = None,
    model_commentary: str | None = None,
    kill_switch: bool = False,
) -> dict:
    return {
        "question": question,
        "abstained": abstained,
        "message": message,
        "claims": [
            {
                **claim,
                "as_of_date": format_date(claim["as_of_date"]) if claim.get("as_of_date") else None,
                "citations": [citation_detail(citation) for citation in claim.get("citations", [])],
            }
            for claim in claims
        ],
        "contradiction": any(claim["claim_type"] == "contradiction" for claim in claims),
        "intents": sorted(intents),
        "resolved_customer_ids": customer_ids,
        "evidence_document_ids": evidence_document_ids or [],
        "version_rule": version_rule,
        "control_notice": control_notice,
        "model_commentary": model_commentary,
        "kill_switch": kill_switch,
        "correlation_id": correlation_id,
        "grounding": "validated" if claims else "abstained",
    }


# Imported by tests that need to confirm denial does not query facts.
__all__ = ["ask", "AccessDeniedError"]
