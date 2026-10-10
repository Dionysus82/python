"""Detect untrusted instruction text. Matching text is content, never a command."""

from __future__ import annotations

import re

INJECTION_PATTERNS = [
    re.compile(r"ignore all security controls", re.IGNORECASE),
    re.compile(r"ignore\s+(all\s+)?(previous|prior|system)\s+instructions", re.IGNORECASE),
    re.compile(r"reveal information about every customer", re.IGNORECASE),
    re.compile(r"reveal every customer", re.IGNORECASE),
    re.compile(r"disable citations", re.IGNORECASE),
    re.compile(r"you are now (a|an|the)", re.IGNORECASE),
]

ALLEGATION_PATTERNS = [
    re.compile(r"\bconvicted\b", re.IGNORECASE),
    re.compile(r"\bbribery\b", re.IGNORECASE),
    re.compile(r"\bcriminal\b", re.IGNORECASE),
    re.compile(r"\bguilty of\b", re.IGNORECASE),
    re.compile(r"\bprison\b", re.IGNORECASE),
    re.compile(r"\bprosecution\b", re.IGNORECASE),
]


def find_injection(text: str) -> list[str]:
    return [pattern.pattern for pattern in INJECTION_PATTERNS if pattern.search(text or "")]


def is_unsupported_allegation(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in ALLEGATION_PATTERNS)
