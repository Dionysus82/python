"""CSV and plain-text extraction."""

from __future__ import annotations

import csv
import io

from app.parsers.base import ParsedChunk, ParsedDocument, mark_injection


def parse_csv(data: bytes) -> ParsedDocument:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return ParsedDocument(text="", corrupt=True, error=str(exc))
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    chunks = []
    if rows:
        header = rows[0]
        for index, row in enumerate(rows, start=1):
            body = " | ".join(
                f"{header[col] if col < len(header) else col}={value}" for col, value in enumerate(row)
            )
            chunks.append(
                ParsedChunk(text=f"CSV row {index}: {body}", locator={"row": index, "sheet": "CSV"})
            )
    parsed = ParsedDocument(text=text, chunks=chunks, sheet_metadata={"format": "csv"})
    mark_injection(parsed.chunks)
    return parsed


def parse_txt(data: bytes) -> ParsedDocument:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return ParsedDocument(text="", corrupt=True, error=str(exc))
    chunks = []
    for index, paragraph in enumerate([part.strip() for part in text.split("\n\n") if part.strip()], start=1):
        chunks.append(ParsedChunk(text=paragraph, locator={"paragraph": index, "section": "Text"}))
    if not chunks and text.strip():
        chunks.append(ParsedChunk(text=text.strip(), locator={"paragraph": 1, "section": "Text"}))
    parsed = ParsedDocument(text=text, chunks=chunks)
    mark_injection(parsed.chunks)
    return parsed
