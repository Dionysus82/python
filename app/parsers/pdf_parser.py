"""PDF text extraction with page numbers and block bounding boxes where available."""

from __future__ import annotations

import pymupdf

from app.parsers.base import ParsedChunk, ParsedDocument, mark_injection


def parse_pdf(data: bytes) -> ParsedDocument:
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 - corrupt files are quarantined, not raised
        return ParsedDocument(text="", corrupt=True, error=str(exc))
    if document.needs_pass or document.is_encrypted:
        document.close()
        return ParsedDocument(text="", password_protected=True, error="Password-protected PDF.")
    chunks: list[ParsedChunk] = []
    pages: list[str] = []
    for page_index in range(document.page_count):
        page = document[page_index]
        text = page.get_text("text").strip()
        blocks = []
        try:
            for block in page.get_text("dict").get("blocks", []):
                if block.get("type") != 0:
                    continue
                bbox = block.get("bbox")
                if bbox:
                    blocks.append([round(float(value), 2) for value in bbox])
        except Exception:
            blocks = []
        pages.append(text)
        if text:
            chunks.append(
                ParsedChunk(
                    text=text,
                    locator={"page": page_index + 1, "bounding_boxes": blocks[:8], "section": None},
                )
            )
    page_count = document.page_count
    document.close()
    parsed = ParsedDocument(text="\n".join(pages), chunks=chunks, page_count=page_count)
    mark_injection(parsed.chunks)
    return parsed
