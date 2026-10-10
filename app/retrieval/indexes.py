"""Keyword and vector indexes that refuse an unscoped query."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from app.domain.errors import AuthorisationError
from app.domain.protocols import require_scope
from app.embeddings.hashing import embed_text

TOKEN = __import__("re").compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return TOKEN.findall(text.lower())


class BM25Index:
    def __init__(self, records: list[dict]) -> None:
        self.records = records
        corpus = [_tokenize(record["text"]) for record in records]
        self.model = BM25Okapi(corpus) if corpus else None

    def search(self, query: str, *, allowed_document_ids: set[str] | None, k: int) -> list[dict]:
        allowed = require_scope(allowed_document_ids)
        if not self.model or not allowed:
            return []
        indices = [
            index
            for index, record in enumerate(self.records)
            if record["document_id"] in allowed
        ]
        if not indices:
            return []
        scores = self.model.get_batch_scores(_tokenize(query), indices)
        ranked = sorted(zip(scores, indices, strict=True), key=lambda item: item[0], reverse=True)
        hits = []
        for score, index in ranked[:k]:
            if score <= 0:
                continue
            record = dict(self.records[index])
            record["score"] = float(score)
            record["retriever"] = "bm25"
            hits.append(record)
        return hits


class NumpyVectorIndex:
    def __init__(self, records: list[dict], vectors: np.ndarray | None) -> None:
        self.records = records
        self.vectors = vectors

    def search(self, query: str, *, allowed_document_ids: set[str] | None, k: int) -> list[dict]:
        allowed = require_scope(allowed_document_ids)
        if self.vectors is None or not len(self.records) or not allowed:
            return []
        query_vector = np.array(embed_text(query), dtype=np.float32)
        hits = []
        for index, record in enumerate(self.records):
            if record["document_id"] not in allowed:
                continue
            score = float(np.dot(self.vectors[index], query_vector))
            if score <= 0:
                continue
            item = dict(record)
            item["score"] = score
            item["retriever"] = "vector"
            hits.append(item)
        hits.sort(key=lambda item: item["score"], reverse=True)
        return hits[:k]

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "records.json").write_text(json.dumps(self.records), encoding="utf-8")
        if self.vectors is not None:
            np.save(directory / "vectors.npy", self.vectors)

    @classmethod
    def load(cls, directory: Path) -> NumpyVectorIndex:
        records = json.loads((directory / "records.json").read_text(encoding="utf-8"))
        path = directory / "vectors.npy"
        vectors = np.load(path) if path.exists() else None
        return cls(records, vectors)


def build_vector_matrix(records: list[dict]) -> np.ndarray:
    if not records:
        return np.zeros((0, 384), dtype=np.float32)
    return np.array([embed_text(record["text"]) for record in records], dtype=np.float32)


class FeatureReranker:
    """Deterministic reranker. A cross-encoder can replace this behind the same method."""

    def rerank(self, query: str, hits: list[dict], k: int) -> list[dict]:
        if hits is None:
            raise AuthorisationError("Reranking requires an already scoped hit list.")
        tokens = set(_tokenize(query))
        ranked = []
        for hit in hits:
            lexical = len(tokens & set(_tokenize(hit["text"]))) / (len(tokens) or 1)
            current_bonus = 0.15 if not hit.get("superseded") else 0.0
            injection_penalty = 0.5 if hit.get("prompt_injection_suspected") else 0.0
            score = float(hit.get("score", 0)) + lexical + current_bonus - injection_penalty
            item = dict(hit)
            item["rerank_score"] = score
            ranked.append(item)
        ranked.sort(key=lambda item: item["rerank_score"], reverse=True)
        deduped = []
        seen = set()
        for item in ranked:
            if item["chunk_id"] in seen:
                continue
            seen.add(item["chunk_id"])
            deduped.append(item)
        return deduped[:k]
