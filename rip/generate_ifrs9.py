"""Regenerate IFRS 9 cash-flow and collateral extracts from the property portfolio.

Rules match the previous generation: semiannual dates counted back from
maturity, contract-stable coupon and amortization, present value of interest
plus principal within half a cent of the outstanding balance, and one
collateral row per contract with a stable fictional address.
"""

from __future__ import annotations

import csv
import calendar
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "property_data" / "source"
OUT = ROOT / "property_data" / "generated"

CENT = Decimal("0.01")
HALF_CENT = Decimal("0.005")
SIX = Decimal("0.000001")

# Contract-stable coupon and amortization. The 40 customer loans stay
# 24 bullet / 12 equal / 4 declining. The bond is extra and is bullet at
# the borrower's coupon.
TERMS = {
    "CTR-0001-01": ("0.030000", "BULLET"),
    "CTR-0001-02": ("0.030000", "BULLET"),
    "CTR-0001-03": ("0.030000", "EQUAL_AMORT"),
    "CTR-0001-04": ("0.030000", "EQUAL_AMORT"),
    "CTR-0002-01": ("0.030000", "BULLET"),
    "CTR-0002-02": ("0.030000", "BULLET"),
    "CTR-0002-03": ("0.030000", "EQUAL_AMORT"),
    "CTR-0002-04": ("0.030000", "BULLET"),
    "CTR-0003-01": ("0.050000", "BULLET"),
    "CTR-0003-02": ("0.050000", "BULLET"),
    "CTR-0003-03": ("0.050000", "EQUAL_AMORT"),
    "CTR-0003-04": ("0.050000", "DECLINING_AMORT"),
    "CTR-0004-01": ("0.055000", "BULLET"),
    "CTR-0004-02": ("0.055000", "BULLET"),
    "CTR-0004-03": ("0.055000", "EQUAL_AMORT"),
    "CTR-0004-04": ("0.055000", "BULLET"),
    "CTR-0005-01": ("0.060000", "BULLET"),
    "CTR-0005-02": ("0.060000", "BULLET"),
    "CTR-0005-03": ("0.060000", "EQUAL_AMORT"),
    "CTR-0005-04": ("0.060000", "BULLET"),
    "CTR-0006-01": ("0.060000", "BULLET"),
    "CTR-0006-02": ("0.060000", "BULLET"),
    "CTR-0006-03": ("0.060000", "EQUAL_AMORT"),
    "CTR-0006-04": ("0.060000", "EQUAL_AMORT"),
    "CTR-0007-01": ("0.050000", "BULLET"),
    "CTR-0007-02": ("0.050000", "BULLET"),
    "CTR-0007-03": ("0.050000", "EQUAL_AMORT"),
    "CTR-0007-04": ("0.050000", "DECLINING_AMORT"),
    "CTR-0008-01": ("0.055000", "BULLET"),
    "CTR-0008-02": ("0.055000", "BULLET"),
    "CTR-0008-03": ("0.055000", "EQUAL_AMORT"),
    "CTR-0008-04": ("0.055000", "BULLET"),
    "CTR-0009-01": ("0.045000", "BULLET"),
    "CTR-0009-02": ("0.045000", "BULLET"),
    "CTR-0009-03": ("0.045000", "EQUAL_AMORT"),
    "CTR-0009-04": ("0.045000", "DECLINING_AMORT"),
    "CTR-0010-01": ("0.055000", "BULLET"),
    "CTR-0010-02": ("0.055000", "BULLET"),
    "CTR-0010-03": ("0.055000", "EQUAL_AMORT"),
    "CTR-0010-04": ("0.055000", "DECLINING_AMORT"),
    "CTR-0010-06": ("0.055000", "BULLET"),
}

GOVERNMENT = {"Metro Gov Authority A", "State Treasury Bureau B"}

FLOW_COLUMNS = [
    "TABLE_NAME",
    "CONTRACT_REFERENCE",
    "BORROWER_NAME",
    "BORROWER_GRADE",
    "CURRENT_PD_GRADE",
    "CCY_CODE",
    "DISCOUNT_RATE",
    "AMORTIZATION_METHOD",
    "CASH_FLOW_DATE",
    "CASH_FLOW_TYPE",
    "CASH_FLOW_AMOUNT",
    "OUTSTANDING",
]
COLLATERAL_COLUMNS = [
    "REPORTING_DATE",
    "CONTRACT_REFERENCE",
    "COLLATERAL_REFERENCE",
    "BORROWER_NAME",
    "INSTRUMENT",
    "COLLATERAL_TYPE",
    "CCY_CODE",
    "PROPERTY_ADDRESS",
    "DISTRICT",
    "CHARGE_RANK",
    "VALUATION_DATE",
    "MARKET_VALUE_HKD",
    "NET_REALIZABLE_VALUE_HKD",
    "BAL_OUTSTD_HKD",
    "LTV",
    "LTV_ON_NRV",
]

RESIDENTIAL = [
    ("Central", "Meridian Court", "Meridian Lane"),
    ("Central", "Harbourlight House", "Ice House Street"),
    ("Mid-Levels", "Caine Residences", "Caine Road"),
    ("Mid-Levels", "Robinson Chambers", "Robinson Road"),
    ("Admiralty", "Queensway Lodge", "Queensway"),
    ("Wan Chai", "Lockhart House", "Lockhart Road"),
    ("Wan Chai", "Hennessy Court", "Hennessy Road"),
    ("Causeway Bay", "Percival Place", "Percival Street"),
    ("Happy Valley", "Blue Pool House", "Blue Pool Road"),
    ("North Point", "Java Court", "Java Road"),
    ("Quarry Bay", "King's Residences", "King's Road"),
    ("Tsim Sha Tsui", "Nathan House", "Nathan Road"),
    ("Tsim Sha Tsui", "Kimberley Court", "Kimberley Road"),
    ("Mong Kok", "Argyle Residences", "Argyle Street"),
    ("Kowloon Tong", "Waterloo Lodge", "Waterloo Road"),
    ("Ho Man Tin", "Princess Court", "Princess Margaret Road"),
    ("Sha Tin", "Sha Tin Heights", "Tai Po Road"),
    ("Tai Po", "Tai Po Garden", "Kwong Fuk Road"),
    ("Tsuen Wan", "Castle Peak Lodge", "Castle Peak Road"),
    ("Tuen Mun", "Tuen Mun Court", "Tuen Mun Heung Sze Wui Road"),
]
COMMERCIAL = [
    ("Central", "Exchange Tower", "Connaught Road Central"),
    ("Central", "Pedder Place", "Pedder Street"),
    ("Admiralty", "Pacific Annex", "Harcourt Road"),
    ("Wan Chai", "Gloucester House", "Gloucester Road"),
    ("Causeway Bay", "Russell Centre", "Russell Street"),
    ("Tsim Sha Tsui", "Canton Tower", "Canton Road"),
    ("Mong Kok", "Portland Centre", "Portland Street"),
    ("Kowloon Bay", "Wang Kwong Centre", "Wang Kwong Road"),
    ("Kwun Tong", "Hoi Yuen Place", "Hoi Yuen Road"),
    ("Cheung Sha Wan", "Cheung Sha Centre", "Cheung Sha Wan Road"),
    ("Quarry Bay", "Westlands Annex", "Westlands Road"),
    ("North Point", "King's Commerce", "King's Road"),
    ("Sheung Wan", "Bonham Tower", "Bonham Strand"),
    ("Jordan", "Austin Centre", "Austin Road"),
    ("San Po Kong", "Tseuk Luk Place", "Tseuk Luk Street"),
]


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def parse_iso(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def fmt(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def shift_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    end_of_month = day.day == calendar.monthrange(day.year, day.month)[1]
    last = calendar.monthrange(year, month)[1]
    return date(year, month, last if end_of_month else min(day.day, last))


def payment_dates(maturity: date, reporting: date) -> list[date]:
    """Semiannual dates from maturity back to the reporting date.

    Dates strictly before the reporting date are dropped. A maturity that
    falls on the reporting date is kept: the balance is still outstanding
    and is repaid that day, discounted as period 1.
    """
    if maturity < reporting:
        raise ValueError(f"maturity {maturity} is before reporting {reporting}")
    found = []
    cursor = maturity
    for _ in range(80):
        if cursor < reporting:
            break
        if cursor > reporting or cursor == maturity:
            found.append(cursor)
        cursor = shift_months(cursor, -6)
    else:
        raise ValueError(f"date walk did not finish for {maturity}")
    found.sort()
    if not found or found[-1] != maturity:
        raise ValueError(f"schedule for {maturity} does not end on maturity")
    return found


def principal_parts(balance: Decimal, count: int, method: str) -> list[Decimal]:
    cents = int((balance * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if method == "BULLET":
        parts = [0] * (count - 1) + [cents]
    elif method == "EQUAL_AMORT":
        each = cents // count
        parts = [each] * count
        parts[-1] = cents - each * (count - 1)
    elif method == "DECLINING_AMORT":
        weights = list(range(count, 0, -1))
        weight_sum = sum(weights)
        parts = [cents * weight // weight_sum for weight in weights]
        parts[-1] = cents - sum(parts[:-1])
    else:
        raise ValueError(method)
    return [Decimal(part) / 100 for part in parts]


def contractual_interest(opening: Decimal, rate: Decimal) -> Decimal:
    return money(opening * rate * Decimal("0.5"))


def present_value(pairs: list[tuple[Decimal, Decimal]], rate: Decimal) -> Decimal:
    factor = Decimal(1) + rate / Decimal(2)
    total = Decimal(0)
    for period, (interest, principal) in enumerate(pairs, start=1):
        total += (interest + principal) / (factor ** period)
    return total


def fit_interest(
    pairs: list[tuple[Decimal, Decimal]], rate: Decimal, balance: Decimal
) -> tuple[list[tuple[Decimal, Decimal]], int]:
    fitted = list(pairs)
    steps = 0
    for _ in range(5000):
        gap = present_value(fitted, rate) - balance
        if abs(gap) <= HALF_CENT:
            return fitted, steps
        interest, principal = fitted[-1]
        interest = interest - CENT if gap > 0 else interest + CENT
        if interest < 0:
            raise RuntimeError("interest nudge crossed zero")
        fitted[-1] = (interest, principal)
        steps += 1
    raise RuntimeError("present value did not converge")


def cash_flows_for(row: dict, rate: Decimal, method: str) -> list[dict]:
    reporting = parse_iso(row["REPORTING_DATE"])
    maturity = parse_iso(row["MATURITY_DATE"])
    balance = money(Decimal(row["BAL_OUTSTD"]))
    dates = payment_dates(maturity, reporting)
    principals = principal_parts(balance, len(dates), method)
    opening = balance
    rough = []
    outstanding_before = []
    for principal in principals:
        interest = contractual_interest(opening, rate)
        outstanding_before.append(opening)
        rough.append((interest, principal))
        opening = money(opening - principal)
    if opening != 0:
        raise RuntimeError(f"{row['CONTRACT_REFERENCE']} principal does not clear")
    fitted, _steps = fit_interest(rough, rate, balance)
    output = []
    for when, before, (interest, principal) in zip(dates, outstanding_before, fitted):
        after = money(before - principal)
        base = {
            "TABLE_NAME": "CASH_FLOW",
            "CONTRACT_REFERENCE": row["CONTRACT_REFERENCE"],
            "BORROWER_NAME": row["BORROWER1"],
            "BORROWER_GRADE": row["BORROWER_GRADE"],
            "CURRENT_PD_GRADE": row["CURRENT_PD_GRADE"],
            "CCY_CODE": row["CCY"],
            "DISCOUNT_RATE": f"{rate:.6f}",
            "AMORTIZATION_METHOD": method,
            "CASH_FLOW_DATE": fmt(when),
            "REPORTING_DATE": fmt(reporting),
        }
        output.append({**base, "CASH_FLOW_TYPE": "I", "CASH_FLOW_AMOUNT": f"{interest:.2f}", "OUTSTANDING": f"{before:.2f}"})
        if principal > 0:
            output.append({**base, "CASH_FLOW_TYPE": "N", "CASH_FLOW_AMOUNT": f"{principal:.2f}", "OUTSTANDING": f"{after:.2f}"})
    return output


def address_book(rows: list[dict]) -> dict[str, tuple[str, str]]:
    by_type = defaultdict(list)
    for row in rows:
        by_type[row["COLLATERAL_TYPE"]].append(row["COLLATERAL_ID"])
    book = {}
    pools = {
        "Residential Property": RESIDENTIAL,
        "Commercial Property": COMMERCIAL,
    }
    for kind, ids in by_type.items():
        pool = pools[kind]
        for index, collateral_id in enumerate(sorted(set(ids))):
            district, building, street = pool[index % len(pool)]
            number = 8 + index * 2
            floor = 3 + (index % 30)
            if kind == "Residential Property":
                flat = "ABCDEFGH"[index % 8]
                address = f"Flat {flat}, {floor}/F, {building}, {number} {street}, {district}"
            else:
                address = f"Unit {101 + index}, {floor}/F, {building}, {number} {street}, {district}"
            book[collateral_id] = (address, district)
    return book


def collateral_row(row: dict, address: str, district: str) -> dict:
    reporting = fmt(parse_iso(row["REPORTING_DATE"]))
    balance = money(Decimal(row["BAL_OUTSTD"]))
    market = money(Decimal(row["MARKET_VALUE_HKD"]))
    nrv = money(Decimal(row["NET_REALIZABLE_VALUE_HKD"]))
    if balance == 0:
        ltv = ltv_nrv = Decimal("0.000000")
    else:
        ltv = (balance / market).quantize(SIX, rounding=ROUND_HALF_UP)
        ltv_nrv = (balance / nrv).quantize(SIX, rounding=ROUND_HALF_UP)
    return {
        "REPORTING_DATE": reporting,
        "CONTRACT_REFERENCE": row["CONTRACT_REFERENCE"],
        "COLLATERAL_REFERENCE": row["COLLATERAL_ID"],
        "BORROWER_NAME": row["BORROWER1"],
        "INSTRUMENT": row["INSTRUMENT"],
        "COLLATERAL_TYPE": row["COLLATERAL_TYPE"],
        "CCY_CODE": row["CCY"],
        "PROPERTY_ADDRESS": address,
        "DISTRICT": district,
        "CHARGE_RANK": "1",
        "VALUATION_DATE": reporting,
        "MARKET_VALUE_HKD": f"{market:.2f}",
        "NET_REALIZABLE_VALUE_HKD": f"{nrv:.2f}",
        "BAL_OUTSTD_HKD": f"{balance:.2f}",
        "LTV": f"{ltv:.6f}",
        "LTV_ON_NRV": f"{ltv_nrv:.6f}",
    }


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_xlsx(path: Path, columns: list[str], sheets: list[tuple[str, list[dict]]]) -> None:
    book = Workbook()
    book.remove(book.active)
    for name, rows in sheets:
        sheet = book.create_sheet(name[:31])
        sheet.append(columns)
        for row in rows:
            sheet.append([row[column] for column in columns])
        sheet.auto_filter.ref = sheet.dimensions
        sheet.freeze_panes = "A2"
    path.parent.mkdir(parents=True, exist_ok=True)
    book.save(path)


def load_months() -> list[tuple[str, list[dict]]]:
    months = []
    for path in sorted(SOURCE.glob("IFRS9_Property_Portfolio_*.csv")):
        stamp = path.stem.rsplit("_", 1)[-1].replace("-", "")
        with path.open(encoding="utf-8-sig", newline="") as handle:
            months.append((stamp, list(csv.DictReader(handle))))
    if len(months) != 12:
        raise RuntimeError(f"expected 12 monthly files, found {len(months)}")
    return months


def validate(flow_rows: list[dict], collateral_rows: list[dict], months: list[tuple[str, list[dict]]]) -> list[str]:
    notes = []
    by_contract = defaultdict(list)
    for row in flow_rows:
        by_contract[(row["REPORTING_DATE"], row["CONTRACT_REFERENCE"])].append(row)
    method_counts = defaultdict(int)
    bond_count = 0
    same_day = []
    max_gap = Decimal(0)
    for (reporting, contract), rows in by_contract.items():
        rate = Decimal(rows[0]["DISCOUNT_RATE"])
        method = rows[0]["AMORTIZATION_METHOD"]
        principal = sum(Decimal(row["CASH_FLOW_AMOUNT"]) for row in rows if row["CASH_FLOW_TYPE"] == "N")
        opening = Decimal(rows[0]["OUTSTANDING"])
        if principal != opening:
            raise RuntimeError(f"{contract} {reporting} principal {principal} != {opening}")
        if Decimal(rows[-1]["OUTSTANDING"]) != 0 or rows[-1]["CASH_FLOW_TYPE"] != "N":
            raise RuntimeError(f"{contract} {reporting} does not end at zero")
        pairs = []
        pending_interest = None
        for row in rows:
            amount = Decimal(row["CASH_FLOW_AMOUNT"])
            if row["CASH_FLOW_TYPE"] == "I":
                if pending_interest is not None:
                    pairs.append((pending_interest, Decimal(0)))
                pending_interest = amount
            else:
                pairs.append((pending_interest if pending_interest is not None else Decimal(0), amount))
                pending_interest = None
        if pending_interest is not None:
            pairs.append((pending_interest, Decimal(0)))
        gap = abs(present_value(pairs, rate) - opening)
        max_gap = max(max_gap, gap)
        if gap > HALF_CENT:
            raise RuntimeError(f"{contract} {reporting} PV gap {gap}")
        maturity = datetime.strptime(rows[-1]["CASH_FLOW_DATE"], "%d/%m/%Y").date()
        report = datetime.strptime(reporting, "%d/%m/%Y").date()
        for row in rows:
            flow_date = datetime.strptime(row["CASH_FLOW_DATE"], "%d/%m/%Y").date()
            if flow_date > maturity or flow_date < report:
                raise RuntimeError(f"{contract} date {flow_date} outside {report}..{maturity}")
        if report == maturity:
            same_day.append(f"{reporting} {contract} {opening:.2f}")
        if contract == "CTR-0010-06":
            bond_count += 1
            if method != "BULLET" or rate != Decimal("0.055000"):
                raise RuntimeError("bond terms drifted")
        else:
            method_counts[method] += 1
    if method_counts["BULLET"] != 24 * 12 or method_counts["EQUAL_AMORT"] != 12 * 12 or method_counts["DECLINING_AMORT"] != 4 * 12:
        raise RuntimeError(f"amortization mix {dict(method_counts)}")
    if bond_count != 12:
        raise RuntimeError(f"bond months {bond_count}")
    addresses = {}
    per_month = defaultdict(int)
    for row in collateral_rows:
        per_month[row["REPORTING_DATE"]] += 1
        key = row["COLLATERAL_REFERENCE"]
        current = (row["PROPERTY_ADDRESS"], row["DISTRICT"])
        if key in addresses and addresses[key] != current:
            raise RuntimeError(f"{key} address changed")
        addresses[key] = current
        balance = Decimal(row["BAL_OUTSTD_HKD"])
        market = Decimal(row["MARKET_VALUE_HKD"])
        nrv = Decimal(row["NET_REALIZABLE_VALUE_HKD"])
        if balance == 0:
            if Decimal(row["LTV"]) != 0 or Decimal(row["LTV_ON_NRV"]) != 0:
                raise RuntimeError("zero balance LTV")
        else:
            expect = (balance / market).quantize(SIX, rounding=ROUND_HALF_UP)
            expect_nrv = (balance / nrv).quantize(SIX, rounding=ROUND_HALF_UP)
            if Decimal(row["LTV"]) != expect or Decimal(row["LTV_ON_NRV"]) != expect_nrv:
                raise RuntimeError(f"LTV mismatch {row['CONTRACT_REFERENCE']} {row['REPORTING_DATE']}")
        if row["CHARGE_RANK"] != "1" or row["VALUATION_DATE"] != row["REPORTING_DATE"]:
            raise RuntimeError("charge or valuation date")
        if row["CCY_CODE"] != "HKD":
            raise RuntimeError("currency")
    if any(count != 60 for count in per_month.values()) or len(per_month) != 12:
        raise RuntimeError(f"collateral month counts {dict(per_month)}")
    source_positive = 0
    for _stamp, rows in months:
        for row in rows:
            if Decimal(row["BAL_OUTSTD"]) > 0:
                source_positive += 1
                if row["CONTRACT_REFERENCE"] not in TERMS and row["INSTRUMENT"] != "Off-Bal":
                    raise RuntimeError(f"no terms for {row['CONTRACT_REFERENCE']}")
    notes.append(f"Cash-flow contract-months: {len(by_contract)} (40 customer loans + 1 bond, each month).")
    notes.append("Customer-loan amortization across 12 months: 24 bullet, 12 equal, 4 declining, unchanged by contract.")
    notes.append("Bond CTR-0010-06 is included because its outstanding balance is positive. It is bullet at 5.5%.")
    notes.append("Off-balance facilities with zero outstanding are excluded from cash flow and kept on collateral with LTV 0.")
    notes.append(f"Largest present-value gap: {max_gap} (limit 0.005).")
    notes.append("Loans whose maturity equals the reporting date, kept as one discounted repayment that day:")
    notes.extend(f"  {item}" for item in same_day)
    notes.append(f"Collateral rows: {len(collateral_rows)}. Distinct collateral addresses: {len(addresses)}.")
    notes.append(f"Source rows with a positive balance: {source_positive}.")
    return notes


def main() -> None:
    months = load_months()
    first_rows = months[0][1]
    addresses = address_book(first_rows)
    flow_all = []
    collateral_all = []
    flow_sheets = []
    collateral_sheets = []
    amortization = []
    seen_terms = set()
    for stamp, rows in months:
        month_flows = []
        month_collateral = []
        for row in rows:
            address, district = addresses[row["COLLATERAL_ID"]]
            month_collateral.append(collateral_row(row, address, district))
            if Decimal(row["BAL_OUTSTD"]) <= 0:
                continue
            if row["INSTRUMENT"] == "Off-Bal":
                raise RuntimeError("Off-Bal row has a balance")
            rate_text, method = TERMS[row["CONTRACT_REFERENCE"]]
            rate = Decimal(rate_text)
            if row["BORROWER1"] in GOVERNMENT and rate != Decimal("0.030000"):
                raise RuntimeError("government coupon")
            if row["CCY"] != "HKD":
                raise RuntimeError("currency")
            month_flows.extend(cash_flows_for(row, rate, method))
            if row["CONTRACT_REFERENCE"] not in seen_terms:
                seen_terms.add(row["CONTRACT_REFERENCE"])
                amortization.append({
                    "CONTRACT_REFERENCE": row["CONTRACT_REFERENCE"],
                    "BORROWER_NAME": row["BORROWER1"],
                    "INSTRUMENT": row["INSTRUMENT"],
                    "DISCOUNT_RATE": rate_text,
                    "AMORTIZATION_METHOD": method,
                })
        label = f"{stamp[:4]}-{stamp[4:]}"
        write_csv(OUT / "cashflow" / f"CASH_FLOW_{stamp}.csv", FLOW_COLUMNS, month_flows)
        write_csv(OUT / "collateral" / f"COLLATERAL_{stamp}.csv", COLLATERAL_COLUMNS, month_collateral)
        flow_all.extend(month_flows)
        collateral_all.extend(month_collateral)
        flow_sheets.append((label, month_flows))
        collateral_sheets.append((label, month_collateral))
    flow_columns = ["REPORTING_DATE", *FLOW_COLUMNS]
    write_csv(OUT / "cashflow" / "CASH_FLOW_ALL.csv", flow_columns, flow_all)
    write_csv(OUT / "collateral" / "COLLATERAL_ALL.csv", COLLATERAL_COLUMNS, collateral_all)
    write_csv(ROOT / "property_data" / "CASH_FLOW_ALL_2026.csv", flow_columns, flow_all)
    write_csv(ROOT / "property_data" / "COLLATERAL_ALL_2026.csv", COLLATERAL_COLUMNS, collateral_all)
    write_csv(
        OUT / "CONTRACT_AMORTIZATION.csv",
        ["CONTRACT_REFERENCE", "BORROWER_NAME", "INSTRUMENT", "DISCOUNT_RATE", "AMORTIZATION_METHOD"],
        amortization,
    )
    write_xlsx(OUT / "cashflow" / "Cash_Flow.xlsx", flow_columns, [("All", flow_all), *flow_sheets])
    write_xlsx(OUT / "collateral" / "Collateral.xlsx", COLLATERAL_COLUMNS, [("All", collateral_all), *collateral_sheets])
    notes = validate(flow_all, collateral_all, months)
    text = "\n".join(notes) + "\n"
    (OUT / "VALIDATION.txt").write_text(text, encoding="utf-8")
    print(text)
    print(f"cash-flow rows {len(flow_all)}")
    print(f"collateral rows {len(collateral_all)}")


if __name__ == "__main__":
    main()
