"""Claim-level citation display."""

from __future__ import annotations

from app.domain.dates import format_date, format_timestamp


def citation_label(citation: dict) -> str:
    if citation.get("kind") == "document":
        parts = [citation.get("source_title") or citation.get("title") or "Document"]
        if citation.get("page"):
            parts.append(f"page {citation['page']}")
        if citation.get("sheet"):
            parts.append(f"sheet {citation['sheet']}")
        if citation.get("cell_range"):
            parts.append(f"cells {citation['cell_range']}")
        if citation.get("section"):
            parts.append(f"section {citation['section']}")
        if citation.get("paragraph"):
            parts.append(f"paragraph {citation['paragraph']}")
        if citation.get("version"):
            parts.append(f"version {citation['version']}")
        if citation.get("reporting_date"):
            parts.append(f"reporting date {format_date(citation['reporting_date'])}")
        return "[" + ", ".join(str(part) for part in parts if part) + "]"
    hkd = citation.get("hkd_equivalent")
    return (
        f"[{citation.get('source_system') or citation.get('record_table')}, "
        f"record {citation.get('record_id')}, as at {format_date(citation.get('as_of_date'))}, "
        f"calculated {format_timestamp(citation.get('calculated_at'))}, "
        f"unit {citation.get('unit') or 'n/a'}, currency {citation.get('currency') or 'n/a'}, "
        f"HKD equivalent {hkd if hkd is not None else 'n/a'}]"
    )


def citation_detail(citation: dict) -> dict:
    """All required citation fields, with nulls preserved when a format does not use them."""
    return {
        "label": citation_label(citation),
        "source_title": citation.get("source_title"),
        "original_filename": citation.get("original_filename"),
        "document_id": citation.get("document_id"),
        "customer_id": citation.get("customer_id"),
        "risk_domain": citation.get("risk_domain"),
        "reporting_date": format_date(citation.get("reporting_date")) if citation.get("reporting_date") else None,
        "document_version": citation.get("version"),
        "authoring_function": citation.get("authoring_function"),
        "page": citation.get("page"),
        "sheet": citation.get("sheet"),
        "cell_range": citation.get("cell_range"),
        "section": citation.get("section"),
        "paragraph": citation.get("paragraph"),
        "record_table": citation.get("record_table"),
        "record_id": citation.get("record_id"),
        "as_of_date": format_date(citation.get("as_of_date")) if citation.get("as_of_date") else None,
        "calculated_at": format_timestamp(citation.get("calculated_at")) if citation.get("calculated_at") else None,
        "unit": citation.get("unit"),
        "currency": citation.get("currency"),
        "hkd_equivalent": citation.get("hkd_equivalent"),
        "source_system": citation.get("source_system"),
        "viewer_route": citation.get("viewer_route"),
        "excerpt": citation.get("excerpt"),
    }
