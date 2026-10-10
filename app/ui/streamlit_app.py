"""Management interface for the Harbour Meridian hackathon profile.

Domain rules live in services. This module only presents them.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.database import get_session_factory
from app.domain.banner import FICTIONAL_BANK, FICTIONAL_BANK_NOTICE, SYNTHETIC_BANNER
from app.domain.dates import format_date
from app.domain.errors import AccessDeniedError, IngestionError, SeparationOfDutiesError
from app.domain.money import format_money
from app.evaluation.runner import run_evaluation
from app.rag.pipeline import ask
from app.reporting.generator import generate_customer_report, record_review
from app.security.principal import load_principal
from app.security.tokens import read_token
from app.services import analytics, sources, uploads
from app.services.serialise import jsonable

st.set_page_config(page_title="Harbour Meridian Risk Intelligence", layout="wide")
st.markdown(
    """
    <style>
      .banner {background:#7a1f1f;color:#fff;padding:10px 14px;font-weight:700;border-radius:4px;}
      .sub {color:#334;font-size:0.95rem;margin-top:0.4rem;}
      .card {background:#f7fafc;border:1px solid #d5dde5;padding:10px 12px;border-radius:4px;margin-bottom:8px;}
    </style>
    """,
    unsafe_allow_html=True,
)

PAGES = [
    "Management Dashboard",
    "Customer and Counterparty Search",
    "Customer 360",
    "Group 360",
    "Ask Risk Intelligence",
    "Customer Risk Report Generator",
    "Portfolio Risk View",
    "Facilities and Exposure",
    "Limits and Covenants",
    "Collateral",
    "Early-Warning Indicators",
    "AML and Financial-Crime Indicators",
    "Trusted Documents",
    "Upload and Ingestion",
    "Data Quality and Freshness",
    "RAG Evaluation",
    "AI Governance",
    "Audit Activity",
    "Administration",
]


def banner() -> None:
    st.markdown(f'<div class="banner">{SYNTHETIC_BANNER}</div>', unsafe_allow_html=True)
    st.caption(FICTIONAL_BANK_NOTICE)


def session():
    return get_session_factory()()


def current_principal(db):
    token = st.session_state.get("token")
    if not token:
        return None
    username = read_token(token)
    if not username:
        return None
    return load_principal(db, username)


def run(action):
    db = session()
    try:
        principal = current_principal(db)
        if principal is None:
            st.session_state.pop("token", None)
            st.warning("Please sign in again.")
            return None
        result = action(db, principal)
        db.commit()
        return result
    except AccessDeniedError as exc:
        db.commit()
        st.error(str(exc))
        return None
    except (IngestionError, SeparationOfDutiesError) as exc:
        db.commit()
        st.error(str(exc))
        return None
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def login() -> None:
    banner()
    st.title(FICTIONAL_BANK)
    st.subheader("Risk Intelligence Platform")
    st.write("Synthetic demonstration accounts share one password: `Harbour-Demo-2026`.")
    accounts = [
        "cro.shum — Chief risk officer",
        "rm.chan — Relationship manager, corporate portfolio only",
        "fcc.lam — Financial-crime compliance analyst",
        "cra.ho — Credit-risk analyst",
        "ia.fung — Internal auditor, read-only",
        "admin.platform — Platform administrator, no customer portfolio",
        "admin.model — Model administrator",
    ]
    st.caption(" · ".join(accounts))
    username = st.text_input("Username", value="cro.shum")
    password = st.text_input("Password", type="password", value="Harbour-Demo-2026")
    if st.button("Sign in", type="primary"):
        db = session()
        try:
            payload = analytics.authenticate(db, username.strip(), password)
            db.commit()
            st.session_state["token"] = payload["token"]
            st.session_state["display_name"] = payload["display_name"]
            st.session_state["role_label"] = payload["role_label"]
            st.rerun()
        except AccessDeniedError as exc:
            db.commit()
            st.error(str(exc))
        finally:
            db.close()


def chart(title: str, series: list[dict]) -> None:
    st.markdown(f"**{title}**")
    points = [row for row in series if row.get("value") is not None]
    if not points:
        st.info("No plotted values. Missing values are not shown as zero.")
        return
    frame = pd.DataFrame(
        {"as_of": [format_date(row["as_of_date"]) for row in points], "value": [float(row["value"]) for row in points]}
    )
    st.line_chart(frame, x="as_of", y="value")
    last = points[-1]
    st.caption(
        f"Source system: {last.get('source_system')} · As at {format_date(last.get('as_of_date'))} · "
        f"Currency: {last.get('currency')} · Unit: {last.get('unit')} · "
        f"Calculation basis: {last.get('calculation_basis')} · Data quality: {last.get('data_quality')}"
    )


def money(value, currency="HKD") -> str:
    if value is None:
        return "—"
    from decimal import Decimal

    return format_money(Decimal(str(value)), currency)


def table(rows: list[dict]) -> None:
    if not rows:
        st.info("No authorised rows.")
        return
    st.dataframe(pd.DataFrame(jsonable(rows)), use_container_width=True, hide_index=True)


def page_dashboard(db, principal) -> None:
    data = analytics.dashboard(db, principal)
    st.metric("Aggregate exposure (HKD)", money(data["aggregate_exposure_hkd"]))
    st.caption(f"{data['source_system']} · {data['calculation_basis']} · Data quality: {data['data_quality']}")
    left, right = st.columns(2)
    with left:
        st.subheader("Top customer concentrations")
        table(data["top_customers"])
        st.subheader("Deteriorating ratings")
        table(data["deteriorating_ratings"])
        st.subheader("Limit breaches")
        table(data["limit_breaches"])
        st.subheader("Overdue annual reviews")
        table(data["overdue_annual_reviews"])
        st.subheader("High-risk customer classifications")
        table(data["high_risk_classifications"])
    with right:
        st.subheader("Top group concentrations")
        table(data["top_groups"])
        st.subheader("Rising utilisation")
        table(data["rising_utilisation"])
        st.subheader("Covenant breaches")
        table(data["covenant_breaches"])
        st.subheader("Outstanding actions")
        table(data["outstanding_actions"])
        st.subheader("Early-warning indicators")
        table(data["early_warnings"])
    st.subheader("Risk-domain distribution")
    if data["risk_domain_distribution"]:
        st.bar_chart(pd.DataFrame({"documents": data["risk_domain_distribution"]}))
        st.caption("Count of authorised trusted documents by risk domain. Colour is not the status.")
    st.subheader("Stale documents")
    table(data["stale_documents"])
    st.write(f"Ingestion failures and quarantined files recorded: {data['ingestion_failure_count']}.")


def page_search(db, principal) -> None:
    with st.form("search"):
        q = st.text_input("Name, identifier or keyword")
        c1, c2, c3 = st.columns(3)
        industry = c1.text_input("Industry")
        jurisdiction = c2.text_input("Jurisdiction")
        manager = c3.text_input("Relationship manager")
        c4, c5, c6 = st.columns(3)
        rating = c4.text_input("Internal risk rating")
        classification = c5.selectbox("Customer risk classification", ["", "Low", "Medium", "High"])
        watch = c6.selectbox("Watchlist", ["", "not_listed", "watch", "enhanced_monitoring"])
        c7, c8, c9 = st.columns(3)
        facility = c7.text_input("Facility type")
        product = c8.text_input("Product")
        limit_status = c9.selectbox("Limit status", ["", "within_limit", "near_breach", "breach", "unresolved"])
        ewi = st.checkbox("Open early-warning indicator")
        submitted = st.form_submit_button("Search")
    if submitted or "search_rows" not in st.session_state:
        rows = analytics.search_customers(
            db,
            principal,
            {
                "q": q,
                "industry": industry or None,
                "jurisdiction": jurisdiction or None,
                "relationship_manager": manager or None,
                "internal_risk_rating": rating or None,
                "customer_risk_classification": classification or None,
                "watchlist_status": watch or None,
                "facility_type": facility or None,
                "product": product or None,
                "limit_status": limit_status or None,
                "early_warning": "open" if ewi else None,
            },
        )
        st.session_state["search_rows"] = jsonable(rows)
    rows = st.session_state.get("search_rows") or []
    st.write(f"{len(rows)} authorised customers.")
    table(rows)
    if rows:
        choice = st.selectbox("Open Customer 360", [row["customer_id"] for row in rows])
        if st.button("Open customer"):
            st.session_state["customer_id"] = choice
            st.session_state["page"] = "Customer 360"
            st.rerun()


def page_customer(db, principal) -> None:
    customer_id = st.text_input("Customer ID", value=st.session_state.get("customer_id", "CUS-AHTL-0001")).strip()
    load = st.button("Load customer")
    if load or st.session_state.get("_loaded") == customer_id:
        view = analytics.customer_360(db, principal, customer_id)
        st.session_state["customer_view"] = jsonable(view)
        st.session_state["customer_id"] = customer_id
        st.session_state["_loaded"] = customer_id
    elif "customer_view" not in st.session_state:
        st.info("Enter a customer identifier and load the consolidated view.")
        return
    view = st.session_state["customer_view"]
    profile = view["profile"]
    st.header(profile["legal_name"])
    st.write(profile["business_summary"])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total exposure HKD", money(view["position"]["total_exposure_hkd"]))
    c2.metric("Undrawn HKD", money(view["position"]["undrawn_hkd"]))
    c3.metric("Rating trend", view["risk_trend"])
    c4.metric("Watchlist", profile["watchlist_status"])
    st.caption(
        f"Source: {view['position'].get('source_system')} · As at {view['position'].get('as_of_date')} · "
        f"Currency HKD · Unit HKD · {view['position'].get('data_quality')} · "
        "Excluded facilities are not treated as zero."
    )
    st.subheader("Legal entity")
    table([profile])
    st.subheader("Beneficial ownership (fictional)")
    table(view["beneficial_owners"])
    st.subheader("Group")
    table(view["group_members"])
    st.subheader("Products")
    table(view["products"])
    st.subheader("Facilities")
    table(view["facilities"])
    st.subheader("Histories")
    histories = view["histories"]
    for key in ("drawn_exposure", "deposits", "liquidity_ratio", "cash_reserves"):
        chart(key.replace("_", " ").title(), histories.get(key, []))
    st.subheader("Concern score — deterministic demonstration")
    score = view["concern_score"]
    st.write(f"Score {score.get('score')} · {score.get('label')} · {score.get('hackathon_notice')}")
    st.caption(f"Formula: {score.get('formula')} · Calculated {score.get('calculated_at')} · Quality {score.get('data_quality')}")
    table(score.get("components") or [])
    if score.get("missing_inputs"):
        st.warning("Missing inputs: " + ", ".join(score["missing_inputs"]))
    for title, key in (
        ("Collateral", "collateral"),
        ("Covenants", "covenants"),
        ("Early-warning indicators", "early_warnings"),
        ("Actions", "actions"),
        ("Reviews", "reviews"),
        ("Events", "events"),
        ("Qualitative assessments", "qualitative"),
        ("Legal matters", "legal_matters"),
        ("Documents", "documents"),
        ("Data-quality issues", "data_quality_issues"),
    ):
        st.subheader(title)
        table(view[key])
    st.subheader("AML and financial-crime indicators")
    st.info(view["aml_notice"])
    table(view["alerts"])
    st.subheader("Consolidated assessment")
    for line in view["consolidated_assessment"]:
        st.markdown(f"**{line['type']}.** {line['text']}")


def page_group(db, principal) -> None:
    groups = analytics.list_groups(db, principal)
    if not groups:
        st.info("No authorised groups.")
        return
    choice = st.selectbox("Group", [f"{row['group_id']} — {row['name']}" for row in groups])
    group_id = choice.split(" — ", 1)[0]
    view = analytics.group_360(db, principal, group_id)
    st.header(view["name"])
    st.metric("Drawn exposure in HKD", money(view["drawn_hkd"]))
    st.caption(view["calculation_basis"])
    if view["entities_outside_portfolio"]:
        st.warning(f"{view['entities_outside_portfolio']} group entities are outside your portfolio and are excluded.")
    st.subheader("Original currencies — not aggregated together")
    table([{"currency": key, "drawn": money(value, key)} for key, value in view["original_currency_drawn"].items()])
    for entity in view["entities_in_portfolio"]:
        st.markdown(f"**{entity['legal_name']}** ({entity['customer_id']})")
        table(entity["facilities"])


def page_ask(db, principal) -> None:
    question = st.text_area(
        "Question",
        value="What are the main risks associated with Apex Harbour Trading Limited?",
        height=100,
    )
    focus = st.text_input("Optional customer in focus", value=st.session_state.get("customer_id", ""))
    if st.button("Ask", type="primary"):
        answer = ask(db, principal, question, focus_customer_id=focus or None)
        st.session_state["answer"] = answer
    if "answer" not in st.session_state:
        return
    answer = st.session_state["answer"]
    if answer["abstained"]:
        st.warning(answer["message"])
    else:
        st.write(answer["message"])
    if answer.get("control_notice"):
        st.info(answer["control_notice"])
    if answer.get("model_commentary"):
        st.caption(answer["model_commentary"])
    if answer.get("version_rule"):
        st.caption(answer["version_rule"])
    for claim in answer["claims"]:
        with st.container(border=True):
            st.markdown(f"**{claim['claim_type']}** · {claim['text']}")
            for citation in claim["citations"]:
                label = citation.get("label") or "Source"
                document_id = citation.get("document_id")
                if document_id and st.button(label, key=f"cite-{claim['claim_id']}-{document_id}-{citation.get('page')}"):
                    st.session_state["source_id"] = document_id
                    st.session_state["source_page"] = citation.get("page") or 1
                    st.session_state["page"] = "Trusted Documents"
                    st.rerun()
                elif not document_id:
                    st.caption(label)


def page_report(db, principal) -> None:
    customer_id = st.text_input("Customer ID for the draft report", value=st.session_state.get("customer_id", "CUS-AHTL-0001"))
    if st.button("Generate draft report"):
        payload = generate_customer_report(db, principal, customer_id.strip())
        st.session_state["report"] = payload
    if "report" not in st.session_state:
        st.info("Generated reports are drafts. There is no simulated bank approval.")
        return
    payload = st.session_state["report"]
    st.success(payload["approval_status"])
    st.write(f"Report {payload['report_id']} · {payload['generated_at']}")
    from app.config import get_settings

    root = get_settings().report_dir
    html = (root / f"{payload['report_id']}.html").read_bytes()
    pdf = (root / f"{payload['report_id']}.pdf").read_bytes()
    st.download_button("Download HTML", html, file_name=f"{payload['report_id']}.html", mime="text/html")
    st.download_button("Download PDF", pdf, file_name=f"{payload['report_id']}.pdf", mime="application/pdf")
    st.download_button(
        "Download JSON",
        (root / f"{payload['report_id']}.json").read_bytes(),
        file_name=f"{payload['report_id']}.json",
        mime="application/json",
    )
    note = st.text_area("Human-review note")
    if st.button("Record human review"):
        result = record_review(db, principal, payload["report_id"], note or "Reviewed in the demonstration.")
        st.success(result["approval_status"])
    for section in payload["sections"]:
        with st.expander(section["title"], expanded=section["title"].startswith("2.")):
            if section.get("narrative"):
                st.write(section["narrative"])
            if section.get("rows"):
                st.dataframe(pd.DataFrame(section["rows"], columns=section["headers"] or None), hide_index=True)
            for fact in section.get("facts") or []:
                st.markdown(f"**{fact['kind']}.** {fact['text']}")
                for citation in fact["citations"]:
                    st.caption(citation["label"])


def page_portfolio(db, principal) -> None:
    view = analytics.portfolio_view(db, principal)
    st.metric("Aggregate exposure (HKD)", money(view["aggregate_exposure_hkd"]))
    st.caption(view["calculation_basis"])
    table(view["customers"])
    left, right = st.columns(2)
    with left:
        st.subheader("Industry concentration (HKD)")
        if view["industry_hkd"]:
            st.bar_chart(pd.DataFrame({"hkd": {key: float(value) for key, value in view["industry_hkd"].items()}}))
            st.caption("HKD equivalents from stored rates. Text labels identify the industry.")
    with right:
        st.subheader("Jurisdiction concentration (HKD)")
        if view["jurisdiction_hkd"]:
            st.bar_chart(pd.DataFrame({"hkd": {key: float(value) for key, value in view["jurisdiction_hkd"].items()}}))
            st.caption("HKD equivalents from stored rates. Text labels identify the jurisdiction.")


def page_table(loader):
    def inner(db, principal) -> None:
        table(jsonable(loader(db, principal)))

    return inner


def page_aml(db, principal) -> None:
    view = analytics.aml_view(db, principal)
    if view["restricted"]:
        st.warning(view["message"])
        return
    st.info(view["message"])
    for row in view["rows"]:
        st.markdown(f"**{row['legal_name']}** · classification {row['aml_risk_classification']}")
        table(row["alerts"])
        table(row["reviews"])


def page_documents(db, principal) -> None:
    rows = analytics.documents_view(db, principal)
    table(jsonable(rows))
    if not rows:
        return
    default = st.session_state.get("source_id", rows[0]["document_id"])
    ids = [row["document_id"] for row in rows]
    if default not in ids:
        default = ids[0]
    document_id = st.selectbox("Open source", ids, index=ids.index(default))
    page = st.number_input("PDF page", min_value=1, value=int(st.session_state.get("source_page") or 1))
    sheet = st.text_input("Excel sheet name (optional)")
    payload = sources.open_source(db, principal, document_id, page=int(page), sheet=sheet or None)
    st.subheader(payload["title"])
    st.caption(
        f"{payload['original_filename']} · {payload['controlled_reference']} · version {payload['version']} · "
        f"reporting date {format_date(payload['reporting_date'])} · "
        f"{'Superseded' if payload['superseded'] else 'Current version'} · "
        f"checksum {payload['checksum_sha256'][:12]}… · malware scan {payload['malware_scan_status']}"
    )
    if payload["prompt_injection_suspected"]:
        st.warning("This document contains instruction-like text. It is stored as content and does not change controls.")
    preview = payload["preview"]
    if preview["kind"] == "pdf":
        st.image(preview["png"], caption=f"Page {preview['page']} of {preview['page_count']}")
    elif preview["kind"] in {"xlsx", "csv"}:
        st.dataframe(pd.DataFrame(preview["rows"]), hide_index=True)
        if preview["kind"] == "xlsx":
            st.caption("Sheet: " + preview["sheet"])
    elif preview["kind"] == "docx":
        for paragraph in preview["paragraphs"]:
            st.write(paragraph)
    else:
        st.text(preview.get("text", ""))
    if principal.can("document.download"):
        data, media, filename = sources.document_bytes(db, principal, document_id)
        st.download_button("Download original", data, file_name=filename, mime=media)


def page_upload(db, principal) -> None:
    st.write("Uploads must carry the synthetic-data declaration unless an administrator has enabled demonstration mode.")
    customer_id = st.text_input("Customer ID", value="CUS-AHTL-0001")
    domain = st.text_input("Risk domain", value="credit")
    reporting = st.date_input("Reporting date")
    upload = st.file_uploader("PDF, DOCX, XLSX, CSV or TXT", type=["pdf", "docx", "xlsx", "csv", "txt"])
    if upload is not None and st.button("Ingest"):
        result = uploads.accept_upload(
            db,
            principal,
            filename=upload.name,
            data=upload.getvalue(),
            customer_id=customer_id.strip(),
            risk_domain=domain.strip(),
            document_type="uploaded_report",
            reporting_date=reporting,
        )
        st.success(f"{result['document_id']} · {result['ingestion_status']}")
        if result["prompt_injection_suspected"]:
            st.warning("Instruction-like text was logged and ignored as an instruction.")


def page_quality(db, principal) -> None:
    view = analytics.data_quality_view(db, principal)
    st.subheader("Recorded issues")
    table(view["issues"])
    st.subheader("Unresolved facility snapshots")
    table(jsonable(view["unresolved_snapshots"]))
    st.subheader("Stale documents")
    table(view["stale_documents"])
    st.subheader("Ingestion exceptions")
    table(view["ingestion_exceptions"])


def page_evaluation(db, principal) -> None:
    st.write("The evaluation uses the seeded questions. Results below are measured on this database, not assumed.")
    if principal.can("evaluation.run") and st.button("Run evaluation"):
        summary = run_evaluation(db)
        st.session_state["evaluation"] = summary
    if "evaluation" not in st.session_state:
        st.info("Run the evaluation to see retrieval, citation, abstention and authorisation scores.")
        return
    summary = st.session_state["evaluation"]
    headline = {key: value for key, value in summary.items() if key != "results"}
    st.json(headline)
    table(
        [
            {
                "id": item["id"],
                "scenario": item["scenario"],
                "passed": "Pass" if item["passed"] else "Fail",
                "abstained": item["abstained"],
                "contradiction": item["contradiction"],
            }
            for item in summary["results"]
        ]
    )


def page_governance(db, principal) -> None:
    view = analytics.governance_view(db, principal)
    st.write(view["intended_purpose"])
    st.write(f"System owner: {view['system_owner']}")
    st.write(f"Risk owner: {view['risk_owner']}")
    st.write(f"Periodic review date: {view['periodic_review_date']}")
    st.info(view["independent_validation"])
    st.write(view["training_data_declaration"])
    st.warning(view["residual_risks"])
    st.subheader("Model inventory")
    table(view["models"])
    st.subheader("Prompt register")
    table(view["prompts"])
    st.subheader("Prohibited uses")
    table(view["prohibited_uses"])
    st.subheader("Third parties")
    table(view["third_parties"])
    st.subheader("Controls")
    table(jsonable(view["controls"]))
    st.subheader("Risk taxonomy")
    table(view["taxonomy"])
    st.subheader("AI incidents")
    table(jsonable(view["incidents"]))
    if not view["incidents"]:
        st.caption("No demonstration incidents are open. The register exists so an incident can be recorded.")


def page_audit(db, principal) -> None:
    table(jsonable(analytics.audit_view(db, principal)))


def page_admin(db, principal) -> None:
    view = analytics.admin_view(db, principal)
    table(view["users"])
    table(jsonable(view["controls"]))
    if principal.can("admin.demo_mode"):
        enabled = st.checkbox("Controlled demonstration mode for uploads that lack a synthetic declaration", value=False)
        if st.button("Save demonstration mode"):
            st.success(str(analytics.set_control(db, principal, "demo_mode", enabled)))
    if principal.can("model.admin"):
        killed = st.checkbox("AI kill switch — suppress narrative commentary", value=False)
        if st.button("Save kill switch"):
            st.success(str(analytics.set_control(db, principal, "ai_kill_switch", killed)))


def main() -> None:
    if "token" not in st.session_state:
        login()
        return
    banner()
    st.sidebar.title("Harbour Meridian")
    st.sidebar.caption(f"{st.session_state.get('display_name')} · {st.session_state.get('role_label')}")
    page = st.sidebar.radio("Workspace", PAGES, index=PAGES.index(st.session_state.get("page", PAGES[0])))
    st.session_state["page"] = page
    if st.sidebar.button("Sign out"):
        st.session_state.clear()
        st.rerun()
    handlers = {
        "Management Dashboard": page_dashboard,
        "Customer and Counterparty Search": page_search,
        "Customer 360": page_customer,
        "Group 360": page_group,
        "Ask Risk Intelligence": page_ask,
        "Customer Risk Report Generator": page_report,
        "Portfolio Risk View": page_portfolio,
        "Facilities and Exposure": page_table(analytics.facilities_view),
        "Limits and Covenants": page_table(analytics.covenants_view),
        "Collateral": page_table(analytics.collateral_view),
        "Early-Warning Indicators": page_table(analytics.ewi_view),
        "AML and Financial-Crime Indicators": page_aml,
        "Trusted Documents": page_documents,
        "Upload and Ingestion": page_upload,
        "Data Quality and Freshness": page_quality,
        "RAG Evaluation": page_evaluation,
        "AI Governance": page_governance,
        "Audit Activity": page_audit,
        "Administration": page_admin,
    }
    db = session()
    try:
        principal = current_principal(db)
        if principal is None:
            st.session_state.clear()
            st.rerun()
        handlers[page](db, principal)
        db.commit()
    except AccessDeniedError as exc:
        db.commit()
        st.error(str(exc))
    except (IngestionError, SeparationOfDutiesError) as exc:
        db.commit()
        st.error(str(exc))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
