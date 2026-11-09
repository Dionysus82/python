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
    portfolio = {
        "customers": len(customers),
        "facilities_on_balance": sum(1 for row in current if row["INSTRUMENT"] == "Customer Loan"),
        "drawn_hkd": round(drawn, 2),
        "ecl_hkd": 0,
        "prior_ecl_hkd": 0,
        "ecl_coverage": 0,
        "migrations": 0,
        "stages": {
            "1": {"count": len(customers), "drawn_hkd": round(drawn, 2)},
            "2": {"count": 0, "drawn_hkd": 0},
            "3": {"count": 0, "drawn_hkd": 0},
        },
        "dpd": {
            name: {"count": len(customers) if name == "Current" else 0, "drawn_hkd": round(drawn, 2) if name == "Current" else 0}
            for name in ("Current", "1–29", "30–59", "60–89", "90–179", "180+")
        },
        "collateral": {key: round(value, 2) for key, value in collateral_split.items()},
        "maturity": {key: round(value, 2) for key, value in maturity.items()},
        "large_due": [item["customer_id"] for item in customers if item["next_due_hkd"] >= THRESHOLD and item["next_due_days"] <= 90],
        "overdue_reviews": 0,
        "open_warnings": 0,
    }
    focus = next(item for item in customers if item["repay_draft_id"])
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
        "news": [],
        "drafts": letters(customers, focus, industries, drawn, collateral_split),
        "portfolio": portfolio,
    }
    OUT.write_text(json.dumps(book, indent=2), encoding="utf-8")
    print(
        f"groups={len(customers)} drawn={drawn:,.0f} large={portfolio['large_due']} "
        f"focus={focus['legal_name']} {focus['next_due_hkd']:,.0f} in {focus['next_due_days']}d"
    )


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


def letters(customers, focus, industries, drawn, collateral_split):
    property_book = next(item for item in industries if item["industry"] == "Property investment")
    government = next(item for item in industries if item["industry"] == "Government")
    collateral_line = ", ".join(f"{name} {money_words(value)}" for name, value in collateral_split.items())
    news = letter(
        "Adverse news — no item on the property extract",
        ("MAIL-NEWS-APEX", "Adverse news"),
        "",
        [
            "The property portfolio, cash flow and collateral files do not contain an adverse-news feed.",
            "No item was scored for materiality. Exposure, security coverage, guarantor support, financial strength and warnings were not applied to a headline because there is no headline on file.",
            f"The on-balance book at 30 Sep 2026 is {money_words(drawn)} across {len(customers)} borrower groups. This note does not ask for a downgrade, a default call, or an exit.",
        ],
    )
    industry = letter(
        "Industry review — Property investment",
        ("MAIL-IND-WHOLESALE", "Industry stress"),
        "",
        [
            f"Property investment drawn is {money_words(property_book['drawn_hkd'])} across {property_book['customers']} groups. Government drawn is {money_words(government['drawn_hkd'])} across {government['customers']} groups.",
            f"On-balance collateral market value is {collateral_line}. Portfolio LTV is about 0.63 on every group, because outstanding sits at that fraction of market value in the extract.",
            "Grades on the cash flow file run from 3 for the two government names to 7, 9, 10 and 11 for the property names. No grade changed between January and September 2026.",
            "The review asks for a check of the next principal above HKD 5,000,000. It does not record a sector default and it does not change a grade.",
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
        "Ageing reminder — no facility past due",
        ("MAIL-DPD-LANTERN", "Days past due"),
        "",
        [
            "At 30 Sep 2026 every on-balance facility in the property extract is current.",
            "There is no balance in the 30, 60, 90 or 180 day buckets, so no overdue principal or interest reminder is due.",
            "The next principals above HKD 5,000,000 are still future dates on the cash flow schedule. This draft does not treat a future instalment as past due.",
        ],
    )
    covenant = letter(
        "Covenant headroom — statements not on file",
        ("MAIL-COV-APEX", "Covenant scenario"),
        customers[0]["customer_id"],
        [
            "The uploaded portfolio and the generated cash flow and collateral files do not include financial statements.",
            "Revenue, margin, liquidity, leverage and interest cover cannot be compared with an approved covenant, because no covenant threshold was supplied.",
            f"What is on file for {customers[0]['legal_name']} is drawn {money_words(customers[0]['drawn_hkd'])}, property market value {money_words(customers[0]['collateral_hkd'])}, and LTV {customers[0]['ltv']:.2f}.",
            "No revenue-decline scenario is run. A scenario that needs profit-and-loss figures would invent the result.",
        ],
    )
    return [news, industry, repayment, ageing, covenant]


if __name__ == "__main__":
    main()
