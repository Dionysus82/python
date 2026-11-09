"""Write a demonstration proposal and monitoring report for every obligor.

The layout follows the Apex annual-review paper. Figures come from the latest
month on each obligor's extract. The narrative is illustrative.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent
BOOK = ROOT / "book.json"
OUT = ROOT / "report_files" / "obligors"
NAVY = "1F4E79"
AMBER = "8C3E16"


def shade(cell, hex_color: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), hex_color)
    shd.set(qn("w:val"), "clear")
    tc_pr.append(shd)


def set_run(run, text, *, bold=False, size=10.5, color=None, italic=False) -> None:
    run.text = text
    run.bold = bold
    run.italic = italic
    run.font.size = Pt(size)
    run.font.name = "Calibri"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def para(doc, text, *, bold=False, size=10.5, space_after=8, italic=False, color=None):
    block = doc.add_paragraph()
    block.paragraph_format.space_after = Pt(space_after)
    block.paragraph_format.space_before = Pt(0)
    block.paragraph_format.line_spacing = 1.08
    set_run(block.add_run(), text, bold=bold, size=size, italic=italic, color=color)
    return block


def heading(doc, text):
    block = doc.add_paragraph()
    block.paragraph_format.space_before = Pt(14)
    block.paragraph_format.space_after = Pt(6)
    set_run(block.add_run(), text, bold=True, size=13, color=NAVY)
    return block


def subhead(doc, text):
    block = doc.add_paragraph()
    block.paragraph_format.space_before = Pt(8)
    block.paragraph_format.space_after = Pt(4)
    set_run(block.add_run(), text, bold=True, size=11, color=AMBER)
    return block


def table(doc, headers, rows, widths=None):
    tbl = doc.add_table(rows=1 + len(rows), cols=len(headers))
    tbl.style = "Table Grid"
    tbl.autofit = True
    for i, header in enumerate(headers):
        cell = tbl.rows[0].cells[i]
        cell.text = ""
        shade(cell, NAVY)
        set_run(cell.paragraphs[0].add_run(), header, bold=True, size=9, color="FFFFFF")
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            cell = tbl.rows[r + 1].cells[c]
            cell.text = ""
            if r % 2 == 1:
                shade(cell, "F4F7FB")
            last = r == len(rows) - 1 and str(row[0]).lower().startswith("total")
            set_run(cell.paragraphs[0].add_run(), str(value), bold=last or c == 0, size=9)
    if widths:
        for row in tbl.rows:
            for cell, width in zip(row.cells, widths):
                cell.width = Cm(width)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return tbl


def blank_doc() -> Document:
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Cm(1.6)
    section.bottom_margin = Cm(1.6)
    section.left_margin = Cm(1.6)
    section.right_margin = Cm(1.6)
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    return doc


def hkd(value) -> str:
    if value is None:
        return "—"
    number = float(value)
    if abs(number - round(number)) < 0.005:
        return f"HK${number:,.0f}"
    return f"HK${number:,.2f}"


def label_date(iso: str) -> str:
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%-d %B %Y")


def next_year(iso: str) -> str:
    parsed = datetime.strptime(iso, "%Y-%m-%d")
    return parsed.replace(year=parsed.year + 1).strftime("%-d %B %Y")


def person(customer: dict) -> str:
    name = customer.get("rm") or ""
    if "facilit" in name.lower() or not name.strip():
        return "Not named on the ECL extract"
    return name


def address_of(facility: dict) -> str:
    address = (facility.get("address") or "").strip()
    district = (facility.get("district") or "").strip()
    if address and district and district not in address:
        return f"{address}, {district}, Hong Kong"
    if address:
        return address if address.endswith("Hong Kong") else f"{address}, Hong Kong"
    return "Not on the ECL extract"


def stance(point: dict) -> str:
    if point["stage"] >= 3 or point["dpd"] >= 90:
        return (
            "The extract shows a weak position. This demonstration recommends enhanced monitoring, "
            "no new money, and a review of collateral and any past-due amount before the next annual date."
        )
    if point["stage"] == 2 or point["dpd"] > 0:
        return (
            "The extract shows heightened risk. This demonstration recommends maintaining the present facilities "
            "and keeping the name on the watch list until the next review."
        )
    return (
        "The extract shows a performing position. This demonstration recommends maintaining the facilities "
        "at annual review, with no new money in this paper."
    )


def facility_rows(point: dict) -> list[list[str]]:
    rows = []
    for item in point["facilities"]:
        rows.append([
            item["contract"],
            item["instrument"],
            item.get("status") or "",
            hkd(item["balance_hkd"]),
            hkd(item["limit_hkd"]),
            hkd(item["ecl_hkd"]),
            str(item["stage"]),
            str(item["dpd"]),
            item.get("maturity") or "",
        ])
    on_balance = [item for item in point["facilities"] if item["instrument"] != "Off-Bal"]
    rows.append([
        "Total on-balance",
        "",
        "",
        hkd(point["drawn_hkd"]),
        hkd(sum(item["limit_hkd"] for item in on_balance)),
        hkd(point["ecl_hkd"]),
        str(point["stage"]),
        str(point["dpd"]),
        "",
    ])
    return rows


def collateral_rows(point: dict) -> list[list[str]]:
    rows = []
    for item in point["facilities"]:
        if item["instrument"] == "Off-Bal" and not item.get("market_hkd") and not (item.get("address") or "").strip():
            continue
        rows.append([
            item["contract"],
            item.get("collateral_type") or "Unsecured",
            address_of(item),
            hkd(item.get("market_hkd")),
            f"{item['ltv']:.2f}" if item.get("market_hkd") else "—",
        ])
    if not rows:
        rows.append(["—", "No collateral amount on the extract", "Not on the ECL extract", "—", "—"])
    rows.append(["Total", "", "", hkd(point.get("collateral_hkd")), ""])
    return rows


def warning_lines(customer: dict) -> list[str]:
    lines = [item["description"] for item in customer.get("warnings") or [] if item.get("description")]
    return lines[:6]


def build_proposal(customer: dict, point: dict) -> Document:
    doc = blank_doc()
    as_of = label_date(point["date"])
    kicker = doc.add_paragraph()
    set_run(kicker.add_run(), "SUBJECT CREDIT PROPOSAL", bold=True, size=9, color=NAVY)
    title = doc.add_paragraph()
    title.paragraph_format.space_after = Pt(2)
    set_run(title.add_run(), f"Annual Review — {customer['legal_name']}", bold=True, size=20, color=NAVY)
    sub = doc.add_paragraph()
    set_run(sub.add_run(), f"BEA - Risk Intelligence  ·  Position {as_of}  ·  {customer['customer_id']}", size=12, color=AMBER)
    para(
        doc,
        "Demonstration annual-review proposal. Figures are the latest month on the property extract or the ECL monthly files. The narrative illustrates the report function and is not a credit decision.",
        italic=True,
        size=9,
        color="666666",
    )
    heading(doc, "Proposal type")
    table(doc, ["Type", "Selected"], [
        ["New application", "No"],
        ["Limit increase", "No"],
        ["Annual renewal / review", "Yes"],
        ["Others", "Demonstration paper for the report function"],
    ])
    heading(doc, "Signing section")
    aliases = customer.get("rdw_legal_names") or []
    alias = "; ".join(aliases) if aliases else "Same name on the RDW extract, or not applicable"
    table(doc, ["Role", "Name"], [
        ["Borrower", customer["legal_name"]],
        ["RDW name, where different", alias],
        ["Guarantor", customer.get("guarantor") or "None on the extract"],
        ["Industry", customer.get("industry") or ""],
        ["Current PD grade", str(point["rating"])],
        ["Original PD grade", str(customer.get("prior_rating"))],
        ["Stage / days past due", f"Stage {point['stage']} / {point['dpd']} days"],
        ["Relationship manager", person(customer)],
        ["Prepared for", "BEA - Risk Intelligence"],
    ], [6.5, 11.0])
    heading(doc, "Approval section")
    table(doc, ["Item", "Date"], [
        ["Position used for this paper", as_of],
        ["Proposed next review", next_year(point["date"])],
        ["Date of approval", "Demonstration only. Not submitted."],
    ])
    para(doc, stance(point) + f" Drawn exposure is {hkd(point['drawn_hkd'])} and ECL is {hkd(point['ecl_hkd'])}.")
    heading(doc, "A. Facility section")
    subhead(doc, "A1 : Facility overview")
    table(
        doc,
        ["Contract", "Instrument", "Status", "Balance", "Limit", "ECL", "Stage", "DPD", "Maturity"],
        facility_rows(point),
    )
    subhead(doc, "A5 : Security details and coverage")
    table(
        doc,
        ["Contract", "Security", "Address", "Latest valuation", "LTV"],
        collateral_rows(point),
    )
    coverage = point.get("coverage_ratio")
    ltv = point.get("ltv")
    para(
        doc,
        f"Collateral recorded on the extract is {hkd(point.get('collateral_hkd'))}. "
        f"Coverage of drawn exposure is {coverage if coverage is not None else '—'}. "
        f"Portfolio LTV on that collateral is {ltv if ltv is not None else '—'}. "
        "An address is the property address on the collateral extract. Where the ECL file has no address, the cell says so.",
    )
    subhead(doc, "A6 : Loan classification and internal rating")
    table(doc, ["Item", "Position"], [
        ["Current PD grade", str(point["rating"])],
        ["Original PD grade", str(customer.get("prior_rating"))],
        ["Stage", str(point["stage"])],
        ["Days past due", str(point["dpd"])],
        ["ECL", hkd(point["ecl_hkd"])],
        ["EAD", hkd(point.get("ead_hkd"))],
    ])
    notes = warning_lines(customer)
    if notes:
        para(doc, "Points carried from the extract: " + " ".join(notes))
    heading(doc, "Recommendation")
    para(doc, stance(point) + " This paper does not change a grade, call default, or approve a new limit.")
    return doc


def build_report(customer: dict, point: dict) -> Document:
    doc = blank_doc()
    as_of = label_date(point["date"])
    kicker = doc.add_paragraph()
    set_run(kicker.add_run(), "BEA - RISK INTELLIGENCE  ·  ANNUAL REVIEW", bold=True, size=9, color=NAVY)
    title = doc.add_paragraph()
    title.paragraph_format.space_after = Pt(2)
    set_run(title.add_run(), f"{customer['legal_name']} Credit Monitoring Report", bold=True, size=20, color=NAVY)
    sub = doc.add_paragraph()
    set_run(sub.add_run(), f"Detailed level  ·  Position {as_of}  ·  {customer['customer_id']}", size=12, color=AMBER)
    para(
        doc,
        "Demonstration monitoring report prepared from the stored proposal figures. It is not a credit, compliance or business decision.",
        italic=True,
        size=9,
        color="666666",
    )
    heading(doc, "1. Facility information")
    table(doc, ["Item", "Details"], [
        ["Customer", customer["legal_name"]],
        ["Industry", customer.get("industry") or ""],
        ["Relationship manager", person(customer)],
        ["Outstanding drawn", hkd(point["drawn_hkd"])],
        ["ECL", hkd(point["ecl_hkd"])],
        ["Current PD grade", str(point["rating"])],
        ["Stage", str(point["stage"])],
        ["Days past due", str(point["dpd"])],
        ["Next obligation", f"{hkd(point.get('next_due_hkd'))} on {point.get('next_due_date') or '—'}"],
        ["Guarantor", customer.get("guarantor") or "None on the extract"],
    ], [6.0, 11.5])
    para(doc, stance(point))
    heading(doc, "2. Security position")
    table(
        doc,
        ["Contract", "Security", "Address", "Latest valuation", "LTV"],
        collateral_rows(point),
    )
    para(
        doc,
        f"Charged or secured amount on the extract is {hkd(point.get('collateral_hkd'))}. "
        f"Coverage is {point.get('coverage_ratio') if point.get('coverage_ratio') is not None else '—'} "
        f"and LTV is {point.get('ltv') if point.get('ltv') is not None else '—'}.",
    )
    heading(doc, "3. Account conduct")
    table(doc, ["Item", "Status"], [
        ["Stage", str(point["stage"])],
        ["Days past due", str(point["dpd"])],
        ["ECL", hkd(point["ecl_hkd"])],
        ["Facilities", str(len(point["facilities"]))],
    ])
    notes = warning_lines(customer)
    if notes:
        para(doc, "Extract warnings: " + " ".join(notes))
    else:
        para(doc, "No warning text is stored on this name beyond stage and days past due.")
    heading(doc, "4. Recommendation")
    para(
        doc,
        f"Input to this report is the annual-review proposal for {customer['legal_name']} at {as_of}. "
        + stance(point)
        + " Download either file from BEA - Risk Intelligence after the borrower is selected.",
    )
    return doc


def main() -> None:
    book = json.loads(BOOK.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    index = []
    for customer in book["customers"]:
        point = customer["history"][-1]
        folder = OUT / customer["customer_id"]
        folder.mkdir(parents=True, exist_ok=True)
        build_proposal(customer, point).save(folder / "proposal.docx")
        build_report(customer, point).save(folder / "report.docx")
        index.append({
            "id": customer["customer_id"],
            "name": customer["legal_name"],
            "aliases": customer.get("rdw_legal_names") or [],
            "industry": customer.get("industry") or "",
            "rm": person(customer),
            "asof": label_date(point["date"]),
            "drawn": hkd(point["drawn_hkd"]),
            "ecl": hkd(point["ecl_hkd"]),
            "stage": point["stage"],
            "dpd": point["dpd"],
            "rating": point["rating"],
        })
    (ROOT / "report_files" / "obligors.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    print(f"obligors={len(index)}")


if __name__ == "__main__":
    main()
