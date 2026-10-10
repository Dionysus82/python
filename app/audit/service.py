"""Append-only audit records."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.domain.dates import utcnow
from app.models.tables import AuditEvent
from app.security.principal import Principal


def write_audit(
    session: Session,
    *,
    event_type: str,
    outcome: str,
    detail: str,
    principal: Principal | None = None,
    username: str | None = None,
    role: str | None = None,
    customer_id: str | None = None,
    document_id: str | None = None,
    correlation_id: str | None = None,
    aml_access: bool = False,
) -> AuditEvent:
    event = AuditEvent(
        audit_id=f"AUD-{uuid.uuid4().hex[:16]}",
        created_at=utcnow(),
        event_type=event_type,
        username=principal.username if principal else username,
        role=principal.role if principal else role,
        customer_id=customer_id,
        document_id=document_id,
        detail=detail[:2000],
        correlation_id=correlation_id or uuid.uuid4().hex,
        aml_access=aml_access,
        outcome=outcome,
    )
    session.add(event)
    session.flush()
    return event
