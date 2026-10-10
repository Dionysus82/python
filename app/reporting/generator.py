"""Draft customer risk summaries in HTML, PDF and JSON.

Reports restate authorised records. They are not approvals.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy.orm import Session

from app.audit.service import write_audit
from app.authorisation.service import allowed_customer_ids, visible_document_ids
from app.config import get_settings
from app.domain.banner import (
    FICTIONAL_BANK,
    FICTIONAL_BANK_NOTICE,
    HUMAN_REVIEW_NOTICE,
    REGULATORY_REVIEW_NOTICE,
    SYNTHETIC_BANNER,
)
from app.domain.dates import format_date, format_timestamp, utcnow
from app.domain.errors import AccessDeniedError, SeparationOfDutiesError
from app.domain.money import format_money
from app.models.tables import GeneratedReport, ReportReview
from app.rag.claims import build_customer_claims
from app.security.principal import Principal
from app.services.analytics import customer_360
from app.services.serialise import jsonable

TEMPLATE_DIR = Path(__file__).resolve().parent
APPROVAL = "Draft — human review required. This is not a bank approval."


def generate_customer_report(session: Session, principal: Principal, customer_id: str) -> dict:
    if not principal.can("report.generate"):
        raise AccessDeniedError("This role cannot generate reports.")
    if principal.read_only:
        raise AccessDeniedError("This role is read-only.")
    view = customer_360(session, principal, customer_id)
    allowed = allowed_customer_ids(session, principal)
    visible = visible_document_ids(session, principal, allowed)
    claims = build_customer_claims(session, principal, customer_id, visible, historical=True)
    report_id = f"RPT-{uuid.uuid4().hex[:12]}"
    generated_at = utcnow()
    sections = _sections(view, claims)
    payload = {
        "report_id": report_id,
        "classification": "Hackathon draft — synthetic",
        "banner": SYNTHETIC_BANNER,
        "bank": FICTIONAL_BANK,
        "bank_notice": FICTIONAL_BANK_NOTICE,
        "title": f"Customer and Counterparty Risk Summary — {view['profile']['legal_name']}",
        "customer_id": customer_id,
        "generated_at": format_timestamp(generated_at),
        "generated_by": principal.username,
        "approval_status": APPROVAL,
        "human_review": HUMAN_REVIEW_NOTICE,
        "regulatory": REGULATORY_REVIEW_NOTICE,
        "model_commentary_disclaimer": (
            "Narrative text organises cited records. It is model-assisted drafting only when the kill switch is off. "
            "Numeric scores come from deterministic Python rules."
        ),
        "sections": sections,
        "concern_score": view["concern_score"],
    }
    html = _html(payload)
    pdf = _pdf(payload)
    settings = get_settings()
    settings.report_dir.mkdir(parents=True, exist_ok=True)
    html_key = f"{report_id}.html"
    pdf_key = f"{report_id}.pdf"
    (settings.report_dir / html_key).write_text(html, encoding="utf-8")
    (settings.report_dir / pdf_key).write_bytes(pdf)
    (settings.report_dir / f"{report_id}.json").write_text(json.dumps(jsonable(payload), indent=2), encoding="utf-8")
    session.add(
        GeneratedReport(
            report_id=report_id,
            customer_id=customer_id,
            generated_by=principal.username,
            generated_at=generated_at,
            approval_status=APPROVAL,
            html_key=html_key,
            pdf_key=pdf_key,
            payload=jsonable(payload),
        )
    )
    write_audit(
        session,
        event_type="report_generated",
        outcome="ok",
        detail="Draft customer risk summary generated.",
        principal=principal,
        customer_id=customer_id,
        correlation_id=report_id,
    )
    return jsonable(payload)


def load_report_bytes(session: Session, principal: Principal, report_id: str, kind: str) -> tuple[bytes, str]:
    report = session.get(GeneratedReport, report_id)
    if report is None or report.customer_id not in allowed_customer_ids(session, principal):
        raise AccessDeniedError("The requested customer is outside your authorised portfolio or does not exist.")
    if not principal.can("document.download") and not principal.can("report.generate"):
        raise AccessDeniedError("This role cannot download reports.")
    key = report.html_key if kind == "html" else report.pdf_key
    if not key:
        raise AccessDeniedError("The report file is not available.")
    path = get_settings().report_dir / key
    media = "text/html" if kind == "html" else "application/pdf"
    write_audit(
        session,
        event_type="report_download",
        outcome="ok",
        detail=f"Downloaded {kind}.",
        principal=principal,
        customer_id=report.customer_id,
        correlation_id=report_id,
    )
    return path.read_bytes(), media


def record_review(session: Session, principal: Principal, report_id: str, note: str) -> dict:
    if not principal.can("report.review"):
        raise AccessDeniedError("This role cannot record a human review.")
    report = session.get(GeneratedReport, report_id)
    if report is None or report.customer_id not in allowed_customer_ids(session, principal):
        raise AccessDeniedError("The requested customer is outside your authorised portfolio or does not exist.")
    if report.generated_by == principal.username:
        raise SeparationOfDutiesError("The author of a draft cannot record the human review of that draft.")
    status = "Human review noted. The document remains a draft and is not a bank approval."
    session.add(
        ReportReview(
            review_id=f"RR-{uuid.uuid4().hex[:12]}",
            report_id=report_id,
            reviewer=principal.username,
            reviewed_at=utcnow(),
            note=note[:1000],
            status=status,
        )
    )
    report.approval_status = status
    write_audit(
        session,
        event_type="report_review",
        outcome="ok",
        detail=status,
        principal=principal,
        customer_id=report.customer_id,
        correlation_id=report_id,
    )
    return {"report_id": report_id, "approval_status": status}


def _sections(view: dict, claims: list[dict]) -> list[dict]:
    profile = view["profile"]
    position = view["position"]
    def facts_for(*keys: str, types: set[str] | None = None) -> list[dict]:
        found = []
        for claim in claims:
            family = claim["metric_key"].split(":", 1)[0]
            if keys and family not in keys and claim["metric_key"] not in keys:
                continue
            if types and claim["claim_type"] not in types:
                continue
            found.append(_fact(claim))
        return found

    facility_rows = []
    for row in view["facilities"]:
        facility_rows.append(
            [
                row["facility_id"],
                row["name"],
                row["currency"],
                _money(row["committed_limit"], row["currency"]),
                _money(row["drawn"], row["currency"]),
                _money(row["hkd_drawn"], "HKD"),
                row["limit_status"],
                str(row["data_quality"]),
                format_date(row["as_of_date"]),
            ]
        )
    return [
        {
            "title": "1. Report classification and synthetic-data disclaimer",
            "narrative": SYNTHETIC_BANNER + " " + FICTIONAL_BANK_NOTICE,
            "facts": [],
            "rows": [],
            "headers": [],
        },
        {
            "title": "2. Executive summary",
            "narrative": "The points below restate cited records and deterministic calculations.",
            "facts": facts_for("total_exposure", "concern_score", "risk_trend", "internal_credit_rating"),
            "rows": [],
            "headers": [],
        },
        {
            "title": "3. Customer and group overview",
            "narrative": profile["business_summary"],
            "facts": [],
            "headers": ["Field", "Value"],
            "rows": [
                ["Customer", profile["legal_name"]],
                ["Customer ID", profile["customer_id"]],
                ["Group", f"{profile['group_name']} ({profile['group_id']})"],
                ["Industry", profile["industry"]],
                ["Jurisdiction", profile["jurisdiction"]],
                ["Relationship manager", profile["relationship_manager"]],
                ["Onboarding", profile["onboarding_status"]],
                ["Customer risk classification", profile["customer_risk_classification"]],
            ],
        },
        {
            "title": "4. Business relationship",
            "narrative": None,
            "facts": facts_for("business_relationship", "portfolio_membership"),
            "rows": [[item["code"], item["name"]] for item in view["products"]],
            "headers": ["Product", "Name"] if view["products"] else [],
        },
        {
            "title": "5. Facilities, limits and exposure",
            "narrative": (
                f"Authorised total exposure { _money(position['total_exposure_hkd'], 'HKD') }. "
                "Original currencies are converted with the stored rate card. Unresolved facilities are excluded."
            ),
            "facts": facts_for("drawn_exposure", "total_exposure", "contingent_exposure", "ccr"),
            "headers": ["Facility", "Name", "Ccy", "Limit", "Drawn", "HKD drawn", "Limit status", "Quality", "As at"],
            "rows": facility_rows,
        },
        {"title": "6. Consolidated risk assessment", "narrative": profile.get("data_freshness"), "facts": facts_for("concern_score", "risk_trend"), "rows": [], "headers": []},
        {"title": "7. Credit-risk assessment", "narrative": None, "facts": facts_for("internal_credit_rating", "expected_loss", "probability_of_default"), "rows": [], "headers": []},
        {"title": "8. Liquidity-risk assessment", "narrative": "Liquidity observations are not a statement of credit default.", "facts": facts_for("liquidity_ratio", "cash_reserves", "deposit_balance"), "rows": [], "headers": []},
        {"title": "9. Market and interest-rate-risk assessment", "narrative": None, "facts": facts_for("ccr", "market_risk", "interest_rate"), "rows": [], "headers": []},
        {"title": "10. Operational-risk assessment", "narrative": None, "facts": [ _fact(c) for c in claims if "operational" in c.get("tags", []) or c["metric_key"].startswith("operational")], "rows": [], "headers": []},
        {"title": "11. AML and financial-crime indicators", "narrative": view["aml_notice"], "facts": facts_for("aml_risk", "review"), "rows": [], "headers": []},
        {"title": "12. Country, industry and concentration risk", "narrative": f"Industry {profile['industry']}; jurisdiction {profile['jurisdiction']}.", "facts": facts_for("portfolio_membership"), "rows": [], "headers": []},
        {"title": "13. Legal, reputation and strategic risk", "narrative": None, "facts": [], "rows": [[row["domain"], row["severity"], row["statement"]] for row in view["qualitative"]], "headers": ["Domain", "Severity", "Statement"] if view["qualitative"] else []},
        {"title": "14. Climate-risk indicators", "narrative": None, "facts": facts_for("climate_indicator"), "rows": [], "headers": []},
        {"title": "15. Collateral and risk mitigants", "narrative": "Collateral is a mitigant. It does not eliminate the underlying risk.", "facts": facts_for("eligible_collateral", "collateral_coverage"), "rows": [], "headers": []},
        {"title": "16. Key changes since the previous period", "narrative": view["risk_trend"], "facts": facts_for("risk_trend"), "rows": [], "headers": []},
        {"title": "17. Early-warning indicators", "narrative": None, "facts": facts_for("early_warning"), "rows": [], "headers": []},
        {"title": "18. Limit and covenant breaches", "narrative": None, "facts": facts_for("utilisation_pct", "covenant_status", "limit_status"), "rows": [], "headers": []},
        {"title": "19. Watchlist information", "narrative": profile["watchlist_status"], "facts": facts_for("watchlist_status"), "rows": [], "headers": []},
        {"title": "20. Overdue reviews and outstanding actions", "narrative": None, "facts": facts_for("annual_review_status", "management_action", "review"), "rows": [], "headers": []},
        {"title": "21. Data-quality and freshness warnings", "narrative": profile["data_freshness"], "facts": [item for item in (_fact(c) for c in claims) if c_is_warning(item)], "rows": [], "headers": []},
        {"title": "22. Evidence and source references", "narrative": "Every material fact above carries a citation. Select a document link to open the source viewer.", "facts": [], "rows": [[row["document_id"], row["title"], format_date(row["reporting_date"]), f"v{row['version']}", "Superseded" if row["superseded"] else "Current"] for row in view["documents"]], "headers": ["Document", "Title", "Reporting date", "Version", "Status"] if view["documents"] else []},
        {"title": "23. Model-generated commentary disclaimer", "narrative": "Commentary, where shown, is labelled and does not create numeric scores.", "facts": [], "rows": [], "headers": []},
        {"title": "24. Generation timestamp", "narrative": "The timestamp is recorded in Asia/Hong_Kong when the draft is stored.", "facts": [], "rows": [], "headers": []},
        {"title": "25. Approval status", "narrative": APPROVAL, "facts": [], "rows": [], "headers": []},
    ]


def c_is_warning(fact: dict) -> bool:
    return fact["kind"] in {"Unresolved contradiction", "Missing evidence"}


def _fact(claim: dict) -> dict:
    from app.citations.format import citation_detail

    kind = {
        "sourced_fact": "Sourced fact",
        "calculation": "Deterministic calculation",
        "rule": "Rule-based classification",
        "contradiction": "Unresolved contradiction",
        "missing": "Missing evidence",
        "model_summary": "Model-generated summary",
    }.get(claim["claim_type"], "Note")
    return {
        "kind": kind,
        "text": claim["text"],
        "citations": [citation_detail(item) for item in claim.get("citations", [])],
    }


def _money(amount, currency: str) -> str:
    return format_money(amount, currency)


def _html(payload: dict) -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape(["html"]))
    return env.get_template("template.html").render(**payload)


def _pdf(payload: dict) -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm)
    styles = getSampleStyleSheet()
    banner = ParagraphStyle("banner", parent=styles["Normal"], textColor="white", backColor="#7a1f1f", fontSize=8, leading=11)
    heading = ParagraphStyle("h", parent=styles["Heading2"], textColor="#0b3a5b", spaceBefore=10, spaceAfter=4)
    body = styles["Normal"]
    story = [
        Paragraph(payload["banner"], banner),
        Spacer(1, 8),
        Paragraph(payload["title"], styles["Title"]),
        Paragraph(payload["bank_notice"], body),
        Paragraph(f"Generated {payload['generated_at']} · {payload['approval_status']}", body),
        Paragraph(payload["human_review"], body),
    ]
    for section in payload["sections"]:
        story.append(Paragraph(section["title"], heading))
        if section.get("narrative"):
            story.append(Paragraph(_escape(section["narrative"]), body))
        for fact in section.get("facts") or []:
            story.append(Paragraph(f"<b>{_escape(fact['kind'])}.</b> {_escape(fact['text'])}", body))
            for citation in fact["citations"]:
                story.append(Paragraph(_escape(citation["label"]), body))
        if section.get("rows"):
            for row in section["rows"][:40]:
                story.append(Paragraph(_escape(" | ".join(str(cell) for cell in row)), body))
    doc.build(story)
    return buffer.getvalue()


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
