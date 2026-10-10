"""Portfolio and role checks. Scope is applied before content is read."""

from __future__ import annotations

from typing import NoReturn

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import write_audit
from app.domain.banner import DENIAL_MESSAGE
from app.domain.errors import AccessDeniedError, AuthorisationError
from app.models.tables import Customer, Document, DocumentCustomer
from app.security.principal import Principal


def require_permission(principal: Principal, permission: str) -> None:
    if not principal.can(permission):
        raise AccessDeniedError(DENIAL_MESSAGE)


def allowed_customer_ids(session: Session, principal: Principal) -> set[str]:
    """Customer scope. Empty means the caller can see no customers."""
    if not principal.can("customer.read") or not principal.portfolio_ids:
        return set()
    rows = session.scalars(
        select(Customer.customer_id).where(Customer.portfolio_id.in_(principal.portfolio_ids))
    ).all()
    return set(rows)


def name_index(session: Session) -> list[dict[str, str]]:
    """Identifiers only. Financial attributes are not loaded for resolution."""
    rows = session.execute(
        select(
            Customer.customer_id,
            Customer.legal_name,
            Customer.group_id,
            Customer.portfolio_id,
        )
    ).all()
    return [
        {
            "customer_id": row.customer_id,
            "legal_name": row.legal_name,
            "group_id": row.group_id,
            "portfolio_id": row.portfolio_id,
        }
        for row in rows
    ]


def deny(
    session: Session,
    principal: Principal,
    *,
    customer_id: str | None,
    detail: str,
    correlation_id: str,
) -> NoReturn:
    write_audit(
        session,
        event_type="access_denied",
        outcome="denied",
        detail=detail,
        principal=principal,
        customer_id=customer_id,
        correlation_id=correlation_id,
    )
    raise AccessDeniedError(DENIAL_MESSAGE)


def ensure_customers_allowed(
    session: Session,
    principal: Principal,
    customer_ids: set[str],
    *,
    correlation_id: str,
) -> set[str]:
    allowed = allowed_customer_ids(session, principal)
    blocked = customer_ids - allowed
    if blocked:
        deny(
            session,
            principal,
            customer_id=sorted(blocked)[0],
            detail="Direct retrieval blocked before content queries.",
            correlation_id=correlation_id,
        )
    return allowed


def visible_document_ids(session: Session, principal: Principal, allowed_customers: set[str]) -> set[str]:
    """Fail closed: a document is hidden if any linked customer is outside scope."""
    if allowed_customers is None:
        raise AuthorisationError("Document visibility requires an authorisation scope.")
    links: dict[str, set[str]] = {}
    for document_id, customer_id in session.execute(
        select(DocumentCustomer.document_id, DocumentCustomer.customer_id)
    ):
        links.setdefault(document_id, set()).add(customer_id)
    visible: set[str] = set()
    rows = session.execute(
        select(
            Document.document_id,
            Document.sensitivity,
            Document.enterprise,
            Document.ingestion_status,
        )
    ).all()
    enterprise_ok = principal.can("portfolio.enterprise")
    aml_ok = principal.can("aml.read")
    for document_id, sensitivity, enterprise, status in rows:
        if status != "indexed":
            continue
        if sensitivity == "aml" and not aml_ok:
            continue
        linked = links.get(document_id, set())
        if enterprise and not linked:
            if enterprise_ok:
                visible.add(document_id)
            continue
        if linked and linked <= allowed_customers:
            visible.add(document_id)
    return visible
