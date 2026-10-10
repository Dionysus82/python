"""Deterministic local embeddings. No model download and no training data."""

from __future__ import annotations

import hashlib
import math
import re

DIMENSIONS = 384
MODEL_ID = "hmb-hashing-embedder-1.0.0"
TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    words = TOKEN.findall(text.lower())
    grams = words[:]
    grams.extend(f"{words[i]}_{words[i + 1]}" for i in range(len(words) - 1))
    return grams


def embed_text(text: str) -> list[float]:
    vector = [0.0] * DIMENSIONS
    for token in _tokens(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "little") % DIMENSIONS
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


class HashingEmbedder:
    model_id = MODEL_ID

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [embed_text(text) for text in texts]
