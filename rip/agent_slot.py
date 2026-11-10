"""Slot for a Gemini agent connected later through Antigravity.

The Knowledge assistant calls ask(). Until RIP_AGENT_URL is set, ask()
returns None and the page keeps the local demonstration answers.

When the agent built in Google Enterprise is ready, set these on the
server. Do not write the key into this file or the repository.

    RIP_AGENT_URL   HTTPS endpoint Antigravity exposes for that agent
    RIP_AGENT_KEY   bearer token, if the endpoint requires one

This page sends one JSON POST:

    {
      "question": "...",
      "as_of": "30 November 2026",
      "checked_dates": ["2026-11-30"],
      "borrower": {"customer_id": "BOR-AGHL", "legal_name": "...", ...}
    }

It expects JSON back:

    {"answer": "...", "sources": [{"title": "", "locator": "", "passage": ""}]}
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

TIMEOUT_SECONDS = 8
_LAST_ERROR = ""


def configured() -> bool:
    return bool(os.environ.get("RIP_AGENT_URL", "").strip())


def status() -> str:
    if not configured():
        return "Not connected. This page is using the local demonstration."
    if _LAST_ERROR:
        return "The agent endpoint is set, and the last call did not return an answer. The local demonstration is shown instead."
    return "Connected. Questions on this page are sent to the Gemini agent."


def ask(row: dict, question: str, dates: list[str], as_of: str) -> tuple[str, list[dict]] | None:
    global _LAST_ERROR
    url = os.environ.get("RIP_AGENT_URL", "").strip()
    if not url:
        _LAST_ERROR = ""
        return None
    payload = {
        "question": question,
        "as_of": as_of,
        "checked_dates": dates,
        "borrower": {
            "customer_id": row.get("customer_id"),
            "legal_name": row.get("legal_name"),
            "industry": row.get("industry"),
            "rating": row.get("rating"),
            "prior_rating": row.get("prior_rating"),
            "stage": row.get("stage"),
            "drawn_hkd": row.get("drawn_hkd"),
            "ecl_hkd": row.get("ecl_hkd"),
            "dpd": row.get("dpd"),
            "collateral_type": row.get("collateral_type"),
            "collateral_hkd": row.get("collateral_hkd"),
            "rm": row.get("rm"),
        },
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    key = os.environ.get("RIP_AGENT_KEY", "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
        parsed = json.loads(raw)
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        _LAST_ERROR = "unavailable"
        return None
    answer = parsed.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        _LAST_ERROR = "empty"
        return None
    sources = []
    for item in parsed.get("sources") or []:
        if not isinstance(item, dict):
            continue
        sources.append(
            {
                "title": str(item.get("title") or "Gemini agent"),
                "locator": str(item.get("locator") or "Antigravity"),
                "passage": str(item.get("passage") or ""),
            }
        )
    _LAST_ERROR = ""
    return answer.strip(), sources
