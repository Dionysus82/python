"""Interfaces that keep business rules independent of providers."""

from __future__ import annotations

from typing import Protocol

from app.domain.errors import AuthorisationError


class DocumentStore(Protocol):
    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...


class DocumentParser(Protocol):
    def parse(self, data: bytes, filename: str) -> object: ...


class EmbeddingProvider(Protocol):
    model_id: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class VectorStore(Protocol):
    def upsert(self, ids: list[str], vectors: list[list[float]], metadata: list[dict]) -> None: ...

    def search(
        self, vector: list[float], *, allowed_document_ids: set[str], k: int
    ) -> list[dict]: ...


class KeywordRetriever(Protocol):
    def search(self, query: str, *, allowed_document_ids: set[str], k: int) -> list[dict]: ...


class Reranker(Protocol):
    def rerank(self, query: str, hits: list[dict], k: int) -> list[dict]: ...


class LLMProvider(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> str: ...


class CitationResolver(Protocol):
    def display(self, citation: object) -> str: ...


class GroundingValidator(Protocol):
    def validate(self, answer: object, principal: object) -> object: ...


def require_scope(allowed_document_ids: set[str] | None) -> set[str]:
    if allowed_document_ids is None:
        raise AuthorisationError("Retrieval requires an authorisation scope before search.")
    return allowed_document_ids
