"""Build the demonstration book from the seeded synthetic customers."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_CANDIDATES = [
    Path("/tmp/rip/risk-intelligence-platform/data/harbour_meridian.db"),
    ROOT.parent / "data" / "harbour_meridian.db",
]
OUT = ROOT / "book.json"
AS_OF = "2026-09-30"
THRESHOLD = 5_000_000
NOTIFY = "credit.desk@hkbea.example"

PD = {1: 0.002, 2: 0.004, 3: 0.008, 4: 0.015, 5: 0.035, 6: 0.07, 7: 0.12}
LGD = 0.45
COLLATERAL_TYPES = ["Receivables", "Deposit", "Commercial property", "Guarantee"]


def stage_of(rating: int) -> int:
    if rating >= 7:
        return 3
    if rating >= 5:
        return 2
    return 1


def money(n: float | int | None) -> str:
    if n is None:
        return "—"
    return f"HKD {n:,.0f}"


def connect() -> sqlite3.Connection:
    for path in DB_CANDIDATES:
        if path.exists():
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            return conn
    raise SystemExit("Synthetic database not found. Seed the platform before building the book.")


def latest_exposure(conn: sqlite3.Connection) -> dict[str, dict]:
    as_of = conn.execute("SELECT MAX(as_of_date) FROM facility_snapshots").fetchone()[0]
    rows = conn.execute(
        """
        SELECT customer_id,
               SUM(CASE WHEN data_quality='ok' THEN COALESCE(hkd_drawn, 0) ELSE 0 END) AS drawn,
               SUM(CASE WHEN data_quality='ok' THEN COALESCE(hkd_committed, 0) ELSE 0 END) AS committed
        FROM facility_snapshots
        WHERE as_of_date = ?
        GROUP BY customer_id
        """,
        (as_of,),
    )
    return {row["customer_id"]: {"drawn": row["drawn"] or 0, "committed": row["committed"] or 0} for row in rows}


def ratings(conn: sqlite3.Connection) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for row in conn.execute(
        "SELECT customer_id, as_of_date, rating FROM rating_history ORDER BY customer_id, as_of_date"
    ):
        slot = found.setdefault(row["customer_id"], {"current": row["rating"], "prior": row["rating"], "prior_date": row["as_of_date"]})
        if row["as_of_date"] == "2025-04-30":
            slot["prior"] = row["rating"]
            slot["prior_date"] = row["as_of_date"]
        slot["current"] = row["rating"]
        slot["current_date"] = row["as_of_date"]
    return found


def build() -> dict:
    conn = connect()
    exposure = latest_exposure(conn)
    rating = ratings(conn)
    ewi_rows = list(conn.execute("SELECT * FROM early_warning_indicators"))
    ewi_by = {}
    for row in ewi_rows:
        ewi_by.setdefault(row["customer_id"], []).append(
            {
                "code": row["indicator_code"],
                "description": row["description"],
                "status": row["status"],
                "observed": row["observed_value"],
            }
        )
    customers = []
    for row in conn.execute(
        """
        SELECT c.customer_id, c.legal_name, c.industry, c.jurisdiction, c.relationship_manager,
               c.group_id, g.name AS group_name, c.business_summary, c.watchlist_status
        FROM customers c JOIN customer_groups g ON g.group_id = c.group_id
        ORDER BY c.legal_name
        """
    ):
        cid = row["customer_id"]
        exp = exposure.get(cid, {"drawn": 0, "committed": 0})
        rat = rating.get(cid, {"current": 5, "prior": 5, "prior_date": "2025-04-30", "current_date": AS_OF})
        current = int(rat["current"])
        prior = int(rat["prior"])
        drawn = float(exp["drawn"])
        committed = float(exp["committed"])
        customers.append(
            {
                "customer_id": cid,
                "legal_name": row["legal_name"],
                "industry": row["industry"],
                "jurisdiction": row["jurisdiction"],
                "rm": row["relationship_manager"].replace(" (synthetic staff)", ""),
                "group_id": row["group_id"],
                "group_name": row["group_name"],
                "summary": row["business_summary"],
                "watchlist": row["watchlist_status"],
                "drawn_hkd": drawn,
                "committed_hkd": committed,
                "rating": current,
                "prior_rating": prior,
                "prior_rating_date": rat.get("prior_date", "2025-04-30"),
                "stage": stage_of(current),
                "prior_stage": stage_of(prior),
                "warnings": ewi_by.get(cid, []),
            }
        )
    enrich(customers)
    industries = rollup_industries(customers)
    news = news_items(customers)
    drafts = email_drafts(customers, industries, news)
    book = {
        "as_of": AS_OF,
        "threshold_hkd": THRESHOLD,
        "notify_to": NOTIFY,
        "banner": "SYNTHETIC HACKATHON DATA - NOT FOR CUSTOMER, CREDIT, COMPLIANCE, RISK, REGULATORY OR BUSINESS DECISION-MAKING",
        "customers": customers,
        "industries": industries,
        "news": news,
        "drafts": drafts,
        "portfolio": portfolio(customers),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(book, indent=2), encoding="utf-8")
    print(f"wrote {OUT} customers={len(customers)} drafts={len(drafts)}")
    return book


def enrich(customers: list[dict]) -> None:
    """Fill demonstration fields. The three worked examples keep a written story."""
    stories = {
        "CUS-AHTL-0001": {
            "dpd": 0,
            "dpd_component": "none",
            "collateral_type": "Receivables",
            "collateral_hkd": 36_000_000,
            "guarantor": None,
            "revenue_hkd": [420_000_000, 390_000_000, 348_000_000],
            "margin_pct": [11.4, 9.8, 7.6],
            "liquidity_ratio": [1.45, 1.22, 1.05],
            "leverage": [1.8, 2.2, 2.7],
            "interest_coverage": [3.1, 2.4, 2.2],
            "coverage_assumption": 2.5,
            "coverage_threshold": 2.0,
            "next_due_days": 74,
            "next_due_hkd": 12_000_000,
            "next_due_source": "Credit proposal",
            "refinancing": True,
        },
        "CUS-LFLL-0003": {
            "dpd": 22,
            "dpd_component": "interest",
            "collateral_type": "Deposit",
            "collateral_hkd": 18_000_000,
            "guarantor": "Lantern Ferry Holdings Limited",
            "revenue_hkd": [210_000_000, 206_000_000, 198_000_000],
            "margin_pct": [8.2, 7.9, 7.1],
            "liquidity_ratio": [1.40, 1.22, 1.05],
            "leverage": [2.1, 2.3, 2.6],
            "interest_coverage": [2.8, 2.5, 2.3],
            "coverage_assumption": 2.5,
            "coverage_threshold": 2.0,
            "next_due_days": 18,
            "next_due_hkd": 8_000_000,
            "next_due_source": "Watchlist",
            "refinancing": False,
        },
        "CUS-RBFL-0013": {
            "dpd": 0,
            "dpd_component": "none",
            "collateral_type": "Receivables",
            "collateral_hkd": 7_500_000,
            "guarantor": None,
            "revenue_hkd": [96_000_000, 88_000_000, 74_000_000],
            "margin_pct": [9.0, 7.4, 5.5],
            "liquidity_ratio": [1.30, 1.15, 1.02],
            "leverage": [2.4, 2.8, 3.3],
            "interest_coverage": [2.2, 1.9, 1.6],
            "coverage_assumption": 2.2,
            "coverage_threshold": 2.0,
            "next_due_days": 40,
            "next_due_hkd": 6_500_000,
            "next_due_source": "Credit proposal",
            "refinancing": True,
        },
    }
    dpd_cycle = [0, 0, 0, 0, 0, 0, 12, 18, 27, 34, 66, 95]
    collateral_cycle = COLLATERAL_TYPES
    for index, customer in enumerate(customers):
        story = stories.get(customer["customer_id"])
        if story:
            customer.update(story)
        else:
            customer["dpd"] = dpd_cycle[index % len(dpd_cycle)]
            customer["dpd_component"] = "principal" if customer["dpd"] else "none"
            customer["collateral_type"] = collateral_cycle[index % len(collateral_cycle)]
            customer["collateral_hkd"] = round(customer["drawn_hkd"] * (0.35 + (index % 5) * 0.12), 0)
            customer["guarantor"] = None
            base = max(customer["drawn_hkd"] * 4, 20_000_000)
            customer["revenue_hkd"] = [round(base * 1.08, 0), round(base, 0), round(base * 0.94, 0)]
            customer["margin_pct"] = [8.5, 8.0, 7.4]
            customer["liquidity_ratio"] = [1.5, 1.4, 1.3]
            customer["leverage"] = [1.6, 1.7, 1.8]
            customer["interest_coverage"] = [3.0, 2.8, 2.6]
            customer["coverage_assumption"] = 2.5
            customer["coverage_threshold"] = 2.0
            customer["next_due_days"] = 20 + (index * 7) % 120
            customer["next_due_hkd"] = round(max(customer["drawn_hkd"] * 0.08, 400_000), 0)
            customer["next_due_source"] = "Credit proposal" if index % 2 == 0 else "Watchlist"
            customer["refinancing"] = customer["next_due_days"] <= 90 and customer["next_due_hkd"] >= THRESHOLD
        drawn = customer["drawn_hkd"]
        customer["ecl_hkd"] = round(drawn * PD.get(customer["rating"], 0.04) * LGD, 0)
        prior_pd = PD.get(customer["prior_rating"], 0.04)
        customer["prior_ecl_hkd"] = round(drawn * prior_pd * LGD * 0.9, 0)
        customer["provision_hkd"] = customer["ecl_hkd"]
        customer["ltv"] = round(drawn / customer["collateral_hkd"], 2) if customer["collateral_hkd"] else None
        customer["coverage_ratio"] = round(customer["collateral_hkd"] / drawn, 2) if drawn else None
        customer["full_file"] = customer["customer_id"] in stories
        customer["documents"] = documents_for(customer)


def documents_for(customer: dict) -> dict:
    name = customer["legal_name"]
    cid = customer["customer_id"]
    revenue = customer["revenue_hkd"]
    return {
        "credit_paper": {
            "title": f"Credit paper — {name}",
            "locator": "page 4",
            "passage": (
                f"Approved interest-coverage covenant is at least {customer['coverage_threshold']:.1f} times. "
                f"The credit assumption used at approval was {customer['coverage_assumption']:.1f} times. "
                f"Group {customer['group_name']}."
            ),
        },
        "review": {
            "title": f"Credit review — {name}",
            "locator": "30 Sep 2026, section 2",
            "passage": (
                f"Internal rating moved from {customer['prior_rating']} on {customer['prior_rating_date']} "
                f"to {customer['rating']} on 30 Sep 2026. "
                + (
                    "The review records weaker cash flow and higher revolving utilisation."
                    if cid == "CUS-AHTL-0001"
                    else "The review records the latest financial extracts and repayment status."
                )
            ),
        },
        "financials": {
            "title": f"Financial statements extract — {name}",
            "locator": "income statement, three year-ends",
            "passage": (
                f"Revenue HKD {revenue[0]:,.0f}, {revenue[1]:,.0f}, {revenue[2]:,.0f}. "
                f"Margin {customer['margin_pct'][0]:.1f}%, {customer['margin_pct'][1]:.1f}%, {customer['margin_pct'][2]:.1f}%. "
                f"Interest coverage {customer['interest_coverage'][0]:.1f}x, {customer['interest_coverage'][1]:.1f}x, {customer['interest_coverage'][2]:.1f}x."
            ),
        },
        "repayment": {
            "title": f"Repayment schedule — {name}",
            "locator": customer["next_due_source"],
            "passage": (
                f"Next obligation HKD {customer['next_due_hkd']:,.0f} in {customer['next_due_days']} days, "
                f"sourced from the {customer['next_due_source'].lower()}. "
                f"Days past due: {customer['dpd']} ({customer['dpd_component']})."
            ),
        },
    }


def dpd_bucket(dpd: int) -> str:
    if dpd <= 0:
        return "Current"
    if dpd < 30:
        return "1–29"
    if dpd < 60:
        return "30–59"
    if dpd < 90:
        return "60–89"
    if dpd < 180:
        return "90–179"
    return "180+"


def rollup_industries(customers: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for customer in customers:
        grouped.setdefault(customer["industry"], []).append(customer)
    rows = []
    for industry, members in grouped.items():
        drawn = sum(member["drawn_hkd"] for member in members)
        rows.append(
            {
                "industry": industry,
                "customers": len(members),
                "drawn_hkd": drawn,
                "stage2": sum(1 for member in members if member["stage"] >= 2),
                "migrations": sum(1 for member in members if member["stage"] > member["prior_stage"]),
                "open_warnings": sum(len(member["warnings"]) for member in members),
                "dpd_accounts": sum(1 for member in members if member["dpd"] > 0),
                "collateral_hkd": sum(member["collateral_hkd"] for member in members),
            }
        )
    rows.sort(key=lambda item: item["drawn_hkd"], reverse=True)
    return rows


def portfolio(customers: list[dict]) -> dict:
    drawn = sum(customer["drawn_hkd"] for customer in customers)
    ecl = sum(customer["ecl_hkd"] for customer in customers)
    prior_ecl = sum(customer["prior_ecl_hkd"] for customer in customers)
    buckets = ["Current", "1–29", "30–59", "60–89", "90–179", "180+"]
    dpd = {bucket: {"count": 0, "drawn_hkd": 0} for bucket in buckets}
    stages = {1: {"count": 0, "drawn_hkd": 0}, 2: {"count": 0, "drawn_hkd": 0}, 3: {"count": 0, "drawn_hkd": 0}}
    collateral: dict[str, float] = {}
    maturity = {"month": 0.0, "quarter": 0.0, "later": 0.0}
    large_due = []
    for customer in customers:
        bucket = dpd_bucket(customer["dpd"])
        dpd[bucket]["count"] += 1
        dpd[bucket]["drawn_hkd"] += customer["drawn_hkd"]
        stages[customer["stage"]]["count"] += 1
        stages[customer["stage"]]["drawn_hkd"] += customer["drawn_hkd"]
        collateral[customer["collateral_type"]] = collateral.get(customer["collateral_type"], 0) + customer["collateral_hkd"]
        amount = customer["next_due_hkd"]
        if customer["next_due_days"] <= 30:
            maturity["month"] += amount
        elif customer["next_due_days"] <= 90:
            maturity["quarter"] += amount
        else:
            maturity["later"] += amount
        if amount >= THRESHOLD and customer["next_due_days"] <= 90:
            large_due.append(customer["customer_id"])
    return {
        "customers": len(customers),
        "drawn_hkd": drawn,
        "ecl_hkd": ecl,
        "prior_ecl_hkd": prior_ecl,
        "ecl_coverage": round(ecl / drawn, 4) if drawn else None,
        "migrations": sum(1 for customer in customers if customer["stage"] > customer["prior_stage"]),
        "stages": stages,
        "dpd": dpd,
        "collateral": collateral,
        "maturity": maturity,
        "large_due": large_due,
        "overdue_reviews": 3,
        "open_warnings": sum(len(customer["warnings"]) for customer in customers),
    }


def news_items(customers: list[dict]) -> list[dict]:
    by_id = {customer["customer_id"]: customer for customer in customers}
    apex = by_id["CUS-AHTL-0001"]
    return [
        {
            "id": "NEWS-APEX-DIST",
            "headline": "Mainland distributor receipts reported about six weeks slower",
            "source": "Credit Risk Alert Portal (demonstration feed)",
            "date": "18 Sep 2026",
            "customer_id": apex["customer_id"],
            "industry": apex["industry"],
            "body": "A trade note says a named distributor is paying Apex Harbour Trading about six weeks late. The note does not state a loss amount.",
            "factors": materiality(apex, direct_hit=True),
        },
        {
            "id": "NEWS-WHOLESALE-TRADE",
            "headline": "Trade friction is slowing orders across consumer-goods wholesalers",
            "source": "Credit Risk Alert Portal (demonstration feed)",
            "date": "2 Oct 2026",
            "customer_id": None,
            "industry": "Wholesale trade",
            "body": "Sector reporting describes weaker order books for consumer-goods wholesalers. It does not name a default.",
            "factors": {
                "exposure_hkd": sum(c["drawn_hkd"] for c in customers if c["industry"] == "Wholesale trade"),
                "security_coverage": "mixed across the industry book",
                "guarantor_support": "not an industry-level fact",
                "financial_strength": "two wholesale names are rating 6",
                "warning_signals": "open rating and utilisation warnings at Apex Harbour Trading",
                "score": 72,
                "material": True,
            },
        },
        {
            "id": "NEWS-SMALL-MENTION",
            "headline": "Unnamed blog mentions a small marine supplier",
            "source": "Credit Risk Alert Portal (demonstration feed)",
            "date": "5 Oct 2026",
            "customer_id": "CUS-G042",
            "industry": "Marine supplies",
            "body": "The item does not name a payment default, a rating action, or a figure.",
            "factors": materiality(by_id["CUS-G042"], direct_hit=False),
        },
    ]


def materiality(customer: dict, direct_hit: bool) -> dict:
    coverage = customer.get("coverage_ratio") or 0
    score = 0
    if customer["drawn_hkd"] >= 50_000_000:
        score += 25
    elif customer["drawn_hkd"] >= 10_000_000:
        score += 15
    else:
        score += 5
    if coverage < 0.5:
        score += 20
    elif coverage < 0.8:
        score += 10
    if not customer.get("guarantor"):
        score += 10
    if customer["rating"] >= 6:
        score += 15
    elif customer["rating"] >= 5:
        score += 8
    score += min(20, 10 * len(customer["warnings"]))
    if not direct_hit:
        score = min(score, 24)
    return {
        "exposure_hkd": customer["drawn_hkd"],
        "security_coverage": coverage,
        "guarantor_support": customer.get("guarantor") or "none on file",
        "financial_strength": f"rating {customer['rating']}",
        "warning_signals": len(customer["warnings"]),
        "score": score,
        "material": score >= 50,
    }


def email_drafts(customers: list[dict], industries: list[dict], news: list[dict]) -> list[dict]:
    by_id = {customer["customer_id"]: customer for customer in customers}
    apex = by_id["CUS-AHTL-0001"]
    lantern = by_id["CUS-LFLL-0003"]
    wholesale = next(row for row in industries if row["industry"] == "Wholesale trade")
    drafts = [
        letter_news(apex, news[0]),
        letter_industry(wholesale),
        letter_repayment(lantern),
        letter_dpd(lantern),
        letter_covenant(apex, "revenue_decline"),
    ]
    return drafts


def letter_header(subject: str) -> str:
    return (
        f"To: {NOTIFY}\n"
        f"Subject: {subject}\n\n"
        "SYNTHETIC HACKATHON DATA - NOT FOR CUSTOMER, CREDIT, COMPLIANCE, RISK, REGULATORY OR BUSINESS DECISION-MAKING\n\n"
    )


def letter_news(customer: dict, item: dict) -> dict:
    factors = item["factors"]
    body = letter_header(f"[Demonstration] Adverse news — {customer['legal_name']}")
    body += f"""Dear colleague,

This is a demonstration alert generated from the synthetic book as at 30 Sep 2026. It is addressed to {NOTIFY} so it can be sent on manually. It is not a credit decision.

News
{item['date']}. {item['headline']}.
Source: {item['source']}.
{item['body']}

Materiality
The item is treated as material because the score is {factors['score']}.
Exposure: {money(factors['exposure_hkd'])}.
Security coverage: {factors['security_coverage']}.
Guarantor: {factors['guarantor_support']}.
Financial strength: {factors['financial_strength']}.
Open warning signals: {factors['warning_signals']}.

Credit implication
The onshore borrower remains the named customer in {customer['industry']}. Slower receipts tighten cash available for the revolving facility. Drawn exposure is {money(customer['drawn_hkd'])}. Collateral of type {customer['collateral_type']} is {money(customer['collateral_hkd'])}. Coverage does not eliminate the exposure.

Follow-up for the relationship manager ({customer['rm']})
Ask for a monthly receivable ageing and identify whether the named distributor is the same debtor supporting the receivable charge. Bring the result to the next review. Do not treat this note as an instruction to downgrade, to call default, or to exit the relationship.

Risk Intelligence Platform
"""
    return {"id": "MAIL-NEWS-APEX", "kind": "Adverse news", "subject": f"Adverse news — {customer['legal_name']}", "customer_id": customer["customer_id"], "body": body}


def letter_industry(industry: dict) -> dict:
    body = letter_header("[Demonstration] Industry review — Wholesale trade")
    body += f"""Dear colleague,

This is a demonstration industry alert for the synthetic portfolio as at 30 Sep 2026.

What is rising
Wholesale trade has {industry['customers']} customers and drawn exposure of {money(industry['drawn_hkd'])}.
Stage 2 names: {industry['stage2']}.
Rating migrations this period: {industry['migrations']}.
Open warning signals: {industry['open_warnings']}.
Accounts with days past due: {industry['dpd_accounts']}.
A sector note on 2 Oct 2026 describes slower orders. Apex Harbour Trading also has a named-distributor receipt delay dated 18 Sep 2026.

Effect on the book
The industry is large enough, and two names are already rating 6, that the signals are material to the portfolio rather than a single keyword hit. Collateral recorded against the industry is {money(industry['collateral_hkd'])}.

Recommended review
Open a wholesale-trade portfolio review. Start with Apex Harbour Trading and Repulse Bay Furnishings. Confirm receivable performance, interest-coverage headroom, and any repayment above HKD 5,000,000 inside the next quarter.

Risk Intelligence Platform
"""
    return {"id": "MAIL-IND-WHOLESALE", "kind": "Industry stress", "subject": "Industry review — Wholesale trade", "customer_id": None, "body": body}


def letter_repayment(customer: dict) -> dict:
    body = letter_header(f"[Demonstration] Large repayment — {customer['legal_name']}")
    body += f"""Dear colleague,

This is a demonstration repayment alert as at 30 Sep 2026.

Obligation
{customer['legal_name']} ({customer['customer_id']}) has a repayment of {money(customer['next_due_hkd'])} due in {customer['next_due_days']} days.
Source of the date and amount: {customer['next_due_source']}.
The monitoring threshold is HKD 5,000,000. This obligation is above that threshold and falls inside the next month.
Relationship manager: {customer['rm']}.
Drawn exposure: {money(customer['drawn_hkd'])}.

Funding
The latest liquidity ratio on file is {customer['liquidity_ratio'][-1]:.2f}, against 1.20 in the early-warning description for this name. Cash and deposits have been falling in the synthetic history. The alert asks the relationship manager to contact the borrower and confirm where the repayment will be funded. It does not waive the instalment and it does not extend the maturity.

Risk Intelligence Platform
"""
    return {"id": "MAIL-REPAY-LANTERN", "kind": "Large repayment", "subject": f"Large repayment — {customer['legal_name']}", "customer_id": customer["customer_id"], "body": body}


def letter_dpd(customer: dict) -> dict:
    body = letter_header(f"[Demonstration] Ageing reminder — {customer['legal_name']}")
    body += f"""Dear colleague,

This is a demonstration ageing reminder as at 30 Sep 2026.

Position
{customer['legal_name']} has {customer['dpd']} days past due on {customer['dpd_component']}.
The next threshold in the reminder schedule is 30 days. The account has not reached 60, 90, or 180 days.
Drawn exposure: {money(customer['drawn_hkd'])}. Rating: {customer['rating']}.

Action
Ask the relationship manager ({customer['rm']}) to confirm whether the interest arrears will clear before day 30, and to reassess the borrower grade if it does not. This reminder does not change the grade by itself.

Risk Intelligence Platform
"""
    return {"id": "MAIL-DPD-LANTERN", "kind": "Days past due", "subject": f"Ageing reminder — {customer['legal_name']}", "customer_id": customer["customer_id"], "body": body}


def letter_covenant(customer: dict, scenario: str) -> dict:
    projected = project_coverage(customer, scenario)
    body = letter_header(f"[Demonstration] Covenant headroom — {customer['legal_name']}")
    body += f"""Dear colleague,

This is a demonstration covenant alert as at 30 Sep 2026. The scenario is stated. It is not a forecast promise.

Current test
Interest coverage covenant: at least {customer['coverage_threshold']:.1f} times.
Credit assumption at approval: {customer['coverage_assumption']:.1f} times.
Latest extracted coverage: {customer['interest_coverage'][-1]:.1f} times.
Status today: {"inside the covenant" if customer['interest_coverage'][-1] >= customer['coverage_threshold'] else "outside the covenant"}.

Scenario
Revenue decline of 15 percent, using the trade-friction news as the reason to run the case, with margin and funding cost held at the latest extract.
Projected interest coverage: {projected:.1f} times.
Headroom against the {customer['coverage_threshold']:.1f} times threshold: {projected - customer['coverage_threshold']:+.1f} times.
Principal driver: lower revenue through the coverage ratio. Collateral and the guarantee, if any, are not restated by this scenario.

Follow-up
Ask {customer['rm']} to review management accounts and the receivable ageing before the next test date. The monitoring plan is a recommendation. It is not a credit approval.

Risk Intelligence Platform
"""
    return {"id": "MAIL-COV-APEX", "kind": "Covenant scenario", "subject": f"Covenant headroom — {customer['legal_name']}", "customer_id": customer["customer_id"], "body": body}


def project_coverage(customer: dict, scenario: str) -> float:
    current = customer["interest_coverage"][-1]
    shifts = {
        "base": 0.0,
        "revenue_decline": -0.6,
        "margin_compression": -0.4,
        "funding_cost": -0.3,
        "liquidity": -0.2,
    }
    return round(current + shifts.get(scenario, 0.0), 1)


if __name__ == "__main__":
    build()
