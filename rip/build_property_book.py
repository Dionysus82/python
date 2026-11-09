"""Fill the Tiffany business-case book from the property collateral and cash flow extracts."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ASOF = "30/09/2026"
PRIOR = "31/08/2026"
THRESHOLD = 5_000_000
COLL = Path("/workspace/rip/property_data/COLLATERAL_ALL_2026.csv")
FLOW = Path("/workspace/rip/property_data/CASH_FLOW_ALL_2026.csv")
OUT = Path(__file__).resolve().parent / "book.json"

GOVERNMENT = {"Metro Gov Authority A", "State Treasury Bureau B"}


def parse_date(text: str):
    return datetime.strptime(text, "%d/%m/%Y")


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def money_words(value: float) -> str:
    return f"HKD {value:,.0f}"


def industry_name(borrower: str) -> str:
    if borrower in GOVERNMENT:
        return "Government"
    return "Property investment"


def main() -> None:
    collateral = load(COLL)
    flows = load(FLOW)
    current = [row for row in collateral if row["REPORTING_DATE"] == ASOF]
    prior_rows = [row for row in collateral if row["REPORTING_DATE"] == PRIOR]
    prior_bal = defaultdict(float)
    for row in prior_rows:
        if row["INSTRUMENT"] == "Customer Loan":
            prior_bal[row["BORROWER_NAME"]] += float(row["BAL_OUTSTD_HKD"])

    terms = {}
    by_contract = defaultdict(list)
    grades_by_month = defaultdict(dict)
    for row in flows:
        grades_by_month[row["REPORTING_DATE"]][row["CONTRACT_REFERENCE"]] = row["CURRENT_PD_GRADE"]
        if row["REPORTING_DATE"] != ASOF:
            continue
        terms[row["CONTRACT_REFERENCE"]] = row
        by_contract[row["CONTRACT_REFERENCE"]].append(row)
    for rows in by_contract.values():
        rows.sort(key=lambda item: parse_date(item["CASH_FLOW_DATE"]))
    grade_drift = [
        ref
        for ref, grade in grades_by_month[ASOF].items()
        if grades_by_month[PRIOR].get(ref) not in (None, grade)
    ]
    if grade_drift:
        raise RuntimeError(f"grade changed for {grade_drift[:5]}")

    grouped = defaultdict(list)
    for row in current:
        grouped[row["BORROWER_NAME"]].append(row)

    customers = []
    reporting = parse_date(ASOF)
    for borrower, rows in grouped.items():
        loans = [row for row in rows if row["INSTRUMENT"] == "Customer Loan"]
        off = [row for row in rows if row["INSTRUMENT"] != "Customer Loan"]
        drawn = sum(float(row["BAL_OUTSTD_HKD"]) for row in loans)
        market = sum(float(row["MARKET_VALUE_HKD"]) for row in loans)
        net = sum(float(row["NET_REALIZABLE_VALUE_HKD"]) for row in loans)
        off_market = sum(float(row["MARKET_VALUE_HKD"]) for row in off)
        grade = int(terms[loans[0]["CONTRACT_REFERENCE"]]["CURRENT_PD_GRADE"])
        next_principal = None
        for loan in loans:
            ref = loan["CONTRACT_REFERENCE"]
            term = terms[ref]
            for flow in by_contract[ref]:
                if flow["CASH_FLOW_TYPE"] != "N" or float(flow["CASH_FLOW_AMOUNT"]) <= 0:
                    continue
                days = (parse_date(flow["CASH_FLOW_DATE"]) - reporting).days
                candidate = {
                    "days": days,
                    "amount": float(flow["CASH_FLOW_AMOUNT"]),
                    "date": flow["CASH_FLOW_DATE"],
                    "contract": ref,
                    "method": term["AMORTIZATION_METHOD"],
                    "rate": float(term["DISCOUNT_RATE"]),
                }
                if next_principal is None or (candidate["days"], -candidate["amount"]) < (
                    next_principal["days"],
                    -next_principal["amount"],
                ):
                    next_principal = candidate
                break
        if next_principal is None:
            raise RuntimeError(f"no principal for {borrower}")
        addresses = [
            f"{row['COLLATERAL_REFERENCE']} {row['PROPERTY_ADDRESS']} ({row['COLLATERAL_TYPE']}, market {money_words(float(row['MARKET_VALUE_HKD']))})"
            for row in loans
        ]
        coverage = round(market / drawn, 2) if drawn else None
        ltv = round(drawn / market, 2) if market else None
        prior = prior_bal[borrower]
        slug = "BOR-" + "".join(word[0] for word in borrower.replace(".", "").split())[:12]
        customers.append(
            {
                "customer_id": slug,
                "legal_name": borrower,
                "group_id": slug,
                "group_name": borrower,
                "rm": f"{len(loans)} on-balance facilities",
                "industry": industry_name(borrower),
                "jurisdiction": "Hong Kong",
                "rating": grade,
                "prior_rating": grade,
                "prior_rating_date": "31/01/2026",
                "stage": 1,
                "prior_stage": 1,
                "drawn_hkd": round(drawn, 2),
                "committed_hkd": round(drawn, 2),
                "collateral_hkd": round(market, 2),
                "collateral_type": "Residential and commercial property",
                "coverage_ratio": coverage,
                "ltv": ltv,
                "guarantor": "None on the extract",
                "dpd": 0,
                "dpd_component": "None",
                "ecl_hkd": 0,
                "prior_ecl_hkd": 0,
                "provision_hkd": 0,
                "revenue_hkd": [None, None, None],
                "margin_pct": [None, None, None],
                "liquidity_ratio": [None, None, None],
                "leverage": [None, None, None],
                "interest_coverage": [None, None, None],
                "coverage_assumption": None,
                "coverage_threshold": None,
                "next_due_days": next_principal["days"],
                "next_due_hkd": round(next_principal["amount"], 2),
                "next_due_date": next_principal["date"],
                "next_due_source": "Cash flow schedule",
                "next_contract": next_principal["contract"],
                "next_method": next_principal["method"],
                "refinancing": next_principal["method"] == "BULLET" and next_principal["days"] <= 90,
                "watchlist": False,
                "warnings": [],
                "full_file": True,
                "summary": (
                    f"{borrower} has {len(loans)} on-balance facilities totalling {money_words(drawn)} "
                    f"and {len(off)} off-balance facilities with property market value {money_words(off_market)}. "
                    f"On-balance market value is {money_words(market)} and net realizable value is {money_words(net)}. "
                    f"LTV is {ltv:.2f}. Grade {grade} is unchanged since 31 Jan 2026. "
                    f"Outstanding on 31 Aug 2026 was {money_words(prior)}."
                ),
                "documents": documents(borrower, grade, drawn, market, net, ltv, addresses, next_principal, prior),
                "repay_draft_id": "",
            }
        )

    customers.sort(key=lambda item: item["drawn_hkd"], reverse=True)
    apply_virtual(customers)
    large = [
        item for item in customers if item["next_due_hkd"] >= THRESHOLD and item["next_due_days"] <= 90
    ]
    large.sort(key=lambda item: (-item["next_due_hkd"], item["next_due_days"]))
    if large:
        large[0]["repay_draft_id"] = "MAIL-REPAY-LANTERN"

    industries = []
    for name in sorted({item["industry"] for item in customers}):
        members = [item for item in customers if item["industry"] == name]
        industries.append(
            {
                "industry": name,
                "customers": len(members),
                "drawn_hkd": round(sum(item["drawn_hkd"] for item in members), 2),
                "stage2": sum(1 for item in members if item["stage"] == 2),
                "migrations": sum(1 for item in members if item["stage"] > item["prior_stage"]),
                "open_warnings": sum(len(item["warnings"]) for item in members),
                "dpd_accounts": sum(1 for item in members if item["dpd"] > 0),
                "collateral_hkd": round(sum(item["collateral_hkd"] for item in members), 2),
            }
        )
    industries.sort(key=lambda item: item["drawn_hkd"], reverse=True)

    drawn = sum(item["drawn_hkd"] for item in customers)
    collateral_split = defaultdict(float)
    for row in current:
        if row["INSTRUMENT"] == "Customer Loan":
            collateral_split[row["COLLATERAL_TYPE"]] += float(row["MARKET_VALUE_HKD"])
    maturity = {"month": 0.0, "quarter": 0.0, "later": 0.0}
    for item in customers:
        amount = item["next_due_hkd"]
        if item["next_due_days"] <= 30:
            maturity["month"] += amount
        elif item["next_due_days"] <= 90:
            maturity["quarter"] += amount
        else:
            maturity["later"] += amount
    ecl = round(sum(item["ecl_hkd"] for item in customers), 2)
    prior_ecl = round(sum(item["prior_ecl_hkd"] for item in customers), 2)
    stages = {}
    for key in (1, 2, 3):
        members = [item for item in customers if item["stage"] == key]
        stages[str(key)] = {
            "count": len(members),
            "drawn_hkd": round(sum(item["drawn_hkd"] for item in members), 2),
        }
    dpd_bands = (
        ("Current", lambda days: days == 0),
        ("1–29", lambda days: 1 <= days <= 29),
        ("30–59", lambda days: 30 <= days <= 59),
        ("60–89", lambda days: 60 <= days <= 89),
        ("90–179", lambda days: 90 <= days <= 179),
        ("180+", lambda days: days >= 180),
    )
    dpd = {}
    for name, test in dpd_bands:
        members = [item for item in customers if test(item["dpd"])]
        dpd[name] = {
            "count": len(members),
            "drawn_hkd": round(sum(item["drawn_hkd"] for item in members), 2),
        }
    portfolio = {
        "customers": len(customers),
        "facilities_on_balance": sum(1 for row in current if row["INSTRUMENT"] == "Customer Loan"),
        "drawn_hkd": round(drawn, 2),
        "ecl_hkd": ecl,
        "prior_ecl_hkd": prior_ecl,
        "ecl_coverage": round(ecl / drawn, 4) if drawn else 0,
        "migrations": sum(1 for item in customers if item["stage"] > item["prior_stage"]),
        "stages": stages,
        "dpd": dpd,
        "collateral": {key: round(value, 2) for key, value in collateral_split.items()},
        "maturity": {key: round(value, 2) for key, value in maturity.items()},
        "large_due": [item["customer_id"] for item in customers if item["next_due_hkd"] >= THRESHOLD and item["next_due_days"] <= 90],
        "overdue_reviews": sum(1 for item in customers if item["dpd"] >= 30),
        "open_warnings": sum(len(item["warnings"]) for item in customers),
    }
    focus = next(item for item in customers if item["repay_draft_id"])
    news = news_items(customers)
    book = {
        "as_of": "2026-09-30",
        "as_of_label": "30 Sep 2026",
        "threshold_hkd": THRESHOLD,
        "notify_to": "yiyangyao2@gmail.com",
        "default_customer_id": customers[0]["customer_id"],
        "default_industry": industries[0]["industry"],
        "banner": (
            "SYNTHETIC HACKATHON DATA - NOT FOR CUSTOMER, CREDIT, COMPLIANCE, "
            "RISK, REGULATORY OR BUSINESS DECISION-MAKING"
        ),
        "customers": customers,
        "industries": industries,
        "news": news,
        "drafts": letters(customers, focus, industries, drawn, collateral_split, news),
        "portfolio": portfolio,
    }
    OUT.write_text(json.dumps(book, indent=2), encoding="utf-8")
    print(
        f"groups={len(customers)} drawn={drawn:,.0f} large={portfolio['large_due']} "
        f"focus={focus['legal_name']} {focus['next_due_hkd']:,.0f} in {focus['next_due_days']}d"
    )


VIRTUAL = {
    "BOR-AGHL": {
        "rm": "Chris Leung",
        "stage": 2,
        "prior_stage": 1,
        "dpd": 0,
        "ecl_rate": 0.035,
        "prior_factor": 0.72,
        "guarantor": "Apex Group parent comfort letter, unsecured",
        "revenue_hkd": [4_820_000_000, 4_260_000_000, 3_640_000_000],
        "margin_pct": [21.4, 18.6, 15.2],
        "liquidity_ratio": [1.38, 1.22, 1.08],
        "leverage": [4.6, 5.3, 6.2],
        "interest_coverage": [2.6, 2.1, 1.7],
        "coverage_assumption": 2.5,
        "coverage_threshold": 2.0,
        "warnings": [
            "Demonstration interest cover is 1.7 times, below the 2.0 times covenant.",
            "Office leasing on the Kowloon towers is behind the budget used at approval.",
        ],
    },
    "BOR-APL": {
        "rm": "May Chan",
        "stage": 1,
        "prior_stage": 1,
        "dpd": 0,
        "ecl_rate": 0.008,
        "prior_factor": 0.94,
        "guarantor": "None on the extract",
        "revenue_hkd": [1_940_000_000, 2_050_000_000, 2_110_000_000],
        "margin_pct": [28.0, 27.4, 26.8],
        "liquidity_ratio": [1.55, 1.52, 1.49],
        "leverage": [3.4, 3.3, 3.2],
        "interest_coverage": [3.4, 3.3, 3.2],
        "coverage_assumption": 3.0,
        "coverage_threshold": 2.0,
        "warnings": [],
    },
    "BOR-MAMH": {
        "rm": "Peter Ng",
        "stage": 1,
        "prior_stage": 1,
        "dpd": 0,
        "ecl_rate": 0.016,
        "prior_factor": 0.95,
        "guarantor": "Municipal holding-company guarantee, limited to drawn balance",
        "revenue_hkd": [3_100_000_000, 3_040_000_000, 2_980_000_000],
        "margin_pct": [18.2, 17.6, 17.1],
        "liquidity_ratio": [1.46, 1.41, 1.36],
        "leverage": [4.1, 4.3, 4.4],
        "interest_coverage": [2.8, 2.6, 2.5],
        "coverage_assumption": 2.5,
        "coverage_threshold": 1.8,
        "warnings": [],
    },
    "BOR-GPIHL": {
        "rm": "Irene Cheung",
        "stage": 1,
        "prior_stage": 1,
        "dpd": 0,
        "ecl_rate": 0.014,
        "prior_factor": 0.96,
        "guarantor": "None on the extract",
        "revenue_hkd": [2_240_000_000, 2_180_000_000, 2_090_000_000],
        "margin_pct": [24.1, 23.0, 21.6],
        "liquidity_ratio": [1.33, 1.29, 1.24],
        "leverage": [4.8, 5.0, 5.2],
        "interest_coverage": [2.4, 2.2, 2.1],
        "coverage_assumption": 2.2,
        "coverage_threshold": 1.75,
        "warnings": ["Vacancy on two commercial floors is above the case used at the last review."],
    },
    "BOR-IDIC": {
        "rm": "Alan Siu",
        "stage": 2,
        "prior_stage": 1,
        "dpd": 36,
        "ecl_rate": 0.045,
        "prior_factor": 0.7,
        "guarantor": "Sponsor completion guarantee on one development site",
        "revenue_hkd": [1_760_000_000, 1_520_000_000, 1_280_000_000],
        "margin_pct": [16.4, 12.8, 9.1],
        "liquidity_ratio": [1.21, 1.08, 0.96],
        "leverage": [5.5, 6.4, 7.3],
        "interest_coverage": [1.9, 1.6, 1.4],
        "coverage_assumption": 2.0,
        "coverage_threshold": 1.8,
        "warnings": [
            "Demonstration ageing shows 36 days past due on one instalment.",
            "A contractor payment claim is open. The amount is not in the property extract.",
        ],
    },
    "BOR-PCH": {
        "rm": "Joanna Lam",
        "stage": 2,
        "prior_stage": 2,
        "dpd": 12,
        "ecl_rate": 0.028,
        "prior_factor": 0.9,
        "guarantor": "Provincial finance bureau letter of support",
        "revenue_hkd": [980_000_000, 940_000_000, 910_000_000],
        "margin_pct": [14.2, 13.5, 12.8],
        "liquidity_ratio": [1.18, 1.12, 1.05],
        "leverage": [5.8, 6.0, 6.3],
        "interest_coverage": [1.8, 1.7, 1.6],
        "coverage_assumption": 1.8,
        "coverage_threshold": 1.5,
        "warnings": ["Twelve days past due on a demonstration ageing item. Still inside 30 days."],
    },
    "BOR-PF": {
        "rm": "David Ho",
        "stage": 1,
        "prior_stage": 1,
        "dpd": 0,
        "ecl_rate": 0.015,
        "prior_factor": 0.97,
        "guarantor": "None on the extract",
        "revenue_hkd": [1_420_000_000, 1_460_000_000, 1_510_000_000],
        "margin_pct": [19.6, 20.1, 20.4],
        "liquidity_ratio": [1.44, 1.47, 1.51],
        "leverage": [3.9, 3.8, 3.6],
        "interest_coverage": [2.7, 2.8, 2.9],
        "coverage_assumption": 2.4,
        "coverage_threshold": 1.8,
        "warnings": [],
    },
    "BOR-AIIC": {
        "rm": "Sophie Yip",
        "stage": 1,
        "prior_stage": 1,
        "dpd": 0,
        "ecl_rate": 0.013,
        "prior_factor": 0.96,
        "guarantor": "Apex Group cross-guarantee, capped",
        "revenue_hkd": [1_680_000_000, 1_720_000_000, 1_750_000_000],
        "margin_pct": [22.0, 21.5, 21.1],
        "liquidity_ratio": [1.36, 1.34, 1.31],
        "leverage": [4.2, 4.2, 4.3],
        "interest_coverage": [2.5, 2.4, 2.3],
        "coverage_assumption": 2.3,
        "coverage_threshold": 1.8,
        "warnings": [],
    },
    "BOR-STBB": {
        "rm": "Raymond Au",
        "stage": 1,
        "prior_stage": 1,
        "dpd": 0,
        "ecl_rate": 0.002,
        "prior_factor": 1.0,
        "guarantor": "Sovereign appropriation, as described in the demonstration file",
        "revenue_hkd": [8_400_000_000, 8_550_000_000, 8_620_000_000],
        "margin_pct": [11.0, 11.2, 11.1],
        "liquidity_ratio": [1.85, 1.88, 1.9],
        "leverage": [2.1, 2.0, 2.0],
        "interest_coverage": [4.8, 4.7, 4.6],
        "coverage_assumption": 4.0,
        "coverage_threshold": 2.5,
        "warnings": [],
    },
    "BOR-MGAA": {
        "rm": "Helen Kwok",
        "stage": 1,
        "prior_stage": 1,
        "dpd": 0,
        "ecl_rate": 0.002,
        "prior_factor": 1.0,
        "guarantor": "Municipal revenue assignment",
        "revenue_hkd": [6_200_000_000, 6_350_000_000, 6_410_000_000],
        "margin_pct": [10.4, 10.6, 10.5],
        "liquidity_ratio": [1.72, 1.74, 1.76],
        "leverage": [2.4, 2.3, 2.3],
        "interest_coverage": [4.2, 4.2, 4.1],
        "coverage_assumption": 3.5,
        "coverage_threshold": 2.5,
        "warnings": [],
    },
}


def apply_virtual(customers: list[dict]) -> None:
    """Fill screens the property extract does not cover. Balances, collateral and grades stay as provided."""
    for customer in customers:
        profile = VIRTUAL[customer["customer_id"]]
        drawn = customer["drawn_hkd"]
        ecl = round(drawn * profile["ecl_rate"], 2)
        customer["rm"] = profile["rm"]
        customer["stage"] = profile["stage"]
        customer["prior_stage"] = profile["prior_stage"]
        customer["dpd"] = profile["dpd"]
        customer["dpd_component"] = "Demonstration instalment" if profile["dpd"] else "None"
        customer["ecl_hkd"] = ecl
        customer["prior_ecl_hkd"] = round(ecl * profile["prior_factor"], 2)
        customer["provision_hkd"] = ecl
        customer["guarantor"] = profile["guarantor"]
        customer["revenue_hkd"] = profile["revenue_hkd"]
        customer["margin_pct"] = profile["margin_pct"]
        customer["liquidity_ratio"] = profile["liquidity_ratio"]
        customer["leverage"] = profile["leverage"]
        customer["interest_coverage"] = profile["interest_coverage"]
        customer["coverage_assumption"] = profile["coverage_assumption"]
        customer["coverage_threshold"] = profile["coverage_threshold"]
        customer["warnings"] = [{"description": text} for text in profile["warnings"]]
        customer["watchlist"] = profile["stage"] >= 2 or profile["dpd"] > 0
        cover = profile["interest_coverage"][-1]
        customer["summary"] += (
            f" Demonstration figures, not on the property extract: relationship manager {profile['rm']}, "
            f"stage {profile['prior_stage']} to {profile['stage']}, days past due {profile['dpd']}, "
            f"ECL {money_words(ecl)}, interest cover {cover:.1f} times against a {profile['coverage_threshold']:.1f} times covenant."
        )
        customer["documents"]["financials"] = {
            "title": f"Demonstration statements — {customer['legal_name']}",
            "locator": "Placeholder financials for the covenant screen. Not in the uploaded extracts.",
            "passage": (
                f"2024 to 2026 revenue {money_words(profile['revenue_hkd'][0])}, "
                f"{money_words(profile['revenue_hkd'][1])}, {money_words(profile['revenue_hkd'][2])}. "
                f"Interest cover {profile['interest_coverage'][0]:.1f} times, "
                f"{profile['interest_coverage'][1]:.1f} times, {cover:.1f} times. "
                f"Covenant {profile['coverage_threshold']:.1f} times. "
                "Replace these figures when statements are provided."
            ),
        }
        customer["documents"]["review"]["passage"] += (
            f" Demonstration overlay: stage {profile['prior_stage']} to {profile['stage']}, "
            f"days past due {profile['dpd']}, ECL {money_words(ecl)}."
        )


def materiality(customer: dict, direct_hit: bool) -> dict:
    coverage = customer.get("coverage_ratio") or 0
    score = 25 if customer["drawn_hkd"] >= 50_000_000 else 15
    if coverage < 1:
        score += 15
    if customer["rating"] >= 10:
        score += 15
    elif customer["rating"] >= 6:
        score += 8
    if customer["dpd"] >= 30:
        score += 15
    elif customer["dpd"] > 0:
        score += 5
    score += min(20, 8 * len(customer["warnings"]))
    if customer["stage"] >= 2:
        score += 10
    if not direct_hit:
        score = min(score, 35)
    return {
        "exposure_hkd": customer["drawn_hkd"],
        "security_coverage": coverage,
        "guarantor_support": customer.get("guarantor") or "none on file",
        "financial_strength": f"rating {customer['rating']}, interest cover {customer['interest_coverage'][-1]:.1f} times",
        "warning_signals": len(customer["warnings"]),
        "score": score,
        "material": score >= 50 and direct_hit,
    }


def news_items(customers: list[dict]) -> list[dict]:
    by_id = {customer["customer_id"]: customer for customer in customers}
    apex = by_id["BOR-AGHL"]
    idic = by_id["BOR-IDIC"]
    metro = by_id["BOR-MGAA"]
    property_drawn = sum(item["drawn_hkd"] for item in customers if item["industry"] == "Property investment")
    return [
        {
            "id": "NEWS-AGHL-LEASE",
            "headline": "Office leasing at Apex Global's Kowloon towers is behind budget",
            "source": "Credit Risk Alert Portal (placeholder feed)",
            "date": "12 Sep 2026",
            "customer_id": apex["customer_id"],
            "industry": apex["industry"],
            "body": (
                "A placeholder alert says two commercial floors in the Kowloon towers leased by Apex Global Holdings "
                "are still vacant against the budget used at the last review. No loss amount is stated. "
                "Replace this item when the live feed is connected."
            ),
            "factors": materiality(apex, direct_hit=True),
        },
        {
            "id": "NEWS-IDIC-CLAIM",
            "headline": "Contractor files a payment claim against Industrial Development Investment Corp.",
            "source": "Credit Risk Alert Portal (placeholder feed)",
            "date": "21 Sep 2026",
            "customer_id": idic["customer_id"],
            "industry": idic["industry"],
            "body": (
                "A placeholder court-list note names a contractor claim. The claim amount is not in the property extract. "
                "The demonstration file also shows 36 days past due on one instalment."
            ),
            "factors": materiality(idic, direct_hit=True),
        },
        {
            "id": "NEWS-PROP-VACANCY",
            "headline": "Hong Kong commercial vacancy stayed high through the third quarter",
            "source": "Credit Risk Alert Portal (placeholder feed)",
            "date": "28 Sep 2026",
            "customer_id": None,
            "industry": "Property investment",
            "body": (
                "A sector placeholder says grade-A and fringe office vacancy did not improve in the quarter. "
                "It does not name a default. It is here so the industry step has a headline until a live feed arrives."
            ),
            "factors": {
                "exposure_hkd": property_drawn,
                "security_coverage": "about 1.58 times market value over drawn, from the collateral extract",
                "guarantor_support": "not an industry-level fact",
                "financial_strength": "property names carry grades 7 to 11 on the cash flow file",
                "warning_signals": "leasing, vacancy and one contractor claim on the placeholder feed",
                "score": 74,
                "material": True,
            },
        },
        {
            "id": "NEWS-GOV-LAND",
            "headline": "Commentary notes slower land-premium receipts for local authorities",
            "source": "Credit Risk Alert Portal (placeholder feed)",
            "date": "4 Sep 2026",
            "customer_id": metro["customer_id"],
            "industry": metro["industry"],
            "body": (
                "A short commentary mentions land premiums. It does not name Metro Gov Authority A in a default, "
                "and it does not give a figure. Scored below the materiality line."
            ),
            "factors": materiality(metro, direct_hit=False),
        },
    ]


def documents(borrower, grade, drawn, market, net, ltv, addresses, nxt, prior):
    address_text = "; ".join(addresses)
    return {
        "credit_paper": {
            "title": f"Credit extract — {borrower}",
            "locator": "Property portfolio collateral extract, 30 Sep 2026",
            "passage": (
                f"Grade {grade}. On-balance drawn {money_words(drawn)}. "
                f"Property market value {money_words(market)}. Net realizable value {money_words(net)}. "
                f"LTV {ltv:.2f}. First charge. Properties: {address_text}."
            ),
        },
        "review": {
            "title": f"Position comparison — {borrower}",
            "locator": "Collateral extract 31 Aug 2026 and 30 Sep 2026",
            "passage": (
                f"Grade stayed at {grade} from 31 Jan 2026 through 30 Sep 2026. "
                f"On-balance outstanding moved from {money_words(prior)} on 31 Aug 2026 to {money_words(drawn)} on 30 Sep 2026. "
                "No stage migration and no days-past-due balance is on the extract."
            ),
        },
        "financials": {
            "title": f"Financial statements — {borrower}",
            "locator": "Not in the property portfolio, cash flow, or collateral extracts",
            "passage": (
                "Revenue, margin, liquidity, leverage and interest cover were not in the uploaded portfolio "
                "or in the generated cash flow and collateral files. No covenant threshold is on file. "
                f"The collateral coverage on 30 Sep 2026 is market value {money_words(market)} against drawn {money_words(drawn)}."
            ),
        },
        "repayment": {
            "title": f"Cash flow schedule — {nxt['contract']}",
            "locator": f"CASH_FLOW as at 30 Sep 2026, {nxt['date']}",
            "passage": (
                f"Next principal is {money_words(nxt['amount'])} on {nxt['date']} ({nxt['days']} days), "
                f"contract {nxt['contract']}, method {nxt['method'].replace('_', ' ').title()}, "
                f"coupon {nxt['rate'] * 100:.1f} percent. Source is the generated cash flow schedule. "
                "The monitoring threshold is HKD 5,000,000."
            ),
        },
    }


def letter(subject, kind, customer_id, paragraphs: list[str]) -> dict:
    banner = (
        "SYNTHETIC HACKATHON DATA - NOT FOR CUSTOMER, CREDIT, COMPLIANCE, "
        "RISK, REGULATORY OR BUSINESS DECISION-MAKING"
    )
    body = "\n".join(
        [
            "To: yiyangyao2@gmail.com",
            f"Subject: {subject}",
            "",
            banner,
            "",
            "Dear colleague,",
            "",
            "This draft was written from the property portfolio collateral extract and the generated cash flow schedule as at 30 Sep 2026. It is not a credit decision.",
            "",
            *sum(([paragraph, ""] for paragraph in paragraphs), []),
            "Please send this from your own mailbox if you want it delivered.",
            "",
            "Risk intelligence demonstration",
        ]
    )
    return {"id": kind[0], "kind": kind[1], "subject": subject, "customer_id": customer_id, "body": body}


def letters(customers, focus, industries, drawn, collateral_split, news_feed):
    property_book = next(item for item in industries if item["industry"] == "Property investment")
    government = next(item for item in industries if item["industry"] == "Government")
    collateral_line = ", ".join(f"{name} {money_words(value)}" for name, value in collateral_split.items())
    apex = next(item for item in customers if item["customer_id"] == "BOR-AGHL")
    idic = next(item for item in customers if item["customer_id"] == "BOR-IDIC")
    apex_news = next(item for item in news_feed if item["id"] == "NEWS-AGHL-LEASE")
    vacancy = next(item for item in news_feed if item["id"] == "NEWS-PROP-VACANCY")
    news = letter(
        f"Adverse news — {apex['legal_name']}",
        ("MAIL-NEWS-APEX", "Adverse news"),
        apex["customer_id"],
        [
            f"{apex_news['date']}. {apex_news['headline']}.",
            apex_news["body"],
            f"Materiality score {apex_news['factors']['score']}. Drawn {money_words(apex['drawn_hkd'])}. Collateral coverage {apex['coverage_ratio']}. Guarantor: {apex['guarantor']}. Interest cover on the demonstration statements is {apex['interest_coverage'][-1]:.1f} times.",
            "A second placeholder says a contractor has filed a claim against Industrial Development Investment Corp. Replace both items when the live alert feed is provided.",
            "This note asks the relationship manager to check the leasing budget. It does not downgrade the name, call default, or exit the relationship.",
        ],
    )
    industry = letter(
        "Industry review — Property investment",
        ("MAIL-IND-WHOLESALE", "Industry stress"),
        "",
        [
            f"{vacancy['date']}. {vacancy['headline']}. {vacancy['body']}",
            f"Property investment drawn is {money_words(property_book['drawn_hkd'])} across {property_book['customers']} groups. Stage 2 names: {property_book['stage2']}. Migrations: {property_book['migrations']}. Open warnings: {property_book['open_warnings']}.",
            f"Government drawn is {money_words(government['drawn_hkd'])} across {government['customers']} groups.",
            f"On-balance collateral market value is {collateral_line}. Portfolio LTV on the extract is about 0.63. Grades on the cash flow file did not change between January and September 2026.",
        ],
    )
    repayment = letter(
        f"Large repayment — {focus['legal_name']}",
        ("MAIL-REPAY-LANTERN", "Large repayment"),
        focus["customer_id"],
        [
            f"{focus['legal_name']} has principal of {money_words(focus['next_due_hkd'])} due on {focus['next_due_date']}, {focus['next_due_days']} days after 30 Sep 2026.",
            f"The amount is on {focus['next_contract']}, method {focus['next_method'].replace('_', ' ').title()}. It is above the HKD 5,000,000 monitoring threshold.",
            f"Group drawn is {money_words(focus['drawn_hkd'])}. On-balance property market value is {money_words(focus['collateral_hkd'])}. LTV is {focus['ltv']:.2f}.",
            "The relationship owner should confirm the funding source for this instalment. The draft does not extend the date and it does not waive the payment.",
        ],
    )
    ageing = letter(
        f"Days past due — {idic['legal_name']}",
        ("MAIL-DPD-LANTERN", "Days past due"),
        idic["customer_id"],
        [
            f"The property extract itself shows every facility current. The demonstration ageing, used until a collections file arrives, places {idic['legal_name']} at {idic['dpd']} days past due.",
            f"Drawn {money_words(idic['drawn_hkd'])}. Relationship manager {idic['rm']}. One warning records a contractor claim that is also a placeholder.",
            "Provincial Capital Holdings is 12 days past due on the same demonstration file, still inside 30 days.",
            "The cash-flow dates above HKD 5,000,000 remain future obligations. This draft does not treat those future dates as past due.",
        ],
    )
    projected = round(apex["interest_coverage"][-1] - 0.6, 1)
    covenant = letter(
        f"Covenant test — {apex['legal_name']}",
        ("MAIL-COV-APEX", "Covenant scenario"),
        apex["customer_id"],
        [
            "Financial statements were not in the uploaded files. The figures below are a demonstration so the covenant screen can be used.",
            f"Latest demonstration interest cover for {apex['legal_name']} is {apex['interest_coverage'][-1]:.1f} times. The covenant is {apex['coverage_threshold']:.1f} times, so the name is outside the covenant on this placeholder.",
            f"A revenue decline of 15 percent moves cover to about {projected:.1f} times. Margin, funding cost and liquidity cases are on the financials screen.",
            f"What is from the extract: drawn {money_words(apex['drawn_hkd'])}, property market value {money_words(apex['collateral_hkd'])}, LTV {apex['ltv']:.2f}.",
        ],
    )
    return [news, industry, repayment, ageing, covenant]


if __name__ == "__main__":
    main()
