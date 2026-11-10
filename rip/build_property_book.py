"""Fill the Tiffany business-case book from the property collateral and cash flow extracts."""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ASOF = "30/09/2026"
PRIOR = "31/08/2026"
THRESHOLD = 5_000_000
ROOT = Path("/workspace/rip/property_data")
COLL = ROOT / "COLLATERAL_ALL_2026.csv"
FLOW = ROOT / "CASH_FLOW_ALL_2026.csv"
PORTFOLIO = ROOT / "source" / "IFRS9_Property_Portfolio_2026-09.csv"
PORTFOLIO_PRIOR = ROOT / "source" / "IFRS9_Property_Portfolio_2026-08.csv"
OUT = Path(__file__).resolve().parent / "book.json"



def parse_date(text: str):
    return datetime.strptime(text, "%d/%m/%Y")


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def money_words(value: float) -> str:
    return f"HKD {value:,.0f}"


def borrower_facts(rows: list[dict]) -> dict[str, dict]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["BORROWER1"]].append(row)
    facts = {}
    for name, items in grouped.items():
        on_balance = [row for row in items if row["INSTRUMENT"] != "Off-Bal"]
        facts[name] = {
            "drawn": round(sum(float(row["BAL_OUTSTD"]) for row in on_balance), 2),
            "committed": round(sum(float(row["FACILITY_LIMIT"]) for row in items), 2),
            "ecl": round(sum(float(row["ECL_HKD"]) for row in items), 2),
            "stage": max(int(row["STAGE"]) for row in items),
            "dpd": max(int(row["PAST_DUE_DAY"]) for row in items),
            "industry": items[0]["INDUSTRY_SECTOR"],
            "grade": int(items[0]["CURRENT_PD_GRADE"]),
            "original": int(items[0]["ORIGINAL_PD_GRADE"]),
            "bond": round(sum(float(row["BAL_OUTSTD"]) for row in items if row["INSTRUMENT"] == "Bond"), 2),
        }
    return facts


def iso_to_dmy(iso: str) -> str:
    year, month, day = iso.split("-")
    return f"{day}/{month}/{year}"


def attach_history(customers: list[dict], collateral: list[dict], flows: list[dict]) -> tuple[list[str], list[dict]]:
    """One snapshot per month-end, so the screens can follow any checked date."""
    meta = {item["legal_name"]: item for item in customers}
    collateral_by_date = defaultdict(dict)
    for row in collateral:
        collateral_by_date[row["REPORTING_DATE"]][row["CONTRACT_REFERENCE"]] = row
    flows_by = defaultdict(lambda: defaultdict(list))
    for row in flows:
        flows_by[row["REPORTING_DATE"]][row["CONTRACT_REFERENCE"]].append(row)
    for contracts in flows_by.values():
        for rows in contracts.values():
            rows.sort(key=lambda item: parse_date(item["CASH_FLOW_DATE"]))

    dates = []
    portfolio_history = []
    histories = defaultdict(list)
    previous_stage = {}
    previous_ecl = {}
    for path in sorted((ROOT / "source").glob("IFRS9_Property_Portfolio_*.csv")):
        source_rows = load(path)
        iso = source_rows[0]["REPORTING_DATE"]
        dmy = iso_to_dmy(iso)
        reporting = parse_date(dmy)
        dates.append(iso)
        grouped = defaultdict(list)
        for row in source_rows:
            grouped[row["BORROWER1"]].append(row)
        month_points = []
        for borrower, items in grouped.items():
            point = history_point(
                borrower, items, collateral_by_date[dmy], flows_by[dmy], reporting,
                previous_stage.get(borrower), previous_ecl.get(borrower), meta[borrower]["customer_id"],
            )
            histories[borrower].append(point)
            month_points.append(point)
        portfolio_history.append(portfolio_point(iso, month_points, previous_stage))
        previous_stage = {point["legal_name"]: point["stage"] for point in month_points}
        previous_ecl = {point["legal_name"]: point["ecl_hkd"] for point in month_points}
    for customer in customers:
        customer["history"] = histories[customer["legal_name"]]
        if len(customer["history"]) != 12:
            raise RuntimeError(f"{customer['legal_name']} has {len(customer['history'])} months")
    return dates, portfolio_history


def history_point(borrower, items, collateral, flows, reporting, prior_stage, prior_ecl, customer_id) -> dict:
    on_balance = [row for row in items if row["INSTRUMENT"] != "Off-Bal"]
    drawn = round(sum(float(row["BAL_OUTSTD"]) for row in on_balance), 2)
    market = round(sum(float(row["MARKET_VALUE_HKD"]) for row in on_balance), 2)
    nrv = round(sum(float(row["NET_REALIZABLE_VALUE_HKD"]) for row in on_balance), 2)
    ead = round(sum(float(row["EAD_POST_CCF"]) for row in on_balance), 2)
    nominal = round(sum(float(row["BAL_NOMINAL"]) for row in on_balance), 2)
    facilities = [facility_row(row, collateral.get(row["CONTRACT_REFERENCE"])) for row in items]
    next_principal = None
    for row in on_balance:
        ref = row["CONTRACT_REFERENCE"]
        for flow in flows.get(ref, []):
            if flow["CASH_FLOW_TYPE"] != "N" or float(flow["CASH_FLOW_AMOUNT"]) <= 0:
                continue
            days = (parse_date(flow["CASH_FLOW_DATE"]) - reporting).days
            candidate = {
                "days": days,
                "amount": round(float(flow["CASH_FLOW_AMOUNT"]), 2),
                "date": flow["CASH_FLOW_DATE"],
                "contract": ref,
                "method": flow["AMORTIZATION_METHOD"],
            }
            if next_principal is None or (candidate["days"], -candidate["amount"]) < (next_principal["days"], -next_principal["amount"]):
                next_principal = candidate
            break
    if next_principal is None:
        raise RuntimeError(f"no principal for {borrower} at {reporting.date()}")
    stage = max(int(row["STAGE"]) for row in items)
    return {
        "date": reporting.strftime("%Y-%m-%d"),
        "legal_name": borrower,
        "customer_id": customer_id,
        "industry": items[0]["INDUSTRY_SECTOR"],
        "drawn_hkd": drawn,
        "committed_hkd": round(sum(float(row["FACILITY_LIMIT"]) for row in items), 2),
        "ecl_hkd": round(sum(float(row["ECL_HKD"]) for row in items), 2),
        "prior_ecl_hkd": prior_ecl if prior_ecl is not None else round(sum(float(row["ECL_HKD"]) for row in items), 2),
        "stage": stage,
        "prior_stage": prior_stage if prior_stage is not None else stage,
        "dpd": max(int(row["PAST_DUE_DAY"]) for row in items),
        "rating": int(items[0]["CURRENT_PD_GRADE"]),
        "collateral_hkd": market,
        "nrv_hkd": nrv,
        "ead_hkd": ead,
        "nominal_hkd": nominal,
        "ltv": round(drawn / market, 2) if market else None,
        "coverage_ratio": round(market / drawn, 2) if drawn else None,
        "next_due_days": next_principal["days"],
        "next_due_hkd": next_principal["amount"],
        "next_due_date": next_principal["date"],
        "next_contract": next_principal["contract"],
        "next_method": next_principal["method"],
        "refinancing": next_principal["method"] == "BULLET" and next_principal["days"] <= 90,
        "facilities": facilities,
    }


def facility_row(source: dict, collateral: dict | None) -> dict:
    balance = float(source["BAL_OUTSTD"])
    market = float(source["MARKET_VALUE_HKD"])
    nrv = float(source["NET_REALIZABLE_VALUE_HKD"])
    return {
        "contract": source["CONTRACT_REFERENCE"],
        "instrument": source["INSTRUMENT"],
        "status": source["STATUS"],
        "department": source["DEPT"],
        "stage": int(source["STAGE"]),
        "dpd": int(source["PAST_DUE_DAY"]),
        "grade": int(source["CURRENT_PD_GRADE"]),
        "original_grade": int(source["ORIGINAL_PD_GRADE"]),
        "balance_hkd": round(balance, 2),
        "nominal_hkd": round(float(source["BAL_NOMINAL"]), 2),
        "limit_hkd": round(float(source["FACILITY_LIMIT"]), 2),
        "available_hkd": round(float(source["FACILITY_AVAILABLE"]), 2),
        "ead_hkd": round(float(source["EAD_POST_CCF"]), 2),
        "pd": float(source["SCN_WGT_ANNUAL_PD"]),
        "lgd": float(source["SCN_WGT_LGD"]),
        "ecl_hkd": round(float(source["ECL_HKD"]), 2),
        "maturity": source["MATURITY_DATE"],
        "collateral_id": source["COLLATERAL_ID"],
        "collateral_type": source["COLLATERAL_TYPE"],
        "address": collateral["PROPERTY_ADDRESS"] if collateral else "",
        "district": collateral["DISTRICT"] if collateral else "",
        "market_hkd": round(market, 2),
        "nrv_hkd": round(nrv, 2),
        "ltv": round(balance / market, 6) if balance and market else 0,
        "ltv_nrv": round(balance / nrv, 6) if balance and nrv else 0,
        "charge": "1",
    }


def portfolio_point(iso: str, points: list[dict], previous_stage: dict) -> dict:
    drawn = round(sum(point["drawn_hkd"] for point in points), 2)
    ecl = round(sum(point["ecl_hkd"] for point in points), 2)
    market = round(sum(point["collateral_hkd"] for point in points), 2)
    stages = {}
    for key in (1, 2, 3):
        members = [point for point in points if point["stage"] == key]
        stages[str(key)] = {"count": len(members), "drawn_hkd": round(sum(point["drawn_hkd"] for point in members), 2)}
    bands = (
        ("Current", lambda days: days == 0),
        ("1–29", lambda days: 1 <= days <= 29),
        ("30–59", lambda days: 30 <= days <= 59),
        ("60–89", lambda days: 60 <= days <= 89),
        ("90–179", lambda days: 90 <= days <= 179),
        ("180+", lambda days: days >= 180),
    )
    dpd = {}
    for name, test in bands:
        members = [point for point in points if test(point["dpd"])]
        dpd[name] = {"count": len(members), "drawn_hkd": round(sum(point["drawn_hkd"] for point in members), 2)}
    maturity = {"month": 0.0, "quarter": 0.0, "later": 0.0}
    for point in points:
        if point["next_due_days"] <= 30:
            maturity["month"] += point["next_due_hkd"]
        elif point["next_due_days"] <= 90:
            maturity["quarter"] += point["next_due_hkd"]
        else:
            maturity["later"] += point["next_due_hkd"]
    collateral = defaultdict(float)
    facilities_on_balance = 0
    for point in points:
        for facility in point["facilities"]:
            if facility["instrument"] == "Off-Bal":
                continue
            facilities_on_balance += 1
            collateral[facility["collateral_type"]] += facility["market_hkd"]
    industries = []
    for name in sorted({point["industry"] for point in points}):
        members = [point for point in points if point["industry"] == name]
        industries.append({
            "industry": name,
            "customers": len(members),
            "drawn_hkd": round(sum(point["drawn_hkd"] for point in members), 2),
            "ecl_hkd": round(sum(point["ecl_hkd"] for point in members), 2),
            "stage2": sum(1 for point in members if point["stage"] == 2),
            "migrations": sum(1 for point in members if point["stage"] > previous_stage.get(point["legal_name"], point["stage"])),
            "dpd_accounts": sum(1 for point in members if point["dpd"] > 0),
            "collateral_hkd": round(sum(point["collateral_hkd"] for point in members), 2),
        })
    industries.sort(key=lambda item: item["drawn_hkd"], reverse=True)
    return {
        "date": iso,
        "customers": len(points),
        "facilities_on_balance": facilities_on_balance,
        "drawn_hkd": drawn,
        "ecl_hkd": ecl,
        "prior_ecl_hkd": round(sum(point["prior_ecl_hkd"] for point in points), 2),
        "ecl_coverage": round(ecl / drawn, 4) if drawn else 0,
        "migrations": sum(1 for point in points if point["stage"] > previous_stage.get(point["legal_name"], point["stage"])),
        "stage2_names": stages["2"]["count"],
        "stage2_drawn": stages["2"]["drawn_hkd"],
        "dpd_names": sum(1 for point in points if point["dpd"] > 0),
        "dpd60_drawn": round(sum(point["drawn_hkd"] for point in points if point["dpd"] >= 60), 2),
        "market_hkd": market,
        "ltv": round(drawn / market, 2) if market else None,
        "stages": stages,
        "dpd": dpd,
        "collateral": {key: round(value, 2) for key, value in collateral.items()},
        "maturity": {key: round(value, 2) for key, value in maturity.items()},
        "large_due": [point["customer_id"] for point in points if point["next_due_hkd"] >= THRESHOLD and point["next_due_days"] <= 90],
        "overdue_reviews": sum(1 for point in points if point["dpd"] >= 30),
        "industries": industries,
    }


def main() -> None:
    collateral = load(COLL)
    flows = load(FLOW)
    facts = borrower_facts(load(PORTFOLIO))
    prior_facts = borrower_facts(load(PORTFOLIO_PRIOR))
    current = [row for row in collateral if row["REPORTING_DATE"] == ASOF]
    prior_rows = [row for row in collateral if row["REPORTING_DATE"] == PRIOR]
    prior_bal = defaultdict(float)
    for row in prior_rows:
        if row["INSTRUMENT"] != "Off-Bal":
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
        loans = [row for row in rows if row["INSTRUMENT"] != "Off-Bal"]
        off = [row for row in rows if row["INSTRUMENT"] == "Off-Bal"]
        drawn = round(sum(float(row["BAL_OUTSTD_HKD"]) for row in loans), 2)
        market = sum(float(row["MARKET_VALUE_HKD"]) for row in loans)
        net = sum(float(row["NET_REALIZABLE_VALUE_HKD"]) for row in loans)
        off_market = sum(float(row["MARKET_VALUE_HKD"]) for row in off)
        profile = facts[borrower]
        if abs(profile["drawn"] - drawn) > 1:
            raise RuntimeError(f"{borrower} collateral balance {drawn} != portfolio {profile['drawn']}")
        grade = profile["grade"]
        if int(terms[loans[0]["CONTRACT_REFERENCE"]]["CURRENT_PD_GRADE"]) != grade:
            raise RuntimeError(f"{borrower} cash-flow grade differs from the portfolio")
        earlier = prior_facts[borrower]
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
                "industry": profile["industry"],
                "jurisdiction": "Hong Kong",
                "rating": grade,
                "prior_rating": profile["original"],
                "prior_rating_date": "original grade on the portfolio file",
                "stage": profile["stage"],
                "prior_stage": earlier["stage"],
                "drawn_hkd": round(drawn, 2),
                "committed_hkd": profile["committed"],
                "collateral_hkd": round(market, 2),
                "collateral_type": "Residential and commercial property",
                "coverage_ratio": coverage,
                "ltv": ltv,
                "guarantor": "None on the extract",
                "dpd": profile["dpd"],
                "dpd_component": "Portfolio extract" if profile["dpd"] else "None",
                "ecl_hkd": profile["ecl"],
                "prior_ecl_hkd": earlier["ecl"],
                "provision_hkd": profile["ecl"],
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
                    f"{borrower} has {len(loans)} on-balance facilities totalling {money_words(drawn)}"
                    + (f", including a bond of {money_words(profile['bond'])}," if profile["bond"] else "")
                    + f" and {len(off)} off-balance facilities with property market value {money_words(off_market)}. "
                    f"On-balance market value is {money_words(market)} and net realizable value is {money_words(net)}. "
                    f"LTV is {ltv:.2f}. Current grade is {grade} and the original grade is {profile['original']}. "
                    f"Stage {profile['stage']}, days past due {profile['dpd']}, ECL {money_words(profile['ecl'])}. "
                    f"Outstanding on 31 Aug 2026 was {money_words(prior)} and ECL was {money_words(earlier['ecl'])}."
                ),
                "documents": documents(
                    borrower, grade, profile["original"], drawn, market, net, ltv, addresses,
                    next_principal, prior, profile["stage"], earlier["stage"], profile["dpd"],
                    profile["ecl"], earlier["ecl"],
                ),
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
        if row["INSTRUMENT"] != "Off-Bal":
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
        "facilities_on_balance": sum(1 for row in current if row["INSTRUMENT"] != "Off-Bal"),
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
    dates, portfolio_history = attach_history(customers, collateral, flows)
    drafts = letters(customers, focus, industries, drawn, collateral_split, news)
    anchor_customer = customers[0]["customer_id"]
    anchor_industry = industries[0]["industry"]
    property_months = {
        item["date"]: (item["drawn_hkd"], item["ecl_hkd"], item["customers"])
        for item in portfolio_history
    }
    wholesale_customers, wholesale_sources = load_wholesale({item["customer_id"] for item in customers})
    customers.extend(wholesale_customers)
    portfolio_history = rebuild_portfolio_history(customers, dates)
    for iso in ("2026-10-31", "2026-11-30"):
        point = next(item for item in portfolio_history if item["date"] == iso)
        observed = (point["drawn_hkd"], point["ecl_hkd"], point["customers"])
        if observed != property_months[iso]:
            raise RuntimeError(f"{iso} changed from {property_months[iso]} to {observed}")
    book = {
        "as_of": dates[-1],
        "as_of_label": "31 Dec 2025 to 30 Nov 2026",
        "dates": dates,
        "portfolio_history": portfolio_history,
        "threshold_hkd": THRESHOLD,
        "notify_to": "credit.desk@hkbea.example",
        "default_customer_id": anchor_customer,
        "default_industry": anchor_industry,
        "ecl_sources": wholesale_sources,
        "banner": (
            "SYNTHETIC HACKATHON DATA - NOT FOR CUSTOMER, CREDIT, COMPLIANCE, "
            "RISK, REGULATORY OR BUSINESS DECISION-MAKING"
        ),
        "customers": customers,
        "industries": industries,
        "news": news,
        "drafts": drafts,
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
        "revenue_hkd": [1_180_000_000, 1_140_000_000, 1_140_000_000],
        "margin_pct": [67.8, 67.5, 67.5],
        "liquidity_ratio": [1.35, 1.32, 1.30],
        "leverage": [1.86, 1.85, 1.85],
        "interest_coverage": [2.3, 2.2, 2.2],
        "coverage_assumption": 2.5,
        "coverage_threshold": 2.0,
        "warnings": [
            "Annual-review statements at FY2025: interest cover 2.2 times against a 2.0 times covenant, net gearing 1.85 times. No covenant breach on those statements.",
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
            "Placeholder news: a contractor payment claim is open. The amount is not in the property extract.",
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
        "warnings": [],
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
    """Fill screens the portfolio file does not cover. Balances, collateral, grades, stage, ECL and days past due stay as provided."""
    for customer in customers:
        profile = VIRTUAL[customer["customer_id"]]
        customer["rm"] = profile["rm"]
        customer["guarantor"] = profile["guarantor"]
        customer["revenue_hkd"] = profile["revenue_hkd"]
        customer["margin_pct"] = profile["margin_pct"]
        customer["liquidity_ratio"] = profile["liquidity_ratio"]
        customer["leverage"] = profile["leverage"]
        customer["interest_coverage"] = profile["interest_coverage"]
        customer["coverage_assumption"] = profile["coverage_assumption"]
        customer["coverage_threshold"] = profile["coverage_threshold"]
        extract_warnings = []
        if customer["dpd"] > 0:
            extract_warnings.append(f"Portfolio extract at 30 Sep 2026: {customer['dpd']} days past due.")
        if customer["stage"] >= 2:
            extract_warnings.append(f"Stage {customer['stage']} on the portfolio extract at 30 Sep 2026.")
        customer["warnings"] = [{"description": text} for text in extract_warnings + profile["warnings"]]
        customer["watchlist"] = customer["stage"] >= 2 or customer["dpd"] > 0
        cover = profile["interest_coverage"][-1]
        customer["summary"] += (
            f" Relationship manager {profile['rm']} is a demonstration name. "
            f"Demonstration statements, not on the portfolio file: interest cover {cover:.1f} times "
            f"against a {profile['coverage_threshold']:.1f} times covenant."
        )
        customer["documents"]["financials"] = {
            "title": f"Demonstration statements — {customer['legal_name']}",
            "locator": (
                "Apex Group annual review at 31 October 2025, section C3."
                if customer["customer_id"] == "BOR-AGHL"
                else "Placeholder financials for the covenant screen. Not in the uploaded extracts."
            ),
            "passage": (
                f"2024 to 2026 revenue {money_words(profile['revenue_hkd'][0])}, "
                f"{money_words(profile['revenue_hkd'][1])}, {money_words(profile['revenue_hkd'][2])}. "
                f"Interest cover {profile['interest_coverage'][0]:.1f} times, "
                f"{profile['interest_coverage'][1]:.1f} times, {cover:.1f} times. "
                f"Covenant {profile['coverage_threshold']:.1f} times. "
                + (
                    "These are the group figures in the 31 October 2025 annual review."
                    if customer["customer_id"] == "BOR-AGHL"
                    else "Replace these figures when statements are provided."
                )
            ),
        }
        customer["documents"]["review"]["passage"] += (
            " Relationship manager, financial statements and the covenant threshold are demonstration fields."
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


NEWS_FILE = Path(__file__).resolve().parent / "property_data" / "apex_negative_news_v3.xlsx"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SEVERITY_SCORE = {"CRITICAL": 95, "HIGH": 80, "MEDIUM": 60, "LOW": 35}
SEVERITY_EN = {"中": "MEDIUM", "低": "LOW", "高": "HIGH", "严重": "CRITICAL", "嚴重": "CRITICAL"}
PROPERTY_SECTORS = {"香港商業地產市場", "香港零售物業市場"}


def at_latest(customer: dict) -> dict:
    point = customer["history"][-1]
    row = dict(customer)
    for key, value in point.items():
        if key not in {"customer_id", "date", "legal_name", "industry", "facilities"}:
            row[key] = value
    return row


def split_source(source: str) -> tuple[str, str]:
    english = re.search(r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s*$", source)
    if english:
        when = datetime.strptime(english.group(1), "%d %b %Y")
        return source[: english.start()].rstrip(" -"), f"{when.day} {when.strftime('%b %Y')}"
    chinese = re.search(r"（(\d{4})年(\d{1,2})月）", source)
    if chinese:
        year, month = int(chinese.group(1)), int(chinese.group(2))
        return source[: chinese.start()] + source[chinese.end() :], f"{MONTHS[month - 1]} {year}"
    return source, ""


def news_items(customers: list[dict]) -> list[dict]:
    from openpyxl import load_workbook

    latest = [at_latest(customer) for customer in customers]
    by_name = {customer["legal_name"]: customer for customer in latest}
    property_names = [item for item in latest if item["industry"] == "Property Investment"]
    property_drawn = sum(item["drawn_hkd"] for item in property_names)
    property_market = sum(item["collateral_hkd"] for item in property_names)
    property_grades = [item["rating"] for item in property_names]
    sector_factors = {
        "exposure_hkd": property_drawn,
        "security_coverage": f"{property_market / property_drawn:.2f} times market value over drawn, from the collateral extract",
        "guarantor_support": "not an industry-level fact",
        "financial_strength": f"property investment names carry grades {min(property_grades)} to {max(property_grades)} on the portfolio file",
        "warning_signals": "see the Apex negative-news file",
    }
    workbook = load_workbook(NEWS_FILE, data_only=True)
    items = []
    for sheet_no, sheet in enumerate(workbook.worksheets, start=1):
        rows = list(sheet.iter_rows(values_only=True))
        for row in rows[1:]:
            if not row or row[0] is None:
                continue
            number, headline, source, details, news_type, entities, signal, severity = row[:8]
            severity = SEVERITY_EN.get(str(severity or "").strip(), str(severity or "").strip().upper())
            source_name, when = split_source(str(source or ""))
            named = [by_name[part.strip()] for part in str(entities or "").split(",") if part.strip() in by_name]
            customer = named[0] if named else None
            sector = customer is None and any(part.strip() in PROPERTY_SECTORS for part in str(entities or "").split(","))
            score = SEVERITY_SCORE.get(str(severity or "").strip(), 35)
            if customer:
                factors = materiality(customer, direct_hit=True)
                factors["score"] = score
                factors["material"] = score >= 50
                industry = customer["industry"]
                customer_id = customer["customer_id"]
            elif sector:
                factors = dict(sector_factors)
                factors["score"] = score
                factors["material"] = score >= 50
                industry = "Property Investment"
                customer_id = None
            else:
                factors = {
                    "exposure_hkd": 0,
                    "security_coverage": "not a book obligor",
                    "guarantor_support": "not a book obligor",
                    "financial_strength": "not a book obligor",
                    "warning_signals": 0,
                    "score": score,
                    "material": score >= 50,
                }
                industry = str(news_type or "")
                customer_id = None
            items.append(
                {
                    "id": f"NEWS-XLS-{sheet_no}-{int(number):02d}",
                    "headline": str(headline),
                    "source": source_name,
                    "date": when,
                    "severity": str(severity).strip(),
                    "customer_id": customer_id,
                    "industry": industry,
                    "body": (
                        f"{details} News type: {news_type}. Signal: {signal}. "
                        f"Severity: {severity}. Entities: {entities}."
                    ),
                    "factors": factors,
                }
            )
    return items


def documents(borrower, grade, original, drawn, market, net, ltv, addresses, nxt, prior, stage, prior_stage, dpd, ecl, prior_ecl):
    address_text = "; ".join(addresses)
    return {
        "credit_paper": {
            "title": f"Credit extract — {borrower}",
            "locator": "Property portfolio collateral extract, 30 Sep 2026",
            "passage": (
                f"Current grade {grade}. Original grade {original}. On-balance drawn {money_words(drawn)}. "
                f"Property market value {money_words(market)}. Net realizable value {money_words(net)}. "
                f"LTV {ltv:.2f}. Stage {stage}. Days past due {dpd}. ECL {money_words(ecl)}. "
                f"First charge. Properties: {address_text}."
            ),
        },
        "review": {
            "title": f"Position comparison — {borrower}",
            "locator": "Portfolio extract 31 Aug 2026 and 30 Sep 2026",
            "passage": (
                f"Current PD grade {grade} is the grade on every month-end from 31 Dec 2025 through 30 Nov 2026. "
                f"The original grade on the portfolio file is {original}. "
                f"On-balance outstanding moved from {money_words(prior)} on 31 Aug 2026 to {money_words(drawn)} on 30 Sep 2026. "
                f"Stage was {prior_stage} on 31 Aug 2026 and is {stage} on 30 Sep 2026. "
                f"Days past due on 30 Sep 2026 are {dpd}. ECL moved from {money_words(prior_ecl)} to {money_words(ecl)}."
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
            "To: credit.desk@hkbea.example",
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
    property_book = next(item for item in industries if item["industry"] == "Property Investment")
    development = next(item for item in industries if item["industry"] == "Property Development")
    government = next(item for item in industries if item["industry"] == "Government")
    collateral_line = ", ".join(f"{name} {money_words(value)}" for name, value in collateral_split.items())
    portfolio_ltv = drawn / sum(collateral_split.values())
    late = [item for item in customers if item["dpd"] > 0]
    late.sort(key=lambda item: item["legal_name"])
    late_line = "; ".join(
        f"{item['legal_name']} at {item['dpd']} days, drawn {money_words(item['drawn_hkd'])}, ECL {money_words(item['ecl_hkd'])}"
        for item in late
    )
    apex = next(item for item in customers if item["customer_id"] == "BOR-AGHL")
    apex_news = next(item for item in news_feed if item["customer_id"] == apex["customer_id"])
    vacancy = next(item for item in news_feed if item["customer_id"] is None and item["industry"] == "Property Investment")
    news = letter(
        f"Adverse news — {apex['legal_name']}",
        ("MAIL-NEWS-APEX", "Adverse news"),
        apex["customer_id"],
        [
            f"{apex_news['date']}. {apex_news['headline']}.",
            apex_news["body"],
            f"Severity {apex_news['severity']}. Drawn {money_words(apex['drawn_hkd'])}. Collateral coverage {apex['coverage_ratio']}. Guarantor: {apex['guarantor']}. Interest cover on the demonstration statements is {apex['interest_coverage'][-1]:.1f} times.",
            "The other items in the Apex negative-news file are on the adverse-news page.",
            "This note does not downgrade the name, call default, or exit the relationship.",
        ],
    )
    industry = letter(
        "Industry review — Property Investment",
        ("MAIL-IND-WHOLESALE", "Industry stress"),
        "",
        [
            f"{vacancy['date']}. {vacancy['headline']}. {vacancy['body']}",
            f"Property Investment drawn is {money_words(property_book['drawn_hkd'])} across {property_book['customers']} groups. Stage 2 names: {property_book['stage2']}. Migrations since 31 Aug 2026: {property_book['migrations']}. Open warnings: {property_book['open_warnings']}.",
            f"Property Development drawn is {money_words(development['drawn_hkd'])} across {development['customers']} groups. Government drawn is {money_words(government['drawn_hkd'])} across {government['customers']} groups.",
            f"On-balance collateral market value is {collateral_line}. Portfolio LTV on the on-balance collateral is {portfolio_ltv:.2f}. Current PD grades did not change between the December 2025 and November 2026 month-ends.",
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
        "Days past due — portfolio extract",
        ("MAIL-DPD-LANTERN", "Days past due"),
        "",
        [
            f"The portfolio extract at 30 Sep 2026 records days past due on three names: {late_line}.",
            "Stage on each of these names is 2, the same stage as 31 Aug 2026. The days-past-due figure is PAST_DUE_DAY on the portfolio file.",
            "The cash-flow dates above HKD 5,000,000 are future principal dates. This draft does not treat those future dates as past due.",
        ],
    )
    projected = round(apex["interest_coverage"][-1] - 0.6, 1)
    covenant = letter(
        f"Covenant test — {apex['legal_name']}",
        ("MAIL-COV-APEX", "Covenant scenario"),
        apex["customer_id"],
        [
            "The group statements are those used in the 31 October 2025 annual review. They are not the portfolio-extract balances.",
            f"Latest interest cover for {apex['legal_name']} is {apex['interest_coverage'][-1]:.1f} times. The covenant is {apex['coverage_threshold']:.1f} times, so the name is {'inside' if apex['interest_coverage'][-1] >= apex['coverage_threshold'] else 'outside'} the covenant on those statements.",
            f"A revenue decline of 15 percent moves cover to about {projected:.1f} times. Margin, funding cost and liquidity cases are on the financials screen.",
            f"What is from the extract: drawn {money_words(apex['drawn_hkd'])}, property market value {money_words(apex['collateral_hkd'])}, LTV {apex['ltv']:.2f}.",
        ],
    )
    return [news, industry, repayment, ageing, covenant]


WHOLESALE = Path(__file__).resolve().parent / "property_data" / "wholesale"
RDW_FILE = WHOLESALE / "RDW_ECL_Monthly_Dataset.csv"
ANALYTICS_FILE = WHOLESALE / "ECL_MONTHLY_ANALYTICS_202512_202609.csv"
NAME_STOP = {"ltd", "limited", "corp", "corporation", "group", "the", "and", "of", "plc"}


def blank_amount(text: str) -> float:
    text = (text or "").strip()
    if not text:
        return 0.0
    return float(text)


def flagged(text: str) -> bool:
    text = (text or "").strip()
    if text in {"", "0", "0.0", "N", "No", "NO", "n"}:
        return False
    try:
        return float(text) > 0
    except ValueError:
        return True


def as_iso(text: str) -> str:
    text = text.strip()
    if len(text) >= 10 and text[4] == "-":
        return text[:10]
    return datetime.strptime(text, "%d/%m/%Y").strftime("%Y-%m-%d")


def as_dmy(iso: str) -> str:
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")


def security_type(row: dict) -> str:
    kinds = []
    for key, label in (
        ("SECURED_BY_PROP", "Property"),
        ("SECURED_BY_CASH", "Cash"),
        ("SECURED_BY_ACFT", "Aircraft"),
        ("SECURED_BY_OTHE_COL", "Other collateral"),
    ):
        if flagged(row.get(key, "")):
            kinds.append(label)
    if flagged(row.get("SECURED_BY_GUARANTEE", "")):
        kinds.append("Guarantee")
    return ", ".join(kinds) if kinds else "Unsecured"


def borrower_id(name: str, taken: set[str]) -> str:
    words = [word for word in name.replace(".", " ").replace(",", " ").split() if word.lower() not in NAME_STOP]
    code = "".join(word[0] for word in words).upper()[:8] or "X"
    cid = f"BOR-{code}"
    serial = 2
    while cid in taken:
        cid = f"BOR-{code}{serial}"
        serial += 1
    taken.add(cid)
    return cid


def rebuild_portfolio_history(customers: list[dict], dates: list[str]) -> list[dict]:
    previous = {}
    history = []
    for iso in dates:
        points = []
        for customer in customers:
            point = next((item for item in customer["history"] if item["date"] == iso), None)
            if point is not None:
                points.append(point)
        history.append(portfolio_point(iso, points, previous))
        previous = {point["legal_name"]: point["stage"] for point in points}
    return history


def wholesale_facility(row: dict, rdw: dict | None) -> dict:
    balance = blank_amount(row["BAL_OUTSTD"])
    secured = blank_amount(row["SECURED_COL_TOTAL_AMOUNT"])
    kind = security_type(row)
    return {
        "contract": row["CONTRACT_REFERENCE"],
        "instrument": row["INSTRUMENT"],
        "status": row["CONTRACT_STATUS"],
        "department": row["DEPT"],
        "stage": int(float(row["STAGE"])),
        "dpd": int(float(row["PAST_DUE_DAYS"] or 0)),
        "grade": int(float(row["CURRENT_RATING"])),
        "original_grade": int(float(row["ORIGINAL_RATING"])),
        "balance_hkd": round(balance, 2),
        "nominal_hkd": round(blank_amount(row["BAL_NOMINAL"]), 2),
        "limit_hkd": round(blank_amount(row["FACILITY_LIMIT"]), 2),
        "available_hkd": round(blank_amount(row["FACILITY_AVAILABLE"]), 2),
        "ead_hkd": round(blank_amount(row["EAD_POST_CCF"]), 2),
        "pd": float(row["SCN_WGT_ANNUAL_PD"]),
        "lgd": float(row["SCN_WGT_LGD"]),
        "ecl_hkd": round(blank_amount(row["ECL_HKD"]), 2),
        "maturity": as_dmy(as_iso(row["MATURITY_DATE_IS9"])),
        "collateral_id": row["CONTRACT_REFERENCE"],
        "collateral_type": kind,
        "address": "",
        "district": "",
        "market_hkd": round(secured, 2),
        "nrv_hkd": 0,
        "ltv": round(balance / secured, 6) if balance and secured else 0,
        "ltv_nrv": 0,
        "charge": "1" if secured else "",
        "data_health": (rdw or {}).get("DATA_HEALTH_ACTION", ""),
        "rdw_borrower": (rdw or {}).get("BORROWER1", ""),
    }


def wholesale_documents(name: str, rdw_names: list[str], point: dict) -> dict:
    other = ""
    if rdw_names:
        other = " The RDW extract records this borrower as " + "; ".join(rdw_names) + "."
    return {
        "credit_paper": {
            "title": "ECL monthly analytics",
            "locator": "ECL_MONTHLY_ANALYTICS_202512_202609.csv",
            "passage": (
                f"{name} on 30 Sep 2026 is rating {point['rating']}, original rating {point['prior_rating']}, "
                f"stage {point['stage']}, {point['dpd']} days past due, drawn {money_words(point['drawn_hkd'])}, "
                f"ECL {money_words(point['ecl_hkd'])}. Secured amount {money_words(point['collateral_hkd'])}. "
                "The displayed legal name is the analytics name." + other
            ),
        },
        "review": {
            "title": "RDW ECL monthly dataset",
            "locator": "RDW_ECL_Monthly_Dataset.csv",
            "passage": (
                "Outstanding balances match the analytics file. Where the RDW row records a data-health action, "
                "exposure at default uses the analytics figure. Net realizable value and a property address are not in either file."
            ),
        },
        "financials": {
            "title": "Financial statements",
            "locator": "Not in the ECL monthly files",
            "passage": "Revenue, margin, liquidity, leverage and interest cover are not in the uploaded ECL files.",
        },
        "repayment": {
            "title": "Stated maturity",
            "locator": "MATURITY_DATE_IS9",
            "passage": (
                f"No cash-flow schedule was supplied. The next date is the earliest on-balance maturity, "
                f"{point['next_due_date']}, for {money_words(point['next_due_hkd'])}."
            ),
        },
    }


def load_wholesale(taken: set[str]) -> tuple[list[dict], list[dict]]:
    analytics = load(ANALYTICS_FILE)
    rdw_rows = load(RDW_FILE)
    rdw_index = {(row["CONTRACT_REFERENCE"], as_iso(row["REPORTING_DATE"])): row for row in rdw_rows}
    if len(rdw_index) != len(rdw_rows):
        raise RuntimeError("duplicate RDW contract and reporting date")
    by_borrower = defaultdict(lambda: defaultdict(list))
    for row in analytics:
        iso = as_iso(row["REPORTING_DATE"])
        by_borrower[row["BORROWER1"]][iso].append(row)
    customers = []
    for borrower, months in sorted(by_borrower.items()):
        cid = borrower_id(borrower, taken)
        history = []
        previous_stage = None
        previous_ecl = None
        for iso in sorted(months):
            rows = months[iso]
            reporting = datetime.strptime(iso, "%Y-%m-%d")
            facilities = []
            for row in rows:
                facilities.append(wholesale_facility(row, rdw_index.get((row["CONTRACT_REFERENCE"], iso))))
            on_balance = [item for item in facilities if item["instrument"] != "Off-Bal"]
            drawn = round(sum(item["balance_hkd"] for item in on_balance), 2)
            secured = round(sum(item["market_hkd"] for item in on_balance), 2)
            ead = round(sum(item["ead_hkd"] for item in on_balance), 2)
            nominal = round(sum(item["nominal_hkd"] for item in on_balance), 2)
            ecl = round(sum(item["ecl_hkd"] for item in facilities), 2)
            stage = max(item["stage"] for item in facilities)
            dpd = max(item["dpd"] for item in facilities)
            rated = on_balance or facilities
            rating = max(item["grade"] for item in rated)
            anchor = max(on_balance or facilities, key=lambda item: item["balance_hkd"])
            source_anchor = next(row for row in rows if row["CONTRACT_REFERENCE"] == anchor["contract"])
            next_due = None
            for item in on_balance:
                if item["balance_hkd"] <= 0:
                    continue
                maturity = datetime.strptime(item["maturity"], "%d/%m/%Y")
                days = (maturity - reporting).days
                candidate = (days, -item["balance_hkd"], item["maturity"], item["contract"], item["balance_hkd"])
                if next_due is None or candidate < next_due:
                    next_due = candidate
            if next_due is None:
                maturity = datetime.strptime(anchor["maturity"], "%d/%m/%Y")
                next_due = ((maturity - reporting).days, -anchor["balance_hkd"], anchor["maturity"], anchor["contract"], anchor["balance_hkd"])
            history.append({
                "date": iso,
                "legal_name": borrower,
                "customer_id": cid,
                "industry": source_anchor["INDUSTRY_SECTOR"],
                "drawn_hkd": drawn,
                "committed_hkd": round(sum(item["limit_hkd"] for item in facilities), 2),
                "ecl_hkd": ecl,
                "prior_ecl_hkd": previous_ecl if previous_ecl is not None else ecl,
                "stage": stage,
                "prior_stage": previous_stage if previous_stage is not None else stage,
                "dpd": dpd,
                "rating": rating,
                "collateral_hkd": secured,
                "nrv_hkd": 0,
                "ead_hkd": ead,
                "nominal_hkd": nominal,
                "ltv": round(drawn / secured, 2) if secured else None,
                "coverage_ratio": round(secured / drawn, 2) if drawn else None,
                "next_due_days": next_due[0],
                "next_due_hkd": round(next_due[4], 2),
                "next_due_date": next_due[2],
                "next_contract": next_due[3],
                "next_method": "MATURITY",
                "refinancing": False,
                "facilities": facilities,
            })
            previous_stage = stage
            previous_ecl = ecl
        latest = history[-1]
        rdw_names = sorted({
            item["rdw_borrower"]
            for point in history
            for item in point["facilities"]
            if item["rdw_borrower"] and item["rdw_borrower"] != borrower
        })
        original = max(item["original_grade"] for item in latest["facilities"])
        guarantors = sorted({
            (row.get("GUARANTOR") or "").strip()
            for rows in months.values()
            for row in rows
            if (row.get("GUARANTOR") or "").strip()
        })
        actions = sorted({
            item["data_health"]
            for item in latest["facilities"]
            if item["data_health"] and item["data_health"] != "VERIFIED_OK"
        })
        warnings = []
        if any(row["DEFAULT_INDICATOR"] == "Y" for row in months[latest["date"]]):
            warnings.append({"description": "Default indicator is Y on the ECL extract."})
        if any(row["WATCHLIST_INDICATOR"] == "Y" for row in months[latest["date"]]):
            warnings.append({"description": "Watchlist indicator is Y on the ECL extract."})
        if any(row["SICR_INDICATOR"] == "Y" for row in months[latest["date"]]):
            warnings.append({"description": "SICR indicator is Y on the ECL extract."})
        if any(row["RESTRUCTURED_INDICATOR"] == "Y" for row in months[latest["date"]]):
            warnings.append({"description": "Restructured indicator is Y on the ECL extract."})
        if actions:
            warnings.append({"description": "RDW data-health action on the latest month: " + ", ".join(actions) + "."})
        if rdw_names:
            warnings.append({"description": "RDW borrower name differs from the analytics name: " + "; ".join(rdw_names) + "."})
        loans = [item for item in latest["facilities"] if item["instrument"] != "Off-Bal"]
        customers.append({
            "customer_id": cid,
            "legal_name": borrower,
            "group_id": cid,
            "group_name": borrower,
            "rm": f"{len(loans)} on-balance facilities",
            "industry": latest["industry"],
            "jurisdiction": "Not on the ECL extract",
            "rating": latest["rating"],
            "prior_rating": original,
            "prior_rating_date": "original rating on the ECL extract",
            "stage": latest["stage"],
            "prior_stage": latest["prior_stage"],
            "drawn_hkd": latest["drawn_hkd"],
            "committed_hkd": latest["committed_hkd"],
            "collateral_hkd": latest["collateral_hkd"],
            "collateral_type": "Secured amount on the ECL extract",
            "coverage_ratio": latest["coverage_ratio"],
            "ltv": latest["ltv"],
            "guarantor": "; ".join(guarantors) if guarantors else "None on the extract",
            "dpd": latest["dpd"],
            "dpd_component": "Portfolio extract" if latest["dpd"] else "None",
            "ecl_hkd": latest["ecl_hkd"],
            "prior_ecl_hkd": latest["prior_ecl_hkd"],
            "provision_hkd": latest["ecl_hkd"],
            "revenue_hkd": [None, None, None],
            "margin_pct": [None, None, None],
            "liquidity_ratio": [None, None, None],
            "leverage": [None, None, None],
            "interest_coverage": [None, None, None],
            "coverage_assumption": None,
            "coverage_threshold": None,
            "next_due_days": latest["next_due_days"],
            "next_due_hkd": latest["next_due_hkd"],
            "next_due_date": latest["next_due_date"],
            "next_due_source": "Maturity on the ECL extract",
            "next_contract": latest["next_contract"],
            "next_method": "MATURITY",
            "refinancing": False,
            "watchlist": latest["stage"] >= 2 or latest["dpd"] > 0,
            "warnings": warnings,
            "full_file": True,
            "summary": (
                f"{borrower} is on the wholesale ECL extracts for {len(history)} month-ends through {as_dmy(latest['date'])}. "
                f"{len(loans)} on-balance facilities, drawn {money_words(latest['drawn_hkd'])}, "
                f"ECL {money_words(latest['ecl_hkd'])}, stage {latest['stage']}, {latest['dpd']} days past due. "
                "October and November 2026 are not in these files."
            ),
            "documents": wholesale_documents(borrower, rdw_names, {**latest, "prior_rating": original}),
            "repay_draft_id": "",
            "history": history,
            "rdw_legal_names": rdw_names,
            "source": "ECL monthly analytics and RDW ECL monthly dataset",
        })
    sources = [
        {
            "file": "property_data/wholesale/RDW_ECL_Monthly_Dataset.csv",
            "rows": len(rdw_rows),
            "role": "RDW extract, including the data-health action. Balances match the analytics file.",
        },
        {
            "file": "property_data/wholesale/ECL_MONTHLY_ANALYTICS_202512_202609.csv",
            "rows": len(analytics),
            "role": "Analytics extract. Stage, sector, PD, LGD, security and the displayed legal name come from this file.",
        },
    ]
    return customers, sources


if __name__ == "__main__":
    main()
