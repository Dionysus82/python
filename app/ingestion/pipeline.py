"""Ingestion pipeline. File content is untrusted and cannot change controls."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.audit.service import write_audit
from app.domain.dates import utcnow
from app.ingestion.store import TrustedDocumentStore
from app.models.tables import Document, DocumentChunk, EvidenceStatement, IngestionEvent
from app.parsers import PARSERS
from app.security.injection import find_injection


def _event(session: Session, document_id: str | None, stage: str, status: str, detail: str, correlation_id: str) -> None:
    session.add(
        IngestionEvent(
            event_id=f"ING-{uuid.uuid4().hex[:16]}",
            document_id=document_id,
            stage=stage,
            status=status,
            detail=detail[:1500],
            created_at=utcnow(),
            correlation_id=correlation_id,
        )
    )


def ingest_document(
    session: Session,
    store: TrustedDocumentStore,
    document: Document,
    *,
    correlation_id: str,
    actor: str,
) -> str:
    try:
        data = store.get(document.storage_key)
    except Exception as exc:  # noqa: BLE001
        document.ingestion_status = "failed"
        document.parser_status = "failed"
        document.quarantine_reason = "The stored object could not be read."
        _event(session, document.document_id, "read", "failed", str(exc), correlation_id)
        return "failed"
    parser = PARSERS.get(document.mime_type)
    if parser is None:
        document.ingestion_status = "quarantined"
        document.parser_status = "unsupported"
        document.quarantine_reason = "Unsupported MIME type."
        _event(session, document.document_id, "parser_selection", "failed", document.quarantine_reason, correlation_id)
        return "quarantined"
    parsed = parser(data)
    if parsed.password_protected or parsed.corrupt:
        document.ingestion_status = "quarantined"
        document.parser_status = "failed"
        document.quarantine_reason = parsed.error or "The file could not be parsed."
        _event(session, document.document_id, "parse", "failed", document.quarantine_reason, correlation_id)
        return "quarantined"
    if "SYNTHETIC" not in (parsed.text or ""):
        document.ingestion_status = "quarantined"
        document.parser_status = "rejected"
        document.quarantine_reason = "Synthetic-data declaration not found in extracted text."
        _event(session, document.document_id, "synthetic_check", "failed", document.quarantine_reason, correlation_id)
        return "quarantined"
    session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.document_id))
    injection = False
    for index, chunk in enumerate(parsed.chunks, start=1):
        injection = injection or chunk.prompt_injection_suspected
        session.add(
            DocumentChunk(
                chunk_id=f"{document.document_id}-C{index:03d}",
                document_id=document.document_id,
                text=chunk.text,
                locator=chunk.locator,
                sensitivity=document.sensitivity,
                prompt_injection_suspected=chunk.prompt_injection_suspected,
                token_count=len(chunk.text.split()),
            )
        )
    document.extracted_text = parsed.text
    document.page_count = parsed.page_count
    document.sheet_metadata = parsed.sheet_metadata
    document.section_metadata = parsed.section_metadata
    document.parser_status = "parsed"
    document.ingestion_status = "indexed"
    document.malware_scan_status = "not_scanned_hackathon_placeholder"
    document.prompt_injection_suspected = injection or bool(find_injection(parsed.text))
    _event(session, document.document_id, "index", "ok", "Document indexed.", correlation_id)
    if document.prompt_injection_suspected:
        write_audit(
            session,
            event_type="prompt_injection_detected",
            outcome="logged",
            detail="Instruction-like text was found in a document and stored only as content.",
            username=actor,
            document_id=document.document_id,
            correlation_id=correlation_id,
        )
    _link_statements(session, document.document_id)
    return "indexed"


def _link_statements(session: Session, document_id: str) -> None:
    statements = session.scalars(
        select(EvidenceStatement).where(EvidenceStatement.document_id == document_id)
    ).all()
    chunks = session.scalars(select(DocumentChunk).where(DocumentChunk.document_id == document_id)).all()
    for statement in statements:
        needle = " ".join(statement.text.split())
        match = next(
            (
                chunk
                for chunk in chunks
                if needle and needle in " ".join(chunk.text.split())
            ),
            None,
        )
        if match is not None:
            statement.chunk_id = match.chunk_id
            locator = dict(statement.locator or {})
            for key, value in match.locator.items():
                locator.setdefault(key, value)
            statement.locator = locator


def ingest_pending(session: Session, store: TrustedDocumentStore, *, actor: str = "system") -> dict[str, int]:
    correlation_id = uuid.uuid4().hex
    counts = {"indexed": 0, "quarantined": 0, "failed": 0}
    documents = session.scalars(select(Document).where(Document.ingestion_status == "pending")).all()
    for document in documents:
        status = ingest_document(
            session, store, document, correlation_id=correlation_id, actor=actor
        )
        counts[status] = counts.get(status, 0) + 1
    session.commit()
    return counts
