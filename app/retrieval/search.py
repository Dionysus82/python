"""Build a query-scoped index from authorised chunks only."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.errors import AuthorisationError
from app.embeddings.hashing import embed_text
from app.models.tables import Document, DocumentChunk
from app.retrieval.indexes import BM25Index, FeatureReranker, NumpyVectorIndex


def search_authorised(
    session: Session,
    query: str,
    allowed_document_ids: set[str] | None,
    *,
    k: int = 8,
    include_superseded: bool = False,
    include_injection_chunks: bool = False,
) -> list[dict]:
    if allowed_document_ids is None:
        raise AuthorisationError("Retrieval requires an authorisation scope before search.")
    if not allowed_document_ids:
        return []
    rows = session.execute(
        select(DocumentChunk, Document)
        .join(Document, Document.document_id == DocumentChunk.document_id)
        .where(DocumentChunk.document_id.in_(allowed_document_ids))
    ).all()
    records: list[dict[str, Any]] = []
    for chunk, document in rows:
        if document.superseded and not include_superseded:
            continue
        if chunk.prompt_injection_suspected and not include_injection_chunks:
            continue
        records.append(
            {
                "chunk_id": chunk.chunk_id,
                "document_id": document.document_id,
                "text": chunk.text,
                "superseded": document.superseded,
                "reporting_date": document.reporting_date.isoformat(),
                "prompt_injection_suspected": chunk.prompt_injection_suspected,
                "sensitivity": chunk.sensitivity,
                "title": document.title,
                "locator": chunk.locator,
            }
        )
    if not records:
        return []
    allowed = {record["document_id"] for record in records}
    keyword = BM25Index(records).search(query, allowed_document_ids=allowed, k=k)
    vectors = [embed_text(record["text"]) for record in records]
    import numpy as np

    semantic = NumpyVectorIndex(records, np.array(vectors, dtype=np.float32)).search(
        query, allowed_document_ids=allowed, k=k
    )
    return FeatureReranker().rerank(query, keyword + semantic, k)
