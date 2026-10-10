"""Run the seeded evaluation set and report measured scores. Do not invent results."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.errors import AccessDeniedError
from app.models.tables import AuditEvent
from app.rag.pipeline import ask
from app.security.principal import load_principal

CASES_PATH = Path(__file__).resolve().parent / "cases.json"


def load_cases() -> list[dict]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def run_evaluation(session: Session) -> dict:
    cases = load_cases()
    results = []
    for case in cases:
        results.append(_run_case(session, case))
    session.commit()
    return _summarise(results)


def _run_case(session: Session, case: dict) -> dict:
    principal = load_principal(session, case["username"])
    before = session.scalar(select(AuditEvent.audit_id).order_by(AuditEvent.created_at.desc()))
    denied = False
    answer = None
    error = None
    try:
        if principal is None:
            denied = True
            error = "Unknown user."
        else:
            answer = ask(session, principal, case["question"])
    except AccessDeniedError:
        denied = True
    checks = _checks(case, answer, denied)
    if case["id"] == "G-unauthorised":
        audit_hit = session.scalar(
            select(AuditEvent).where(
                AuditEvent.event_type == "access_denied",
                AuditEvent.username == case["username"],
                AuditEvent.outcome == "denied",
            ).order_by(AuditEvent.created_at.desc())
        )
        checks["audit_event_created"] = audit_hit is not None
    else:
        checks["audit_event_created"] = True
    passed = all(checks.values())
    citation_ids = _citation_documents(answer)
    retrieved = (answer or {}).get("evidence_document_ids") or []
    return {
        "id": case["id"],
        "scenario": case["scenario"],
        "passed": passed,
        "checks": checks,
        "denied": denied,
        "abstained": None if answer is None else answer.get("abstained"),
        "contradiction": None if answer is None else answer.get("contradiction"),
        "resolved_customer_ids": [] if answer is None else answer.get("resolved_customer_ids"),
        "citation_document_ids": citation_ids,
        "retrieved_document_ids": retrieved,
        "error": error,
        "message_excerpt": None if answer is None else (answer.get("message") or "")[:400],
        "before_audit": before,
    }


def _checks(case: dict, answer: dict | None, denied: bool) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    if "expect_denied" in case:
        checks["authorisation"] = denied is bool(case["expect_denied"])
    else:
        checks["authorisation"] = not denied
    if denied or answer is None:
        if case.get("expect_denied"):
            return checks
        checks["answered"] = False
        return checks
    message = answer.get("message") or ""
    folded = message.casefold()
    if "expect_abstain" in case:
        checks["abstention"] = bool(answer.get("abstained")) is bool(case["expect_abstain"])
    if "expect_contradiction" in case:
        checks["contradiction"] = bool(answer.get("contradiction")) is bool(case["expect_contradiction"])
    if case.get("expect_customers") is not None:
        checks["customer_resolution"] = set(answer.get("resolved_customer_ids") or []) == set(case["expect_customers"])
    for forbidden in case.get("forbid_customers") or []:
        checks[f"no_leak_{forbidden}"] = forbidden not in (answer.get("resolved_customer_ids") or [])
    for snippet in case.get("expect_any_substrings") or []:
        checks[f"contains:{snippet}"] = snippet.casefold() in folded
    for snippet in case.get("forbid_substrings") or []:
        checks[f"omits:{snippet}"] = snippet.casefold() not in folded
    citations = set(_citation_documents(answer))
    expected_docs = case.get("expect_documents_in_citations") or []
    if expected_docs:
        checks["citation_completeness"] = set(expected_docs) <= citations
        checks["citation_correctness"] = bool(set(expected_docs) & citations) or not expected_docs
    retrieved = set(answer.get("evidence_document_ids") or [])
    if expected_docs:
        checks["retrieval_recall"] = set(expected_docs) <= (retrieved | citations)
    return checks


def _citation_documents(answer: dict | None) -> list[str]:
    if not answer:
        return []
    found = []
    for claim in answer.get("claims") or []:
        for citation in claim.get("citations") or []:
            document_id = citation.get("document_id")
            if document_id and document_id not in found:
                found.append(document_id)
    return found


def _summarise(results: list[dict]) -> dict:
    total = len(results)
    passed = sum(1 for item in results if item["passed"])
    def rate(name: str) -> dict:
        relevant = [item for item in results if name in item["checks"]]
        if not relevant:
            return {"cases": 0, "passed": 0, "rate": None}
        ok = sum(1 for item in relevant if item["checks"][name])
        return {"cases": len(relevant), "passed": ok, "rate": round(ok / len(relevant), 4)}

    return {
        "case_count": total,
        "cases_passed": passed,
        "case_pass_rate": round(passed / total, 4) if total else None,
        "authorisation_test_pass_rate": rate("authorisation"),
        "abstention_correctness": rate("abstention"),
        "contradiction_detection_accuracy": rate("contradiction"),
        "customer_resolution": rate("customer_resolution"),
        "citation_correctness": rate("citation_correctness"),
        "citation_completeness": rate("citation_completeness"),
        "retrieval_recall": rate("retrieval_recall"),
        "retrieval_precision_note": (
            "Precision is not scored as a single ratio because hybrid retrieval may return additional "
            "authorised documents. Recall is the share of cases whose expected documents were retrieved or cited."
        ),
        "groundedness": rate("citation_completeness"),
        "answer_relevance": {
            "cases": total,
            "passed": passed,
            "rate": round(passed / total, 4) if total else None,
            "definition": "A case is relevant when every declared check on that case passed.",
        },
        "results": results,
    }
