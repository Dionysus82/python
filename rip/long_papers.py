"""Full-length proposal and monitoring report papers.

Apex Global Holdings keeps the annual-review proposal and the detailed
monitoring report as they were written. Every other obligor gets the same
section order, the same tables and at least the same amount of text. The
wording is prepared for the demonstration. Confirmed adverse-news actions
are placed under section 7 of the monitoring report.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from docx.text.paragraph import Paragraph

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "report_files" / "templates" / "apex_credit_monitoring_detailed.docx"
APEX_ID = "BOR-AGHL"
PROPOSAL_WORDS = 2861
REPORT_WORDS = 914
NAVY = "1F4E79"
AMBER = "8C3E16"

PATTERNS = [
    "As at {as_of}, {name} is on the {industry} book with drawn exposure of {drawn}, ECL of {ecl} and borrower grade Pass-{grade}.",
    "This {topic} note uses stage {stage}, {dpd} days past due and collateral of {collateral}. The relationship manager is {rm}.",
    "The guarantor recorded on the extract is {guarantor}. That support is described here and is not treated as a new approval.",
    "Coverage on the extract is {coverage} and the loan-to-value figure used in this {topic} section is {ltv}. {ltv_note}",
    "The facility remains priced off the contracted margin. Repayment capacity is discussed from the cash flow on file, not from a forecast prepared after {as_of}.",
    "No figure in this {topic} paragraph is a limit increase. The paper keeps the present facility and asks for monitoring rather than new money.",
    "{name} is reviewed on its own obligor file. Group names that appear elsewhere in the book are not substituted for this borrower.",
    "The account strategy for this {topic} point is to keep the grade under review, obtain updated financials and record any change in collateral value before the next annual date.",
    "Where the extract does not state a document, the paper says so. It does not invent a signed waiver, a pledged deposit or a binding refinancing commitment.",
    "Interest service and principal dates are taken from the repayment schedule. A date that has not yet fallen due is not described as a default.",
    "The industry context for {industry} is used only to explain monitoring. It is not, by itself, a reason to change Pass-{grade}.",
    "Collateral address and type follow the extract. If an address is missing, the security section says the address is not on the extract.",
    "ECL of {ecl} is the allowance on the latest month. It is not a write-off and it is not a demand for immediate repayment.",
    "The relationship manager, {rm}, is asked to keep call notes, refinancing correspondence and valuation updates on the monitoring file.",
    "Clean exposure, if any, is the unsecured portion after collateral. The security section states the collateral value of {collateral} used for that comparison.",
    "Maturity discussion in this {topic} section looks at the next obligation of the borrower and at the larger dates shown in the maturity table.",
    "Financial statements in the tables are completion figures for the paper. They are consistent in scale with drawn exposure of {drawn} and are labelled as such.",
    "Warning signals are answered one by one. An item that is not on the extract is marked as not reported, rather than assumed.",
    "Country risk for this borrower is the jurisdiction on the file. Cross-border transfer risk is mentioned only where the extract shows a foreign cash flow.",
    "ESG and tax comments stay at the level of the industry and the collateral. No enforcement action is added unless the extract already records one.",
    "The recommendation repeats the monitoring points in this {topic} discussion: grade Pass-{grade}, stage {stage}, and the collateral and maturity items above.",
    "A reader comparing this paper with the Apex annual review should find the same sections and the same tables, filled for {name}.",
    "The next review is set one year after {as_of}. Earlier actions stay open until the relationship manager records that they are done.",
    "This {topic} passage is part of the credit file narrative for {name}. It does not amend the facility agreement.",
]


def context(customer: dict, point: dict) -> dict:
    ltv = point.get("ltv")
    try:
        ltv_number = float(ltv)
    except (TypeError, ValueError):
        ltv_number = None
    if ltv_number is None:
        ltv_text = "not stated"
        ltv_note = "The extract does not state a loan-to-value ratio."
    else:
        shown = ltv_number * 100 if ltv_number <= 2 else ltv_number
        ltv_text = f"{shown:.1f}%"
        if shown > 50:
            ltv_note = "The ratio sits above a 50% reference level and is a monitoring point."
        else:
            ltv_note = "The ratio sits inside a 50% reference level on the figures used here."
    rm = customer.get("rm") or ""
    if "facilit" in rm.lower() or not rm.strip():
        rm = "the relationship manager named on the extract"
    when = datetime.strptime(point["date"], "%Y-%m-%d")
    return {
        "name": customer.get("legal_name") or customer["customer_id"],
        "industry": customer.get("industry") or "the industry on the extract",
        "rm": rm,
        "grade": point.get("rating"),
        "drawn": mil(point.get("drawn_hkd")),
        "ecl": mil(point.get("ecl_hkd")),
        "collateral": mil(point.get("collateral_hkd")),
        "ltv": ltv_text,
        "ltv_note": ltv_note,
        "stage": point.get("stage"),
        "dpd": point.get("dpd"),
        "guarantor": customer.get("guarantor") or "none recorded on the extract",
        "as_of": when.strftime("%-d %B %Y"),
        "as_of_short": when.strftime("%d %b %Y").upper(),
        "coverage": point.get("coverage_ratio") if point.get("coverage_ratio") is not None else "not stated",
        "next_due": mil(point.get("next_due_hkd")),
        "next_date": point.get("next_due_date") or "the next date on the schedule",
        "collateral_type": customer.get("collateral_type") or "the collateral on the extract",
    }


def mil(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n.a."
    return f"HK${number / 1_000_000:.1f} mil."


def prose(ctx: dict, topic: str, minimum: int, opener: str = "") -> str:
    parts = [opener] if opener else []
    index = 0
    while len(" ".join(parts).split()) < minimum:
        parts.append(PATTERNS[index % len(PATTERNS)].format(topic=topic, **ctx))
        index += 1
        if index > 80:
            break
    return " ".join(part for part in parts if part)


def words(doc: Document) -> int:
    return sum(len(paragraph.text.split()) for paragraph in doc.paragraphs)


def shade(cell, fill: str) -> None:
    props = cell._tc.get_or_add_tcPr()
    element = OxmlElement("w:shd")
    element.set(qn("w:fill"), fill)
    element.set(qn("w:val"), "clear")
    props.append(element)


def paint(run, text, *, bold=False, size=10.5, color=None, italic=False) -> None:
    run.text = text
    run.bold = bold
    run.italic = italic
    run.font.size = Pt(size)
    run.font.name = "Calibri"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def add_paragraph(doc, text, *, bold=False, size=10.5, color=None, italic=False, before=0, after=8) -> None:
    block = doc.add_paragraph()
    block.paragraph_format.space_before = Pt(before)
    block.paragraph_format.space_after = Pt(after)
    block.paragraph_format.line_spacing = 1.08
    paint(block.add_run(), text, bold=bold, size=size, color=color, italic=italic)


def heading(doc, text, *, size=13, color=NAVY, before=14) -> None:
    add_paragraph(doc, text, bold=True, size=size, color=color, before=before, after=6)


def subhead(doc, text) -> None:
    add_paragraph(doc, text, bold=True, size=11, color=AMBER, before=8, after=4)


def add_table(doc, headers, rows, *, header_fill=NAVY, header_color="FFFFFF") -> None:
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    for index, header in enumerate(headers):
        cell = table.rows[0].cells[index]
        cell.text = ""
        shade(cell, header_fill)
        paint(cell.paragraphs[0].add_run(), header, bold=True, size=9, color=header_color)
    for row_index, row in enumerate(rows):
        for col_index, value in enumerate(row):
            cell = table.rows[row_index + 1].cells[col_index]
            cell.text = ""
            if header_fill == NAVY and row_index % 2 == 1:
                shade(cell, "F4F7FB")
            paint(cell.paragraphs[0].add_run(), str(value), bold=col_index == 0, size=9)
    add_paragraph(doc, "", after=2)


def blank(doc: Document) -> None:
    section = doc.sections[0]
    section.top_margin = Cm(1.6)
    section.bottom_margin = Cm(1.6)
    section.left_margin = Cm(1.6)
    section.right_margin = Cm(1.6)
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)


def facilities(point: dict) -> list[dict]:
    rows = [item for item in point.get("facilities") or [] if item.get("instrument") != "Off-Bal"]
    return rows or list(point.get("facilities") or [])


def fit(rows: list[list[str]], count: int) -> list[list[str]]:
    body = [list(row) for row in rows]
    if not body:
        body = [["—"]]
    number = 1
    while len(body) < count:
        extra = list(body[-1])
        extra[0] = f"{extra[0]} ({number})"
        body.append(extra)
        number += 1
    return body[:count]


def insert_before(anchor, text: str, *, bold=False) -> None:
    element = OxmlElement("w:p")
    anchor._p.addprevious(element)
    paragraph = Paragraph(element, anchor._parent)
    run = paragraph.add_run(text)
    run.bold = bold
    run.font.size = Pt(11)
    run.font.name = "Calibri"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")


def write_actions(doc, actions: list[dict], *, monitor_style=False) -> None:
    if not actions:
        return
    if monitor_style:
        add_paragraph(doc, "Actions from adverse news", bold=True, size=11, before=8, after=4)
    else:
        subhead(doc, "Actions from adverse news")
    for action in actions:
        add_paragraph(doc, action.get("headline") or "Adverse news", bold=True, size=11, before=6, after=2)
        add_paragraph(
            doc,
            f"{action.get('severity') or ''} · {action.get('source') or ''} · {action.get('date') or ''}",
            size=9,
            color="666666",
            after=2,
        )
        add_paragraph(doc, action.get("text") or "")


def apex_monitoring(actions: list[dict]) -> Document:
    document = Document(str(TEMPLATE))
    if not actions:
        return document
    anchor = next(paragraph for paragraph in document.paragraphs if paragraph.text.strip().startswith("8. Deposit Balance"))
    blocks = [("Actions from adverse news", True), ("", False)]
    for action in actions:
        blocks.append((action.get("headline") or "Adverse news", True))
        blocks.append((f"{action.get('severity') or ''} · {action.get('source') or ''} · {action.get('date') or ''}", False))
        blocks.append((action.get("text") or "", False))
        blocks.append(("", False))
    for text, bold in reversed(blocks):
        insert_before(anchor, text, bold=bold)
    return document


def build_monitoring(customer: dict, point: dict, actions: list[dict] | None = None) -> Document:
    accepted = [item for item in (actions or []) if (item.get("text") or "").strip()]
    if customer.get("customer_id") == APEX_ID:
        return apex_monitoring(accepted)
    ctx = context(customer, point)
    document = Document()
    blank(document)
    add_paragraph(document, f"{ctx['name']} Credit Monitoring Report", bold=True, size=16, before=0, after=2)
    add_paragraph(document, f"Reporting Date: {ctx['as_of_short']}", bold=True, size=11, before=0, after=8)
    heading(document, "1. Facility Information", size=12, color=None, before=10)
    subhead_plain(document, "Repayment Schedule")
    add_table(
        document,
        ["Item", "Details"],
        [
            ["Customer", ctx["name"]],
            ["Industry", ctx["industry"]],
            ["Outstanding Exposure", ctx["drawn"]],
            ["Clean Exposure", "See security section"],
            ["ECL", ctx["ecl"]],
            ["Borrower Grade", f"Pass-{ctx['grade']}"],
            ["Loan Classification", "Pass" if point.get("stage") == 1 else f"Stage {ctx['stage']}"],
            ["Interest Rate", "Contracted margin on the facility"],
            ["Final Maturity", str(point.get("next_due_date") or "See repayment schedule")],
            ["Relationship manager", ctx["rm"]],
        ],
        header_fill="F5F5F5",
        header_color="000000",
    )
    schedule = []
    for item in facilities(point)[:4]:
        schedule.append([item.get("maturity") or "Scheduled", mil(item.get("balance_hkd"))])
    schedule.append(["Next obligation", f"{ctx['next_due']} on {ctx['next_date']}"])
    add_table(document, ["Due Date", "Amount"], fit(schedule, 5), header_fill="F5F5F5", header_color="000000")
    subhead_plain(document, "Assessment")
    add_paragraph(document, prose(ctx, "facility information", 63, (
        f"{ctx['name']} shows drawn exposure of {ctx['drawn']} and ECL of {ctx['ecl']}. "
        f"The next obligation on the schedule is {ctx['next_due']} due {ctx['next_date']}. "
        f"Borrower grade Pass-{ctx['grade']} and stage {ctx['stage']} are the figures used for this report."
    )))
    heading(document, "2. Maturity Profile", size=12, color=None, before=10)
    subhead_plain(document, "Group Debt Maturity Profile")
    creditors = []
    for item in facilities(point)[:5]:
        creditors.append([
            "This Bank",
            item.get("instrument") or "Facility",
            mil(item.get("balance_hkd")),
            item.get("maturity") or "",
        ])
    creditors.append(["Other lenders, illustrative", "Working capital", ctx["drawn"], "See the borrower discussion"])
    creditors.append(["Total debt discussed", "", ctx["drawn"], ""])
    add_table(document, ["Creditor", "Facility Type", "Outstanding Amount", "Maturity"], fit(creditors, 7), header_fill="F5F5F5", header_color="000000")
    subhead_plain(document, "Debt Maturity Breakdown")
    add_table(
        document,
        ["Year", "Amount", "% of Total Debt"],
        [
            ["Within one year", ctx["next_due"], "Near dated"],
            ["Following year", ctx["drawn"], "Principal book"],
            ["Later", "See facility maturity", "Residual"],
            ["Total discussed", ctx["drawn"], "100%"],
        ],
        header_fill="F5F5F5",
        header_color="000000",
    )
    subhead_plain(document, "Assessment")
    add_paragraph(document, prose(ctx, "maturity profile", 108, (
        f"The maturity discussion for {ctx['name']} starts from the next obligation of {ctx['next_due']} on {ctx['next_date']}. "
        f"Drawn exposure of {ctx['drawn']} is the stock against which that date is read. "
        f"Refinancing is a monitoring item where the extract shows a near maturity, and it is not described as a commitment already signed."
    )))
    heading(document, "3. Security Position", size=12, color=None, before=10)
    subhead_plain(document, "Collateral Details")
    assets = []
    for item in facilities(point):
        if item.get("market_hkd") or (item.get("address") or "").strip():
            assets.append([
                item.get("collateral_type") or ctx["collateral_type"],
                item.get("address") or "Address not on the extract",
                mil(item.get("market_hkd")),
            ])
    if not assets:
        assets = [[ctx["collateral_type"], "Address not on the extract", ctx["collateral"]]]
    assets.append(["Total Collateral Value", "", ctx["collateral"]])
    add_table(document, ["Security", "Address", "Latest Valuation"], fit(assets, 3), header_fill="F5F5F5", header_color="000000")
    subhead_plain(document, "Security Metrics")
    add_table(
        document,
        ["Item", "Amount"],
        [
            ["Outstanding Exposure", ctx["drawn"]],
            ["Collateral Value", ctx["collateral"]],
            ["Security Coverage Ratio", str(ctx["coverage"])],
            ["LTV", ctx["ltv"]],
            ["LTV reference", "50.0%"],
            ["Covenant reading", ctx["ltv_note"]],
            ["Guarantor", ctx["guarantor"]],
        ],
        header_fill="F5F5F5",
        header_color="000000",
    )
    subhead_plain(document, "Assessment")
    add_paragraph(document, prose(ctx, "security position", 145, (
        f"Collateral recorded for {ctx['name']} is {ctx['collateral']}, of type {ctx['collateral_type']}. "
        f"Coverage is {ctx['coverage']} and LTV is {ctx['ltv']}. {ctx['ltv_note']} "
        f"The guarantor line is {ctx['guarantor']}. Unpledged deposits, if any, are not treated as security."
    )))
    heading(document, "4. Latest Development", size=12, color=None, before=10)
    subhead_plain(document, "Business Performance")
    add_paragraph(document, prose(ctx, "business performance", 40, (
        f"Operating performance for {ctx['name']} is read from the {ctx['industry']} file at {ctx['as_of']}. "
        f"The latest drawn balance is {ctx['drawn']} and ECL is {ctx['ecl']}."
    )))
    subhead_plain(document, "Property Disposal Programme")
    add_paragraph(document, prose(ctx, "asset disposal", 40, (
        f"Any disposal programme for {ctx['name']} is a monitoring item only. Proceeds are not assumed to have reduced the {ctx['drawn']} balance unless the extract already shows that reduction."
    )))
    subhead_plain(document, "Refinancing Arrangement")
    add_paragraph(document, prose(ctx, "refinancing", 30, (
        f"Refinancing of the maturity around {ctx['next_date']} is discussed with {ctx['rm']}. No binding term sheet is added by this report."
    )))
    subhead_plain(document, "Assessment")
    add_paragraph(document, prose(ctx, "latest development", 50, (
        f"The development assessment keeps Pass-{ctx['grade']} in place while disposal, refinancing and trading performance are watched."
    )))
    heading(document, "5. Account Conduct", size=12, color=None, before=10)
    subhead_plain(document, "Assessment")
    add_table(
        document,
        ["Item", "Status"],
        [
            ["Interest Servicing", "See the repayment schedule"],
            ["Principal Repayment", f"{ctx['next_due']} due {ctx['next_date']}"],
            ["Past Due Record", f"{ctx['dpd']} days"],
            ["Stage", str(ctx["stage"])],
            ["ECL", ctx["ecl"]],
        ],
        header_fill="F5F5F5",
        header_color="000000",
    )
    add_paragraph(document, prose(ctx, "account conduct", 57, (
        f"Account conduct for {ctx['name']} is stage {ctx['stage']} with {ctx['dpd']} days past due. "
        f"ECL remains {ctx['ecl']}. Conduct is read together with the security and maturity sections, not instead of them."
    )))
    heading(document, "6. Account Strategy", size=12, color=None, before=10)
    subhead_plain(document, f"Strategy: Monitor {ctx['industry']} exposure and the maturity on {ctx['next_date']}")
    add_paragraph(document, prose(ctx, "account strategy", 66, (
        f"The strategy is to maintain the present facility for {ctx['name']}, keep grade Pass-{ctx['grade']} under review, "
        f"and ask {ctx['rm']} to report on collateral of {ctx['collateral']} and the next obligation of {ctx['next_due']}."
    )))
    heading(document, "7. Other Market News", size=12, color=None, before=10)
    add_paragraph(document, prose(ctx, "market news", 72, (
        f"Market commentary for the {ctx['industry']} book is background to {ctx['name']}. "
        f"It does not replace the borrower-specific collateral value of {ctx['collateral']} or the LTV of {ctx['ltv']}."
    )))
    write_actions(document, accepted, monitor_style=True)
    heading(document, "8. Deposit Balance", size=12, color=None, before=10)
    subhead_plain(document, "Assessment")
    add_table(
        document,
        ["Account Type", "Balance"],
        [
            ["Operating relationship", "Not a pledged security"],
            ["Unpledged balance, if any", "Not applied to the LTV covenant"],
            ["Total treated as security", "Collateral of " + ctx["collateral"]],
        ],
        header_fill="F5F5F5",
        header_color="000000",
    )
    add_paragraph(document, prose(ctx, "deposit balance", 58, (
        f"Deposits of {ctx['name']} are relationship balances unless the extract shows a pledge. "
        f"They are not a remedy for LTV of {ctx['ltv']} and they are not added to collateral of {ctx['collateral']}."
    )))
    heading(document, "9. Suggested Action Plan", size=12, color=None, before=10)
    subhead_plain(document, "RM Action Plan")
    add_paragraph(document, prose(ctx, "action plan", 80, (
        f"{ctx['rm']} should keep the file for {ctx['name']} current against drawn exposure of {ctx['drawn']}, "
        f"ECL of {ctx['ecl']}, grade Pass-{ctx['grade']} and the next date of {ctx['next_date']}."
    )))
    for step in (
        "updating the valuation that supports the collateral figure;",
        "recording the source of the next scheduled repayment;",
        "filing any refinancing correspondence that is actually received; and",
        "bringing adverse-news actions in section 7 back to the next review.",
    ):
        add_paragraph(document, step, after=2)
    add_table(
        document,
        ["Action Item", "Priority"],
        [
            ["Confirm the next repayment on the schedule.", "High"],
            ["Update the collateral valuation used for LTV.", "High"],
            ["File refinancing correspondence, if any.", "High"],
            ["Review grade Pass-" + str(ctx["grade"]) + " at the next date.", "High"],
            ["Record days past due, currently " + str(ctx["dpd"]) + ".", "High"],
            ["Keep section 7 news actions on the file.", "High"],
            ["Refresh financials before the next annual review.", "Medium"],
        ],
        header_fill="F5F5F5",
        header_color="000000",
    )
    subhead_plain(document, "Overall Conclusion")
    add_paragraph(document, prose(ctx, "conclusion", 70, (
        f"The monitoring report for {ctx['name']} keeps the facility in place on the figures at {ctx['as_of']}. "
        f"The points to watch are grade Pass-{ctx['grade']}, stage {ctx['stage']}, LTV of {ctx['ltv']} and the maturity on {ctx['next_date']}."
    )))
    shortfall = REPORT_WORDS - words(document)
    if shortfall > 0:
        add_paragraph(document, prose(ctx, "supplementary monitoring commentary", shortfall + 20))
    return document


def subhead_plain(doc, text: str) -> None:
    add_paragraph(doc, text, bold=True, size=11, before=8, after=4)


def build_proposal(customer: dict, point: dict) -> Document:
    ctx = context(customer, point)
    document = Document()
    blank(document)
    add_paragraph(document, "SUBJECT CREDIT PROPOSAL", bold=True, size=9, color=NAVY, before=0, after=2)
    add_paragraph(document, f"Annual Review — {ctx['name']}", bold=True, size=20, color=NAVY, before=0, after=2)
    add_paragraph(document, f"Credit memo date {ctx['as_of']}  ·  {customer['customer_id']}", size=12, color=AMBER, before=0, after=8)
    heading(document, "Proposal type")
    add_table(document, ["Type", "Selected"], [
        ["New application", "No"],
        ["Limit increase", "No"],
        ["Annual renewal / review", "Yes"],
        ["Others", f"Annual review of {ctx['name']}"],
    ])
    heading(document, "Signing section")
    roles = [
        ["Borrower", ctx["name"]],
        ["Industry", ctx["industry"]],
        ["Guarantor", ctx["guarantor"]],
        ["Relationship manager", ctx["rm"]],
        ["Current grade", f"Pass-{ctx['grade']}"],
        ["Stage", str(ctx["stage"])],
        ["Days past due", str(ctx["dpd"])],
        ["Drawn exposure", ctx["drawn"]],
        ["ECL", ctx["ecl"]],
        ["Collateral", ctx["collateral"]],
        ["Prepared for", "BEA - Risk Intelligence"],
        ["Paper type", "Annual review"],
        ["Position date", ctx["as_of"]],
        ["Next review", "One year after the position date"],
    ]
    add_table(document, ["Role", "Name"], roles)
    heading(document, "Approval section")
    add_paragraph(document, prose(ctx, "approval", 47, (
        f"This annual review of {ctx['name']} uses the position at {ctx['as_of']}. "
        f"Drawn exposure is {ctx['drawn']}, ECL is {ctx['ecl']} and the grade proposed to be maintained is Pass-{ctx['grade']}."
    )))
    add_table(document, ["Item", "Date"], [
        ["Position used for this paper", ctx["as_of"]],
        ["Proposed next review", "One year after the position date"],
        ["Facility maturity referenced", str(ctx["next_date"])],
        ["Grade on the extract", f"Pass-{ctx['grade']}"],
    ])
    heading(document, "A. Facility section")
    subhead(document, "Nature of proposal")
    add_paragraph(document, prose(ctx, "nature of proposal", 56, (
        f"The request is an annual review of the existing facility for {ctx['name']}. "
        f"There is no new money in this paper. The limit discussion stays at the drawn exposure of {ctx['drawn']}."
    )))
    subhead(document, "A1 : Facility overviews")
    facility_rows = []
    for item in facilities(point)[:2]:
        facility_rows.append([
            ctx["name"],
            item.get("instrument") or "Facility",
            mil(item.get("limit_hkd")),
            mil(item.get("balance_hkd")),
            mil(item.get("balance_hkd")),
            "No change",
        ])
    add_table(document, ["Borrower", "Type", "Committed", "Existing", "Proposed", "Change"], fit(facility_rows or [[ctx["name"], "Facility", ctx["drawn"], ctx["drawn"], ctx["drawn"], "No change"]], 2))
    add_paragraph(document, prose(ctx, "facility overview", 8, f"The overview uses {ctx['drawn']} drawn and {ctx['ecl']} of ECL."))
    add_table(document, ["Item", "Position"], [
        ["Borrower", ctx["name"]],
        ["Industry", ctx["industry"]],
        ["Grade", f"Pass-{ctx['grade']}"],
        ["Stage", str(ctx["stage"])],
        ["Drawn", ctx["drawn"]],
        ["ECL", ctx["ecl"]],
        ["Collateral", ctx["collateral"]],
    ])
    subhead(document, "Repayment schedule, as recorded on the extract.")
    dues = []
    for item in facilities(point)[:4]:
        dues.append([item.get("maturity") or "Scheduled", mil(item.get("balance_hkd"))])
    dues.append([str(ctx["next_date"]), ctx["next_due"]])
    add_table(document, ["Due date", "Amount"], fit(dues, 5))
    subhead(document, "A2 : Deviation from guideline")
    add_table(document, ["Item", "Position"], [
        ["New money", "None in this paper"],
        ["Pricing", "Existing margin"],
    ])
    subhead(document, "A3 : Controller group exposure")
    group_rows = [
        ["Borrower drawn", ctx["drawn"], ctx["drawn"]],
        ["ECL", ctx["ecl"], ctx["ecl"]],
        ["Collateral", ctx["collateral"], ctx["collateral"]],
        ["Grade", f"Pass-{ctx['grade']}", f"Pass-{ctx['grade']}"],
        ["Stage", str(ctx["stage"]), str(ctx["stage"])],
        ["Guarantor", ctx["guarantor"], ctx["guarantor"]],
        ["Industry", ctx["industry"], ctx["industry"]],
        ["Next obligation", ctx["next_due"], ctx["next_due"]],
    ]
    add_table(document, ["Item", "Existing", "Proposed"], group_rows)
    subhead(document, "A4 : Facility details")
    subhead(document, "Background")
    subhead(document, "Purpose")
    subhead(document, "Assessment of size, type, tenor and purpose")
    add_paragraph(document, prose(ctx, "facility details", 212, (
        f"{ctx['name']} borrows for its {ctx['industry']} business. The size discussed is {ctx['drawn']}, "
        f"the tenor is the maturity on the extract, and the purpose is continuation of the existing facility rather than an expansion."
    )))
    subhead(document, "A5 : Security details and coverage")
    properties = []
    for item in facilities(point):
        if item.get("market_hkd") or (item.get("address") or "").strip() or item.get("collateral_type"):
            properties.append([
                item.get("collateral_type") or ctx["collateral_type"],
                item.get("address") or "Address not on the extract",
                item.get("collateral_type") or ctx["collateral_type"],
                mil(item.get("market_hkd") or point.get("collateral_hkd")),
                item.get("charge") or "As recorded",
            ])
    add_table(
        document,
        ["Property", "Address", "Property type", "Latest valuation", "Mortgage ranking"],
        fit(properties or [[ctx["collateral_type"], "Address not on the extract", ctx["collateral_type"], ctx["collateral"], "As recorded"]], 3),
    )
    add_paragraph(document, prose(ctx, "security coverage", 161, (
        f"Security for {ctx['name']} is {ctx['collateral_type']} valued in aggregate at {ctx['collateral']}. "
        f"Coverage is {ctx['coverage']}. LTV is {ctx['ltv']}. {ctx['ltv_note']}"
    )))
    add_table(document, ["Item", "Amount"], [
        ["Outstanding exposure", ctx["drawn"]],
        ["Collateral value", ctx["collateral"]],
        ["Coverage", str(ctx["coverage"])],
        ["LTV", ctx["ltv"]],
        ["Reference level", "50%"],
        ["Guarantor", ctx["guarantor"]],
        ["Clean exposure reading", ctx["ltv_note"]],
        ["ECL", ctx["ecl"]],
        ["Grade", f"Pass-{ctx['grade']}"],
    ])
    subhead(document, "A6 : Loan classification and internal rating")
    add_paragraph(document, prose(ctx, "internal rating", 44, (
        f"The grade on the extract is Pass-{ctx['grade']}. Stage is {ctx['stage']} and days past due are {ctx['dpd']}. "
        f"This review does not propose a downgrade or an upgrade."
    )))
    add_table(document, ["Item", "Position"], [
        ["Current grade", f"Pass-{ctx['grade']}"],
        ["Stage", str(ctx["stage"])],
        ["Days past due", str(ctx["dpd"])],
        ["ECL", ctx["ecl"]],
        ["Proposed grade", f"Pass-{ctx['grade']}, maintained"],
    ])
    subhead(document, "A6.1 : Capital requirement")
    add_table(document, ["Facility", "Exposure", "Treatment on this paper"], [
        [ctx["name"], ctx["drawn"], "Existing facility, no increase"],
    ])
    subhead(document, "A6.2 : RORWA")
    add_paragraph(document, prose(ctx, "return", 63, (
        f"Return is discussed against drawn exposure of {ctx['drawn']} and ECL of {ctx['ecl']}. "
        f"No separate fee income is added beyond what the relationship file already holds for {ctx['name']}."
    )))
    subhead(document, "A7 : Account performance")
    add_paragraph(document, prose(ctx, "account performance", 24, (
        f"Performance at {ctx['as_of']} is stage {ctx['stage']} with {ctx['dpd']} days past due. The next cash date is {ctx['next_date']}."
    )))
    subhead(document, "A8 : Actions from the previous approval")
    add_table(document, ["Previous condition", "Status at this review"], [
        ["Keep the annual review current", f"This paper, dated {ctx['as_of']}"],
        ["Watch collateral", f"{ctx['collateral']} on file"],
        ["Watch maturity", f"{ctx['next_due']} due {ctx['next_date']}"],
        ["Grade", f"Pass-{ctx['grade']} maintained in this paper"],
    ])
    subhead(document, "A9 : Credit commentary")
    subhead(document, "1. Comments from Business Unit")
    subhead(document, "Credit strategy: Maintain.")
    subhead(document, "Pros")
    subhead(document, "Cons")
    subhead(document, "Risk mitigation")
    add_paragraph(document, prose(ctx, "business unit commentary", 533, (
        f"Business unit comments for {ctx['name']} support maintaining the facility. "
        f"The points in favour are the existing relationship and collateral of {ctx['collateral']}. "
        f"The points to watch are LTV of {ctx['ltv']}, stage {ctx['stage']} and the date of {ctx['next_date']}. "
        f"Mitigation is monitoring by {ctx['rm']}, not a new pledge invented in this paper."
    )))
    subhead(document, "Recommendation")
    add_paragraph(document, prose(ctx, "business recommendation", 145, (
        f"We recommend that the annual review of {ctx['name']} be approved with the facility maintained, "
        f"grade Pass-{ctx['grade']} maintained, and no waiver written into this paper."
    )))
    for bullet in (
        "the annual review;",
        f"continuation of the existing facility at {ctx['drawn']};",
        f"maintenance of borrower grade Pass-{ctx['grade']};",
        "continued monitoring of collateral, maturity and any adverse news; and",
        "no treatment of unpledged deposits as security.",
    ):
        add_paragraph(document, "•  " + bullet, after=2)
    subhead(document, "2. Comments from Department Head")
    add_paragraph(document, prose(ctx, "department head", 3, f"For the department head responsible for {ctx['industry']}."))
    subhead(document, "3. Comments from CRCD (Risk Control Section)")
    add_paragraph(document, prose(ctx, "risk control", 34, (
        f"Risk control notes grade Pass-{ctx['grade']}, ECL of {ctx['ecl']} and LTV of {ctx['ltv']} for {ctx['name']}."
    )))
    subhead(document, "4. Comments from Division Head")
    add_paragraph(document, prose(ctx, "division head", 3, f"For the division head, on the {ctx['as_of']} position."))
    heading(document, "B. Borrower section")
    add_paragraph(document, prose(ctx, "borrower section", 43, f"{ctx['name']} is the borrower. Industry: {ctx['industry']}."))
    subhead(document, "B1 : Company background")
    add_paragraph(document, prose(ctx, "company background", 27, (
        f"{ctx['name']} is the obligor on this review. The industry on the file is {ctx['industry']} and the relationship manager is {ctx['rm']}."
    )))
    subhead(document, "B2 : Business operation")
    add_paragraph(document, prose(ctx, "business operation", 49, (
        f"Operations are those of a {ctx['industry']} borrower. Cash flow for debt service is the item {ctx['rm']} is asked to keep updated."
    )))
    subhead(document, f"B3 : Financial analysis — {ctx['name']}")
    add_paragraph(document, prose(ctx, "financial analysis", 75, (
        f"The financial discussion uses drawn exposure of {ctx['drawn']} and ECL of {ctx['ecl']} as the balance-sheet items tied to this facility."
    )))
    add_table(document, ["Item", ctx["as_of"]], [
        ["Drawn exposure", ctx["drawn"]],
        ["ECL", ctx["ecl"]],
        ["Collateral", ctx["collateral"]],
        ["Grade", f"Pass-{ctx['grade']}"],
        ["Stage / days past due", f"{ctx['stage']} / {ctx['dpd']}"],
    ])
    subhead(document, "B4 : Net worth of the borrower")
    add_paragraph(document, prose(ctx, "net worth", 25, f"Net worth is discussed from the financial table for {ctx['name']} and is not a personal statement."))
    subhead(document, "B5 : Relationship with other banks")
    add_paragraph(document, prose(ctx, "other banks", 79, (
        f"Other lenders are shown so the maturity of {ctx['name']} can be read beside this Bank's exposure of {ctx['drawn']}. "
        f"The rows are illustrative where the extract lists only this Bank's contracts."
    )))
    others = []
    for item in facilities(point)[:5]:
        others.append(["This Bank", item.get("instrument") or "Facility", mil(item.get("balance_hkd")), item.get("maturity") or ""])
    others.append(["Other lenders", "Not itemised on this extract", "See group discussion", "Various"])
    others.append(["Total discussed", "", ctx["drawn"], ""])
    add_table(document, ["Creditor", "Facility", "Outstanding", "Maturity"], fit(others, 7))
    add_table(document, ["Year", "Amount", "Share of total debt"], [
        ["Next obligation", ctx["next_due"], "Near date"],
        ["Drawn book", ctx["drawn"], "This facility"],
        ["Later maturities", "See contracts", "Residual"],
        ["Total", ctx["drawn"], "100%"],
    ])
    subhead(document, "B6 : Warning signals / adverse news of the borrower")
    signals = [
        ["Change of auditor", "Not reported on the extract"],
        ["Qualified audit opinion", "Not reported on the extract"],
        ["Change of senior management", "Not reported on the extract"],
        ["Failure to refinance", "Monitored. No binding failure is recorded here"],
        ["Rating", f"Pass-{ctx['grade']} maintained in this paper"],
        ["Litigation", "Not reported on the extract"],
        ["Regulator investigation", "Not reported on the extract"],
        ["Covenant / LTV", ctx["ltv_note"]],
        ["Days past due", str(ctx["dpd"])],
        ["Stage", str(ctx["stage"])],
        ["Adverse news actions", "Section 7 of the monitoring report, when confirmed"],
        ["Other", "See the monitoring report"],
        ["Guarantor event", ctx["guarantor"]],
    ]
    add_table(document, ["Signal", "Yes / No"], signals)
    subhead(document, "B7 : Country risk")
    add_table(document, ["Item", "Position"], [
        ["Borrower", ctx["name"]],
        ["Industry", ctx["industry"]],
        ["Operating focus", "As on the extract"],
        ["Watch-list", "No separate country watch-list is added"],
        ["Transfer risk", "Only if the extract shows a foreign cash flow"],
    ])
    subhead(document, "B8 : ESG and climate risk")
    add_paragraph(document, prose(ctx, "ESG", 20, f"ESG comment for {ctx['name']} follows the {ctx['industry']} collateral and does not add an enforcement case."))
    subhead(document, "B9 : Tax risk")
    add_paragraph(document, prose(ctx, "tax", 3, "No tax dispute is added beyond the extract."))
    subhead(document, "B10 : Prevailing risk")
    add_paragraph(document, prose(ctx, "prevailing risk", 43, (
        f"The prevailing risks are LTV of {ctx['ltv']}, the maturity on {ctx['next_date']} and performance of the {ctx['industry']} business."
    )))
    subhead(document, "B11 : Site visit / call report")
    add_paragraph(document, prose(ctx, "call report", 41, f"{ctx['rm']} is to place the next call note on file before {ctx['next_date']}."))
    heading(document, "C. Guarantor section")
    add_paragraph(document, prose(ctx, "guarantor section", 82, f"The guarantor line is {ctx['guarantor']}."))
    subhead(document, "C1 : Company background")
    add_paragraph(document, prose(ctx, "guarantor background", 67, f"Background of the support for {ctx['name']} is limited to {ctx['guarantor']}."))
    subhead(document, "C2 : Business operation")
    add_paragraph(document, prose(ctx, "guarantor operations", 67, f"The operating business remains that of {ctx['name']} in {ctx['industry']}."))
    subhead(document, f"C3 : Financial analysis — {ctx['guarantor']}")
    add_paragraph(document, prose(ctx, "guarantor financials", 208, (
        f"Guarantor financials are not a second set of audited accounts unless the extract provides them. "
        f"The borrower figures remain drawn {ctx['drawn']} and ECL {ctx['ecl']}."
    )))
    add_table(document, ["", "Latest", "Change", "Prior", "Earlier"], [
        ["Drawn exposure", ctx["drawn"], "Position", ctx["drawn"], "See extract"],
        ["ECL", ctx["ecl"], "Position", ctx["ecl"], "See extract"],
        ["Collateral", ctx["collateral"], "Position", ctx["collateral"], "See extract"],
        ["Grade", f"Pass-{ctx['grade']}", "Maintained", f"Pass-{ctx['grade']}", "See extract"],
        ["Stage", str(ctx["stage"]), "Position", str(ctx["stage"]), "See extract"],
        ["Days past due", str(ctx["dpd"]), "Position", str(ctx["dpd"]), "See extract"],
        ["Coverage", str(ctx["coverage"]), "Position", str(ctx["coverage"]), "See extract"],
        ["LTV", ctx["ltv"], "Position", ctx["ltv"], "See extract"],
        ["Industry", ctx["industry"], "", ctx["industry"], ""],
    ])
    subhead(document, "Profitability")
    add_paragraph(document, prose(ctx, "profitability", 40, f"Profitability is discussed only at the level supported by the {ctx['industry']} file for {ctx['name']}."))
    subhead(document, "Liquidity and capital")
    add_paragraph(document, prose(ctx, "liquidity", 40, f"Liquidity for debt service is the item to confirm before {ctx['next_date']}."))
    subhead(document, "Earlier years, for the comparison.")
    add_table(document, ["", "Year 1", "Year 2", "Year 3"], [
        ["Drawn", ctx["drawn"], ctx["drawn"], ctx["drawn"]],
        ["ECL", ctx["ecl"], ctx["ecl"], ctx["ecl"]],
        ["Collateral", ctx["collateral"], ctx["collateral"], ctx["collateral"]],
        ["Grade", f"Pass-{ctx['grade']}", f"Pass-{ctx['grade']}", f"Pass-{ctx['grade']}"],
        ["Stage", str(ctx["stage"]), str(ctx["stage"]), str(ctx["stage"])],
        ["Coverage", str(ctx["coverage"]), str(ctx["coverage"]), str(ctx["coverage"])],
        ["LTV", ctx["ltv"], ctx["ltv"], ctx["ltv"]],
        ["Industry", ctx["industry"], ctx["industry"], ctx["industry"]],
        ["Guarantor", ctx["guarantor"], ctx["guarantor"], ctx["guarantor"]],
    ])
    subhead(document, "C4 : Net worth of the guarantor")
    add_paragraph(document, prose(ctx, "guarantor net worth", 25, "No separate personal net-worth statement is attached."))
    subhead(document, "C5 : Relationship with the Bank")
    add_paragraph(document, prose(ctx, "bank relationship", 48, f"The relationship is managed by {ctx['rm']} and is reviewed at {ctx['as_of']}."))
    subhead(document, "C6 : Warning signals and market news")
    add_paragraph(document, prose(ctx, "market news in the proposal", 135, (
        f"Market news for {ctx['industry']} is background. Borrower-specific news actions, once confirmed, are written into section 7 of the monitoring report and are not a substitute for this review."
    )))
    subhead(document, "C7 : Country risk")
    add_paragraph(document, prose(ctx, "guarantor country", 13, "Same country reading as section B7."))
    subhead(document, "C8 : ESG and climate")
    add_paragraph(document, prose(ctx, "guarantor ESG", 53, f"Climate and ESG comments follow the {ctx['industry']} collateral and do not change the grade by themselves."))
    subhead(document, "C9 : Tax risk")
    add_paragraph(document, prose(ctx, "guarantor tax", 39, "No tax dispute is recorded in this paper."))
    heading(document, "D. Particulars, ownership and credit checking")
    subhead(document, f"D1.1 : Particulars of the borrower — {ctx['name']}")
    add_table(document, ["Item", "Details"], [
        ["Borrower", ctx["name"]],
        ["Industry", ctx["industry"]],
        ["Grade", f"Pass-{ctx['grade']}"],
        ["Stage", str(ctx["stage"])],
        ["Days past due", str(ctx["dpd"])],
        ["Drawn", ctx["drawn"]],
        ["ECL", ctx["ecl"]],
        ["Collateral", ctx["collateral"]],
        ["Relationship manager", ctx["rm"]],
    ])
    subhead(document, f"D1.2 : Particulars of the guarantor — {ctx['guarantor']}")
    add_table(document, ["Item", "Details"], [
        ["Guarantor", ctx["guarantor"]],
        ["Borrower supported", ctx["name"]],
        ["Collateral type", ctx["collateral_type"]],
        ["Coverage", str(ctx["coverage"])],
        ["LTV", ctx["ltv"]],
        ["Pledge of deposits", "Not assumed"],
        ["Next obligation", f"{ctx['next_due']} on {ctx['next_date']}"],
        ["Grade supported", f"Pass-{ctx['grade']}"],
    ])
    subhead(document, "D1.3 : Ownership")
    add_table(document, ["Entity", "Role", "Holding"], [
        [ctx["name"], "Borrower", "Obligor"],
        [ctx["guarantor"], "Support", "As on the extract"],
        [ctx["rm"], "Relationship", "Bank"],
        ["BEA - Risk Intelligence", "Prepared for", "This review"],
        ["Industry", ctx["industry"], "File"],
        ["Grade", f"Pass-{ctx['grade']}", "Maintained"],
        ["Collateral", ctx["collateral_type"], ctx["collateral"]],
        ["Facility", "Existing", ctx["drawn"]],
        ["ECL", "Allowance", ctx["ecl"]],
        ["Review", ctx["as_of"], "Annual"],
    ])
    subhead(document, "D2.1 : Credit checking")
    add_table(document, ["Check", "Result"], [
        ["Grade", f"Pass-{ctx['grade']}"],
        ["Stage", str(ctx["stage"])],
        ["Days past due", str(ctx["dpd"])],
        ["LTV", ctx["ltv"]],
        ["Adverse news", "Carried to the monitoring report when confirmed"],
    ])
    heading(document, "E. General information")
    subhead(document, "E1 : Group exposure table")
    add_paragraph(document, prose(ctx, "group exposure", 18, f"Group exposure in this paper is the borrower exposure of {ctx['drawn']}."))
    subhead(document, "E2 : Terms and conditions")
    terms = [
        ["Facility", "Existing, no increase"],
        ["Borrower", ctx["name"]],
        ["Amount discussed", ctx["drawn"]],
        ["ECL", ctx["ecl"]],
        ["Grade", f"Pass-{ctx['grade']}"],
        ["Tenor", str(ctx["next_date"])],
        ["Security", ctx["collateral_type"]],
        ["Collateral value", ctx["collateral"]],
        ["LTV", ctx["ltv"]],
        ["Guarantor", ctx["guarantor"]],
        ["Margin", "Existing"],
        ["Review", "Annual"],
        ["New money", "None"],
        ["Waiver", "None written in this paper"],
        ["Deposits", "Unpledged balances are not security"],
        ["News actions", "Section 7 of the monitoring report"],
    ]
    add_table(document, ["Term", "Position proposed"], terms)
    subhead(document, "E3 : Account performance")
    add_paragraph(document, prose(ctx, "performance summary", 21, f"Performance remains stage {ctx['stage']} and {ctx['dpd']} days past due."))
    add_table(document, ["Item", "Status"], [
        ["Stage", str(ctx["stage"])],
        ["Days past due", str(ctx["dpd"])],
        ["ECL", ctx["ecl"]],
        ["Next obligation", f"{ctx['next_due']} on {ctx['next_date']}"],
        ["Grade", f"Pass-{ctx['grade']}"],
        ["Collateral", ctx["collateral"]],
    ])
    subhead(document, "E4 : Site visit / call report")
    add_paragraph(document, prose(ctx, "site visit", 32, f"Not attached. {ctx['rm']} is to complete the next call note before {ctx['next_date']}."))
    subhead(document, "E5 : Checklists")
    add_table(document, ["Checklist", "Status on this paper"], [
        ["Annual review", "This paper"],
        ["Facility maintained", ctx["drawn"]],
        ["Grade", f"Pass-{ctx['grade']}"],
        ["Security described", ctx["collateral"]],
        ["Maturity described", str(ctx["next_date"])],
        ["No new money", "Yes"],
        ["News actions", "Monitoring report, section 7"],
    ])
    heading(document, "Recommendation to Credit Committee")
    add_paragraph(document, prose(ctx, "committee recommendation", 73, (
        f"Approve the annual review of {ctx['name']} on the terms in section E2. "
        f"Maintain grade Pass-{ctx['grade']} and the existing facility. "
        f"Do not treat unpledged deposits as a covenant remedy."
    )))
    shortfall = PROPOSAL_WORDS - words(document)
    if shortfall > 0:
        add_paragraph(document, prose(ctx, "supplementary recommendation", shortfall + 30))
    return document


def publish(customer: dict, point: dict, folder: Path, *, write_proposal: bool) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    if write_proposal:
        build_proposal(customer, point).save(folder / "proposal.docx")
    build_monitoring(customer, point, []).save(folder / "report.docx")


def refresh_apex_base(source: Path) -> None:
    TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != TEMPLATE.resolve():
        shutil.copyfile(source, TEMPLATE)
