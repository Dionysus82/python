"""Management interface for the Harbour Meridian hackathon profile.

Domain rules live in services. This module only presents them.
Charts summarise authorised figures. Raw database rows are not dumped onto the page.
"""

from __future__ import annotations

from decimal import Decimal

import altair as alt
import pandas as pd
import streamlit as st

from app.database import get_session_factory
from app.domain.banner import FICTIONAL_BANK, FICTIONAL_BANK_NOTICE, SYNTHETIC_BANNER
from app.domain.dates import coerce_date, format_date
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
      .banner {background:#9b2330;color:#fff;padding:8px 14px;font-weight:700;border-radius:8px;text-align:center;}
      .hm-note {color:#5d6b7a;font-size:0.86rem;}
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

PALETTE = ["#0b2440", "#1f6f6a", "#b0892c", "#9b2330", "#143556", "#a16207", "#1b6b3a", "#5d6b7a", "#3d6b99", "#7a4e2d"]
HISTORY_CHARTS = (
    ("drawn_exposure", "Drawn exposure (HKD)"),
    ("utilisation_pct", "Limit utilisation (%)"),
    ("liquidity_ratio", "Liquidity ratio"),
    ("deposits", "Deposits (HKD)"),
    ("cash_reserves", "Cash reserves (HKD)"),
    ("internal_rating", "Internal credit rating (1 strongest to 10 default)"),
    ("interest_coverage", "Interest coverage (times)"),
)


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


def _number(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def money(value, currency="HKD") -> str:
    if value is None or value == "":
        return "—"
    return format_money(Decimal(str(value)), currency)


def _pairs(mapping: dict) -> list[tuple[str, float]]:
    pairs = []
    for label, value in mapping.items():
        number = _number(value)
        if number is None or number == 0:
            continue
        pairs.append((str(label), number))
    return pairs


def pie_chart(title: str, mapping: dict, *, note: str) -> None:
    st.markdown(f"**{title}**")
    pairs = _pairs(mapping)
    if not pairs:
        st.info("Nothing to plot. Missing amounts are left out and are not shown as zero.")
        return
    frame = pd.DataFrame({"Category": [label for label, _ in pairs], "Value": [value for _, value in pairs]})
    chart = (
        alt.Chart(frame)
        .mark_arc(innerRadius=52)
        .encode(
            theta=alt.Theta("Value:Q"),
            color=alt.Color("Category:N", scale=alt.Scale(range=PALETTE), legend=alt.Legend(title=None)),
            tooltip=["Category:N", alt.Tooltip("Value:Q", format=",.2f")],
        )
        .properties(height=280)
    )
    st.altair_chart(chart, width="stretch")
    st.caption(note)


def bar_chart(title: str, mapping: dict, *, note: str, horizontal: bool = False) -> None:
    st.markdown(f"**{title}**")
    pairs = _pairs(mapping)
    if not pairs:
        st.info("Nothing to plot. Missing amounts are left out and are not shown as zero.")
        return
    frame = pd.DataFrame({"Category": [label for label, _ in pairs], "Value": [value for _, value in pairs]})
    if horizontal:
        chart = (
            alt.Chart(frame)
            .mark_bar(color="#0b2440")
            .encode(
                x=alt.X("Value:Q", title=None),
                y=alt.Y("Category:N", sort="-x", title=None),
                tooltip=["Category:N", alt.Tooltip("Value:Q", format=",.2f")],
            )
            .properties(height=max(180, 28 * len(pairs)))
        )
        st.altair_chart(chart, width="stretch")
    else:
        st.bar_chart(frame, x="Category", y="Value", width="stretch")
    st.caption(note)


def line_chart(title: str, series: list[dict], *, note: str | None = None) -> None:
    st.markdown(f"**{title}**")
    points = []
    for row in series or []:
        number = _number(row.get("value"))
        as_of = coerce_date(row.get("as_of_date"))
        if number is None or as_of is None:
            continue
        points.append((as_of, number, row))
    if len(points) < 2:
        st.info("Fewer than two historical points. Missing values are not plotted as zero.")
        return
    frame = pd.DataFrame(
        {"As at": pd.to_datetime([item[0].isoformat() for item in points]), "Value": [item[1] for item in points]}
    )
    chart = (
        alt.Chart(frame)
        .mark_line(color="#0b2440", point=True)
        .encode(
            x=alt.X("As at:T", title=None, axis=alt.Axis(format="%b %Y", labelAngle=-35, tickCount=6)),
            y=alt.Y("Value:Q", title=None, scale=alt.Scale(zero=False)),
            tooltip=[
                alt.Tooltip("As at:T", title="Month-end", format="%d %b %Y"),
                alt.Tooltip("Value:Q", format=",.2f"),
            ],
        )
        .properties(height=240)
    )
    st.altair_chart(chart, width="stretch")
    last = points[-1][2]
    detail = (
        f"Source system: {last.get('source_system')} · As at {format_date(last.get('as_of_date'))} · "
        f"Currency: {last.get('currency')} · Unit: {last.get('unit')} · "
        f"Calculation basis: {last.get('calculation_basis')} · Data quality: {last.get('data_quality')}"
    )
    st.caption(note or detail)


def bullets(title: str, lines: list[str]) -> None:
    st.markdown(f"**{title}**")
    if not lines:
        st.caption("None in the authorised view.")
        return
    for line in lines[:12]:
        st.markdown(f"- {line}")


def page_dashboard(db, principal) -> None:
    data = analytics.dashboard(db, principal)
    st.title("Management Dashboard")
    st.caption("Authorised portfolio, shown as charts. Figures use stored HKD equivalents.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Customers", data["customer_count"])
    c2.metric("Aggregate exposure", money(data["aggregate_exposure_hkd"]))
    c3.metric("Overdue annual reviews", data["overdue_review_count"])
    c4.metric("Open early warnings", data["open_ewi_count"])
    st.caption(
        f"{data['source_system']} · {data['calculation_basis']} · Data quality: {data['data_quality']} · "
        f"Ingestion failures and quarantined files: {data['ingestion_failure_count']}."
    )
    left, right = st.columns(2)
    with left:
        pie_chart(
            "Exposure by industry",
            data["industry_hkd"],
            note="Share of authorised total exposure in HKD. The legend names each industry.",
        )
    with right:
        pie_chart(
            "Exposure by jurisdiction",
            data["jurisdiction_hkd"],
            note="Share of authorised total exposure in HKD. The legend names each jurisdiction.",
        )
    line_chart(
        "Authorised drawn exposure by month-end",
        data["exposure_history"],
        note="Synthetic month-end history. Drawn HKD only. Unresolved facility amounts are excluded.",
    )
    left, right = st.columns(2)
    with left:
        bar_chart(
            "Largest customer exposures",
            {row["legal_name"]: row["total_exposure_hkd"] for row in data["top_customers"]},
            note="Total exposure in HKD for the eight largest authorised customers.",
            horizontal=True,
        )
        bar_chart(
            "Internal rating distribution",
            data["rating_distribution"],
            note="Count of customers on each notch. 1 is strongest and 10 is default.",
        )
    with right:
        pie_chart(
            "Customer risk classification",
            data["classification_distribution"],
            note="Count of authorised customers. Colour is paired with the classification name.",
        )
        bar_chart(
            "Trusted documents by risk domain",
            data["risk_domain_distribution"],
            note="Count of authorised trusted documents. Colour is not a status.",
        )
    bullets(
        "Deteriorating ratings",
        [f"{row['legal_name']} — {row['trend']}" for row in data["deteriorating_ratings"]],
    )
    bullets(
        "Rising utilisation (at least 15 percentage points since the first month-end)",
        [
            f"{row['legal_name']} — {row['from_pct']}% to {row['to_pct']}%"
            for row in data["rising_utilisation"]
        ],
    )
    bullets(
        "Limit breaches and near breaches",
        [
            f"{row['legal_name']} — {row['limit_status'].replace('_', ' ')} at {row['utilisation_pct']}%"
            for row in [*data["limit_breaches"], *data["near_breaches"]]
        ],
    )
    bullets(
        "Overdue annual reviews",
        [f"{row['customer_id']} — due {format_date(row['due_date'])}" for row in data["overdue_annual_reviews"]],
    )


def page_search(db, principal) -> None:
    st.title("Customer and Counterparty Search")
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
            },
        )
        st.session_state["search_rows"] = rows
    rows = st.session_state.get("search_rows") or []
    st.write(f"{len(rows)} authorised customers.")
    if not rows:
        st.info("No authorised customers match these filters.")
        return
    bar_chart(
        "Exposure of matching customers",
        {row["legal_name"]: row["total_exposure_hkd"] for row in rows[:12]},
        note="HKD total exposure. Customers without a complete HKD amount are omitted from the chart.",
        horizontal=True,
    )
    pie_chart(
        "Matching customers by industry",
        _count(rows, "industry"),
        note="Count of customers in the current search result.",
    )
    choice = st.selectbox(
        "Open Customer 360",
        [f"{row['customer_id']} — {row['legal_name']} — rating {row['internal_credit_rating']}" for row in rows],
    )
    if st.button("Open customer"):
        st.session_state["customer_id"] = choice.split(" — ", 1)[0]
        st.session_state["page"] = "Customer 360"
        st.rerun()


def _count(rows: list[dict], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        label = str(row.get(key) or "Unstated")
        counts[label] = counts.get(label, 0) + 1
    return counts


def _load_customer(db, principal, customer_id: str) -> dict | None:
    view = analytics.customer_360(db, principal, customer_id)
    st.session_state["customer_view"] = jsonable(view)
    st.session_state["customer_id"] = customer_id
    st.session_state["_loaded"] = customer_id
    return st.session_state["customer_view"]


def page_customer(db, principal) -> None:
    st.title("Customer 360")
    if "customer_choices" not in st.session_state:
        st.session_state["customer_choices"] = analytics.search_customers(db, principal, {})
    choices = st.session_state["customer_choices"]
    labels = [f"{row['customer_id']} — {row['legal_name']}" for row in choices] or ["CUS-AHTL-0001 — Apex Harbour Trading Limited"]
    current = st.session_state.get("customer_id", "CUS-AHTL-0001")
    index = next((i for i, label in enumerate(labels) if label.startswith(current)), 0)
    selected = st.selectbox("Customer", labels, index=index)
    customer_id = selected.split(" — ", 1)[0]
    if st.session_state.get("_loaded") != customer_id or "customer_view" not in st.session_state:
        view = _load_customer(db, principal, customer_id)
        if view is None:
            return
    view = st.session_state["customer_view"]
    profile = view["profile"]
    position = view["position"]
    st.header(profile["legal_name"])
    st.write(profile["business_summary"])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total exposure", money(position.get("total_exposure_hkd")))
    c2.metric("Utilisation", "—" if position.get("utilisation_pct") is None else f"{position['utilisation_pct']}%")
    c3.metric("Rating trend", view["risk_trend"])
    c4.metric("Watchlist", profile["watchlist_status"].replace("_", " "))
    st.caption(
        f"Source: {position.get('source_system')} · As at {format_date(position.get('as_of_date'))} · "
        "Currency HKD · Notional is excluded from total exposure. Incomplete facilities are excluded, not treated as zero."
    )
    facts = st.columns(4)
    facts[0].caption(f"Industry: {profile['industry']}")
    facts[1].caption(f"Jurisdiction: {profile['jurisdiction']}")
    facts[2].caption(f"Relationship manager: {profile['relationship_manager']}")
    facts[3].caption(f"Classification: {profile['customer_risk_classification']} · AML: {profile['aml_risk_classification']}")
    histories = view["histories"]
    _period_change(histories)
    left, right = st.columns(2)
    with left:
        pie_chart(
            "Exposure composition",
            {
                "Drawn": position.get("drawn_hkd"),
                "Undrawn": position.get("undrawn_hkd"),
                "Contingent": position.get("contingent_hkd"),
                "Counterparty credit exposure": position.get("ccr_hkd"),
            },
            note="HKD components of the latest position. Notional is not included.",
        )
    with right:
        bar_chart(
            "Facilities — drawn versus committed (HKD)",
            {
                row["name"]: row["hkd_drawn"]
                for row in view["facilities"]
                if row.get("hkd_drawn") not in (None, "")
            },
            note="Latest stored HKD drawn amount by facility name.",
            horizontal=True,
        )
    left, right = st.columns(2)
    for index, (key, title) in enumerate(HISTORY_CHARTS):
        column = left if index % 2 == 0 else right
        with column:
            line_chart(title, histories.get(key, []))
    score = view["concern_score"]
    st.subheader("Concern score — deterministic demonstration")
    st.write(f"Score {score.get('score')} · {score.get('label')}")
    st.caption(f"{score.get('hackathon_notice')} · Formula: {score.get('formula')}")
    bar_chart(
        "Score components",
        {
            item.get("label") or item.get("key") or "Component": item.get("score")
            for item in (score.get("components") or [])
            if isinstance(item, dict)
        },
        note="Component scores from the Python calculation. A missing input is omitted, not scored as zero.",
    )
    if score.get("missing_inputs"):
        st.warning("Missing inputs: " + ", ".join(score["missing_inputs"]))
    bullets("Beneficial owners (fictional)", [f"{row['name']} · {row['ownership_pct']}%" for row in view["beneficial_owners"]])
    bullets(
        "Group members",
        [
            f"{row['legal_name']} ({row['customer_id']}) — {'in portfolio' if row['in_portfolio'] else 'outside portfolio'}"
            for row in view["group_members"]
        ],
    )
    bullets(
        "Covenants",
        [
            f"{row.get('name')} — {row.get('status')} (actual {row.get('actual_value')} {row.get('unit') or ''})"
            for row in view["covenants"]
        ],
    )
    bullets(
        "Early-warning indicators",
        [f"{row.get('description')} — {row.get('status')}" for row in view["early_warnings"]],
    )
    bullets(
        "Reviews and actions",
        [
            f"{row.get('review_type') or row.get('description') or 'Item'} — {row.get('status')}"
            for row in [*view["reviews"], *view["actions"]]
        ],
    )
    st.subheader("AML and financial-crime indicators")
    st.info(view["aml_notice"])
    bullets("Indicators", [f"{row.get('alert_type', 'Alert')} — {row.get('status')}" for row in view["alerts"]])
    st.subheader("Consolidated assessment")
    for line in view["consolidated_assessment"]:
        st.markdown(f"**{line['type']}.** {line['text']}")


def _period_change(histories: dict) -> None:
    utilisation = [row for row in histories.get("utilisation_pct", []) if _number(row.get("value")) is not None]
    rating = [row for row in histories.get("internal_rating", []) if _number(row.get("value")) is not None]
    if len(utilisation) < 2 and len(rating) < 2:
        return
    parts = []
    if len(utilisation) >= 2:
        start, end = utilisation[0], utilisation[-1]
        parts.append(
            f"Utilisation {start['value']}% on {format_date(start['as_of_date'])} → {end['value']}% on {format_date(end['as_of_date'])}"
        )
    if len(rating) >= 2:
        start, end = rating[0], rating[-1]
        parts.append(
            f"Rating {start['value']} on {format_date(start['as_of_date'])} → {end['value']} on {format_date(end['as_of_date'])}"
        )
    st.info("Synthetic history · " + " · ".join(parts))


def page_group(db, principal) -> None:
    st.title("Group 360")
    groups = analytics.list_groups(db, principal)
    if not groups:
        st.info("No authorised groups.")
        return
    bar_chart(
        "Drawn exposure by group",
        {row["name"]: row["drawn_hkd"] for row in groups},
        note="Sum of authorised entity HKD drawn amounts. Entities outside the portfolio are excluded.",
        horizontal=True,
    )
    choice = st.selectbox("Group", [f"{row['group_id']} — {row['name']}" for row in groups])
    group_id = choice.split(" — ", 1)[0]
    view = analytics.group_360(db, principal, group_id)
    st.header(view["name"])
    st.metric("Drawn exposure", money(view["drawn_hkd"]))
    st.caption(view["calculation_basis"])
    if view["entities_outside_portfolio"]:
        st.warning(f"{view['entities_outside_portfolio']} group entities are outside your portfolio and are excluded.")
    st.markdown("**Original currencies — kept separate**")
    currencies = list(view["original_currency_drawn"].items())
    if currencies:
        columns = st.columns(len(currencies))
        for column, (currency, amount) in zip(columns, currencies, strict=True):
            column.metric(currency, money(amount, currency))
        st.caption("Each figure stays in its original currency. Mixed currencies are not added together.")
    bar_chart(
        "Members in the authorised portfolio",
        {entity["legal_name"]: entity["position"]["drawn_hkd"] for entity in view["entities_in_portfolio"]},
        note="Stored HKD drawn amount for each member you are allowed to see. Incomplete positions are omitted.",
        horizontal=True,
    )


def page_ask(db, principal) -> None:
    st.title("Ask Risk Intelligence")
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
    st.title("Customer Risk Report")
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
            for fact in section.get("facts") or []:
                st.markdown(f"**{fact['kind']}.** {fact['text']}")
                for citation in fact["citations"]:
                    st.caption(citation["label"])


def page_portfolio(db, principal) -> None:
    st.title("Portfolio Risk View")
    view = analytics.portfolio_view(db, principal)
    st.metric("Aggregate exposure", money(view["aggregate_exposure_hkd"]))
    st.caption(view["calculation_basis"])
    left, right = st.columns(2)
    with left:
        pie_chart(
            "Industry concentration",
            view["industry_hkd"],
            note="HKD equivalents from stored rates. The legend names the industry.",
        )
    with right:
        pie_chart(
            "Jurisdiction concentration",
            view["jurisdiction_hkd"],
            note="HKD equivalents from stored rates. The legend names the jurisdiction.",
        )
    bar_chart(
        "Customer exposure",
        {row["legal_name"]: row["total_exposure_hkd"] for row in view["customers"][:15]},
        note="Fifteen largest authorised total exposures in HKD.",
        horizontal=True,
    )
    bar_chart(
        "Utilisation by customer",
        {row["legal_name"]: row["utilisation_pct"] for row in view["customers"] if row["utilisation_pct"] is not None},
        note="Latest utilisation percent. Customers with an unresolved utilisation are omitted.",
        horizontal=True,
    )


def page_facilities(db, principal) -> None:
    st.title("Facilities and Exposure")
    rows = analytics.facilities_view(db, principal)
    by_customer: dict[str, float] = {}
    by_type: dict[str, int] = {}
    for row in rows:
        by_type[row.get("facility_type") or "Unstated"] = by_type.get(row.get("facility_type") or "Unstated", 0) + 1
        amount = _number(row.get("hkd_drawn"))
        if amount is None:
            continue
        name = row["legal_name"]
        by_customer[name] = by_customer.get(name, 0) + amount
    left, right = st.columns(2)
    with left:
        pie_chart("Facilities by type", by_type, note="Count of latest facility snapshots you are allowed to see.")
    with right:
        bar_chart(
            "Drawn exposure by customer",
            by_customer,
            note="Sum of stored HKD drawn amounts. Incomplete snapshots are excluded.",
            horizontal=True,
        )
    if not rows:
        return
    labels = [f"{row['legal_name']} — {row['name']} — {row['limit_status']}" for row in rows]
    choice = st.selectbox("Facility headline", labels)
    row = rows[labels.index(choice)]
    c1, c2, c3 = st.columns(3)
    c1.metric("Drawn", money(row.get("hkd_drawn")))
    c2.metric("Committed", money(row.get("hkd_committed")))
    c3.metric("Utilisation", "—" if row.get("utilisation_pct") is None else f"{row['utilisation_pct']}%")
    st.caption(
        f"{row.get('source_system')} · As at {format_date(row.get('as_of_date'))} · "
        f"Original currency {row.get('currency')} · {row.get('calculation_basis')}"
    )


def page_covenants(db, principal) -> None:
    st.title("Limits and Covenants")
    rows = analytics.covenants_view(db, principal)
    pie_chart("Status mix", _count(rows, "status"), note="Count of covenant and limit observations in the authorised book.")
    comparable = {
        f"{row['legal_name']} · {row.get('name')}": row.get("actual_value")
        for row in rows
        if row.get("actual_value") is not None and row.get("status") in {"breach", "near_breach", "Breach"}
    }
    bar_chart(
        "Actual values on breach or near-breach items",
        comparable,
        note="Actual observation only. Thresholds use different units and are not plotted on the same axis.",
        horizontal=True,
    )
    bullets(
        "Items requiring attention",
        [
            f"{row['legal_name']} — {row.get('name')} — {row.get('status')} as at {format_date(row.get('as_of_date'))}"
            for row in rows
            if str(row.get("status", "")).lower() in {"breach", "near_breach"}
        ],
    )


def page_collateral(db, principal) -> None:
    st.title("Collateral")
    rows = analytics.collateral_view(db, principal)
    bar_chart(
        "Eligible collateral (HKD)",
        {row["legal_name"]: row.get("hkd_amount") for row in rows},
        note="Stored HKD valuation. Collateral mitigates risk and is not deducted from exposure.",
        horizontal=True,
    )
    bar_chart(
        "Coverage of drawn exposure",
        {row["legal_name"]: row.get("coverage") for row in rows},
        note="Eligible collateral divided by drawn HKD. Below 1.00 means collateral does not cover drawn exposure. It does not eliminate risk.",
        horizontal=True,
    )
    bullets(
        "Coverage labels",
        [f"{row['legal_name']} — {row['coverage_label']}" for row in rows],
    )


def page_ewi(db, principal) -> None:
    st.title("Early-Warning Indicators")
    rows = analytics.ewi_view(db, principal)
    left, right = st.columns(2)
    with left:
        pie_chart("By status", _count(rows, "status"), note="Count of authorised early-warning indicators.")
    with right:
        pie_chart("By domain", _count(rows, "domain"), note="Risk domain recorded on the indicator.")
    bullets(
        "Open indicators",
        [f"{row['legal_name']} — {row.get('description')}" for row in rows if row.get("status") == "open"],
    )


def page_aml(db, principal) -> None:
    st.title("AML and Financial-Crime Indicators")
    view = analytics.aml_view(db, principal)
    if view["restricted"]:
        st.warning(view["message"])
        return
    st.info(view["message"])
    pie_chart(
        "Classification of customers with indicators",
        _count(view["rows"], "aml_risk_classification"),
        note="Count of customers shown on this page. This is not a suspicious-transaction recommendation.",
    )
    bullets(
        "Customers",
        [
            f"{row['legal_name']} — {row['aml_risk_classification']} — {len(row['alerts'])} indicator(s)"
            for row in view["rows"]
        ],
    )


def page_documents(db, principal) -> None:
    st.title("Trusted Documents")
    rows = analytics.documents_view(db, principal)
    if not rows:
        st.info("No authorised documents.")
        return
    left, right = st.columns(2)
    with left:
        pie_chart("Documents by risk domain", _count(rows, "risk_domain"), note="Count of documents you are allowed to open.")
    with right:
        pie_chart(
            "Current and superseded",
            {"Current": sum(1 for row in rows if not row.get("superseded")), "Superseded": sum(1 for row in rows if row.get("superseded"))},
            note="Superseded documents stay available for history and are not preferred for the current position.",
        )
    default = st.session_state.get("source_id", rows[0]["document_id"])
    ids = [row["document_id"] for row in rows]
    if default not in ids:
        default = ids[0]
    labels = {row["document_id"]: f"{row['title']} · {format_date(row.get('reporting_date'))}" for row in rows}
    document_id = st.selectbox("Open source", ids, index=ids.index(default), format_func=lambda item: labels.get(item, item))
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
        st.dataframe(pd.DataFrame(preview["rows"]), hide_index=True, width="stretch")
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
    st.title("Upload and Ingestion")
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
    st.title("Data Quality and Freshness")
    view = analytics.data_quality_view(db, principal)
    pie_chart(
        "Recorded issue types",
        _count(view["issues"], "issue_type") or _count(view["issues"], "category"),
        note="Count of data-quality issues in the authorised portfolio.",
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Recorded issues", len(view["issues"]))
    c2.metric("Unresolved snapshots", len(view["unresolved_snapshots"]))
    c3.metric("Stale documents", len(view["stale_documents"]))
    bullets(
        "Unresolved facility snapshots",
        [
            f"{row['customer_id']} · {row['facility_id']} · {row['data_quality']} · {format_date(row['as_of_date'])}"
            for row in view["unresolved_snapshots"]
        ],
    )
    bullets(
        "Ingestion exceptions",
        [f"{row['title']} — {row['status']}" for row in view["ingestion_exceptions"]],
    )


def page_evaluation(db, principal) -> None:
    st.title("RAG Evaluation")
    st.write("The evaluation uses the seeded questions. Results below are measured on this database, not assumed.")
    if principal.can("evaluation.run") and st.button("Run evaluation"):
        summary = run_evaluation(db)
        st.session_state["evaluation"] = summary
    if "evaluation" not in st.session_state:
        st.info("Run the evaluation to see retrieval, citation, abstention and authorisation scores.")
        return
    summary = st.session_state["evaluation"]
    headline = {key: value for key, value in summary.items() if key != "results"}
    bar_chart(
        "Cases passed and failed",
        {
            "Passed": sum(1 for item in summary["results"] if item["passed"]),
            "Failed": sum(1 for item in summary["results"] if not item["passed"]),
        },
        note="Count of seeded evaluation cases on this database.",
    )
    st.json(headline)
    bullets(
        "Case outcomes",
        [f"{item['id']} · {item['scenario']} — {'Pass' if item['passed'] else 'Fail'}" for item in summary["results"]],
    )


def page_governance(db, principal) -> None:
    st.title("AI Governance")
    view = analytics.governance_view(db, principal)
    st.write(view["intended_purpose"])
    st.write(f"System owner: {view['system_owner']}")
    st.write(f"Risk owner: {view['risk_owner']}")
    st.write(f"Periodic review date: {view['periodic_review_date']}")
    st.info(view["independent_validation"])
    st.write(view["training_data_declaration"])
    st.warning(view["residual_risks"])
    bullets("Model inventory", [f"{row['model_id']} — {row['purpose']} — {row['status']}" for row in view["models"]])
    bullets("Prohibited uses", [row["statement"] for row in view["prohibited_uses"]])
    bullets("Risk taxonomy", [f"{row['name']} — {row['owner_function']}" for row in view["taxonomy"]])
    bullets(
        "AI incidents",
        [f"{row['incident_id']} — {row['severity']} — {row['status']}" for row in view["incidents"]],
    )
    if not view["incidents"]:
        st.caption("No demonstration incidents are open. The register exists so an incident can be recorded.")


def page_audit(db, principal) -> None:
    st.title("Audit Activity")
    rows = analytics.audit_view(db, principal)
    bar_chart(
        "Events by type",
        _count(rows, "event_type"),
        note="Count of the latest audit events you are allowed to read. The log is not editable from this page.",
    )
    pie_chart("Outcomes", _count(rows, "outcome"), note="Allowed and denied outcomes in the same extract.")
    bullets(
        "Latest events",
        [
            f"{format_date(row['created_at'])} · {row['username'] or 'unknown'} · {row['event_type']} · {row['outcome']}"
            for row in rows[:12]
        ],
    )


def page_admin(db, principal) -> None:
    st.title("Administration")
    view = analytics.admin_view(db, principal)
    if view["users"]:
        pie_chart("Users by role", _count(view["users"], "role"), note="Demonstration accounts. No production identity provider.")
        bullets(
            "Accounts",
            [f"{row['username']} — {row['display_name']} — {row['role']}" for row in view["users"]],
        )
    bullets("Controls", [f"{row['key']} = {row['value']}" for row in view["controls"]])
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
        "Facilities and Exposure": page_facilities,
        "Limits and Covenants": page_covenants,
        "Collateral": page_collateral,
        "Early-Warning Indicators": page_ewi,
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
