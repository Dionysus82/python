"""Parser result shared by PDF, Word, Excel, CSV and text."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.security.injection import find_injection


@dataclass
class ParsedChunk:
    text: str
    locator: dict
    prompt_injection_suspected: bool = False


@dataclass
class ParsedDocument:
    text: str
    chunks: list[ParsedChunk] = field(default_factory=list)
    page_count: int | None = None
    sheet_metadata: dict | None = None
    section_metadata: dict | None = None
    password_protected: bool = False
    corrupt: bool = False
    error: str | None = None


def mark_injection(chunks: list[ParsedChunk]) -> bool:
    suspected = False
    for chunk in chunks:
        if find_injection(chunk.text):
            chunk.prompt_injection_suspected = True
            suspected = True
    return suspected
