"""Full-length proposal and monitoring report papers.

Apex Global Holdings keeps its annual-review proposal and the detailed
monitoring report. Every other obligor gets the same sections and the same
tables, filled from that obligor's own RDW, ECL and collateral rows. The
narrative is written out to at least the length of the Apex paper.

Confirmed adverse news is summarised into section 7. Confirmed actions are
summarised under section 9.
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
APEX_PROPOSAL = ROOT / "report_files" / "obligors" / "BOR-AGHL" / "proposal.docx"
APEX_ID = "BOR-AGHL"
NAVY = "1F4E79"
AMBER = "8C3E16"


def words(doc: Document) -> int:
    chunks = [paragraph.text for paragraph in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                chunks.append(cell.text)
    return sum(len(chunk.split()) for chunk in chunks)


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


def insert_before(anchor, text: str, *, bold=False) -> None:
    element = OxmlElement("w:p")
    anchor._p.addprevious(element)
    paragraph = Paragraph(element, anchor._parent)
    run = paragraph.add_run(text)
    run.bold = bold
    run.font.size = Pt(11)
    run.font.name = "Calibri"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")


def accepted_actions(actions: list[dict] | None) -> list[dict]:
    return [item for item in (actions or []) if (item.get("text") or item.get("headline") or "").strip()]


def condense(text: str, limit: int = 40) -> str:
    words = " ".join(str(text or "").split())
    pieces = words.split()
    if len(pieces) <= limit:
        return words
    return " ".join(pieces[:limit]).rstrip(".,;") + "."


def news_summary(actions: list[dict], name: str) -> str:
    counts = {}
    for item in actions:
        level = str(item.get("severity") or "UNSTATED")
        counts[level] = counts.get(level, 0) + 1
    mix = ", ".join(f"{counts[level]} {level}" for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNSTATED") if counts.get(level))
    clauses = []
    for item in actions:
        clauses.append(
            f"{item.get('headline') or 'Adverse news'} "
            f"({item.get('severity') or 'unspecified'}, {item.get('source') or 'source not stated'}, {item.get('date') or 'date not stated'})"
        )
    return (
        f"Summary of adverse news confirmed for {name}. "
        f"{len(actions)} item(s) are covered ({mix}). "
        f"They are recorded here as one market-news point, together with the commentary already in this section. "
        f"The items are: {'; '.join(clauses)}. "
        f"This summary does not change the facility, the security position or the grade."
    )


def action_summary(actions: list[dict], name: str) -> str:
    steps = []
    for index, item in enumerate(actions, start=1):
        steps.append(f"({index}) {condense(item.get('text') or item.get('headline') or '')}")
    return (
        f"Summary of the actions confirmed for {name} from the news in section 7. "
        f"The relationship manager is to treat the follow-up as one plan under this section: {' '.join(steps)} "
        f"The action plan already set out above remains in place. This summary does not change a grade or a limit."
    )


def apply_summaries(document: Document, actions: list[dict], name: str) -> Document:
    if not actions:
        return document
    insert_block(
        document,
        "8. Deposit Balance",
        [("Summary of confirmed adverse news", True), (news_summary(actions, name), False)],
    )
    insert_block(
        document,
        "Overall Conclusion",
        [("Summary of confirmed actions", True), (action_summary(actions, name), False)],
    )
    return document


def insert_block(document: Document, anchor_prefix: str, blocks: list[tuple[str, bool]]) -> None:
    anchor = next(paragraph for paragraph in document.paragraphs if paragraph.text.strip().startswith(anchor_prefix))
    for text, bold in reversed(blocks):
        insert_before(anchor, text, bold=bold)


def heading(doc, text, *, size=13, color=NAVY, before=14) -> None:
    add_paragraph(doc, text, bold=True, size=size, color=color, before=before, after=6)


def subhead(doc, text, *, color=AMBER) -> None:
    add_paragraph(doc, text, bold=True, size=11, color=color, before=8, after=4)


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


def shade(cell, fill: str) -> None:
    props = cell._tc.get_or_add_tcPr()
    element = OxmlElement("w:shd")
    element.set(qn("w:fill"), fill)
    element.set(qn("w:val"), "clear")
    props.append(element)


def blank(doc: Document) -> None:
    section = doc.sections[0]
    section.top_margin = Cm(1.6)
    section.bottom_margin = Cm(1.6)
    section.left_margin = Cm(1.6)
    section.right_margin = Cm(1.6)
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)


def hk(value) -> str:
    if value is None or value == "":
        return "not on the extract"
    number = float(value)
    return f"HK${number / 1_000_000:.1f} million"


def ratio_pct(value) -> str:
    if value is None or value == "":
        return "not on the extract"
    return f"{float(value) * 100:.1f}%"


def multiple(value) -> str:
    if value is None or value == "":
        return "not on the extract"
    return f"{float(value):.2f}x"


def nice_date(value) -> str:
    if not value:
        return "not on the extract"
    text = str(value)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%-d %b %Y")
        except ValueError:
            continue
    return text


def long_date(iso: str) -> str:
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%-d %B %Y")


def short_date(iso: str) -> str:
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d %b %Y").upper()


def person(customer: dict) -> str:
    name = (customer.get("rm") or "").strip()
    if "facilit" in name.lower() or not name:
        return "Not named on the extract"
    return name


def rm_phrase(customer: dict, *, leading: bool = False) -> str:
    name = person(customer)
    if name != "Not named on the extract":
        return name
    return "The RM" if leading else "the RM"


def grade_label(point: dict) -> str:
    rating = point.get("rating")
    if classification(point) == "Pass":
        return f"Pass-{rating}"
    return f"Grade {rating}"


def series_text(values, *, money: bool = False) -> str:
    if not values:
        return "not on the file"
    parts = []
    for value in values:
        if value is None:
            parts.append("not stated")
        elif money:
            parts.append(hk(value))
        else:
            parts.append(f"{float(value):.1f}")
    return ", ".join(parts)


def on_balance(point: dict) -> list[dict]:
    return [item for item in point.get("facilities") or [] if item.get("instrument") != "Off-Bal"]


def place(facility: dict) -> str:
    address = (facility.get("address") or "").strip()
    district = (facility.get("district") or "").strip()
    if address and district and district not in address:
        return f"{address}, {district}"
    if address:
        return address
    collateral_id = facility.get("collateral_id") or ""
    if collateral_id:
        return f"address not on the collateral extract ({collateral_id})"
    return "address not on the collateral extract"


def classification(point: dict) -> str:
    statuses = {item.get("status") for item in point.get("facilities") or []}
    if point.get("stage", 1) >= 3 or "Defaulted" in statuses:
        return "Default"
    if point.get("stage", 1) >= 2 or "Special Mention" in statuses:
        return "Special Mention"
    return "Pass"


def clean_exposure(point: dict) -> str:
    drawn = float(point.get("drawn_hkd") or 0)
    collateral = float(point.get("collateral_hkd") or 0)
    gap = drawn - collateral
    if gap <= 1:
        return "Nil"
    return hk(gap)


def year_rows(point: dict) -> list[list[str]]:
    buckets: dict[str, float] = {}
    drawn = float(point.get("drawn_hkd") or 0)
    for item in on_balance(point):
        maturity = str(item.get("maturity") or "")
        year = maturity[:4] if len(maturity) >= 4 and maturity[:4].isdigit() else "Undated"
        buckets[year] = buckets.get(year, 0) + float(item.get("balance_hkd") or 0)
    rows = []
    for year in sorted(buckets):
        amount = buckets[year]
        share = f"{amount / drawn:.1%}" if drawn else "n.a."
        rows.append([year, hk(amount), share])
    rows.append(["Total on-balance", hk(drawn), "100%" if drawn else "n.a."])
    return rows


def facility_lines(facility: dict, mode: str) -> str:
    contract = facility.get("contract") or "contract not numbered"
    instrument = facility.get("instrument") or "facility"
    status = facility.get("status") or "status not stated"
    where = place(facility)
    if mode == "tenor":
        return (
            f"{contract} is a {instrument} in {status} status, stage {facility.get('stage')}, "
            f"{facility.get('dpd')} days past due, department {facility.get('department') or 'not stated'}. "
            f"Drawn balance {hk(facility.get('balance_hkd'))}, limit {hk(facility.get('limit_hkd'))}, "
            f"undrawn {hk(facility.get('available_hkd'))}. Maturity {nice_date(facility.get('maturity'))}. "
            f"ECL on this row is {hk(facility.get('ecl_hkd'))} and EAD is {hk(facility.get('ead_hkd'))}."
        )
    if mode == "security":
        return (
            f"Collateral on {contract} is {facility.get('collateral_type') or 'type not stated'} "
            f"at {where}. Charge {facility.get('charge') or 'not stated'}. "
            f"Market value {hk(facility.get('market_hkd'))}, net realisable value {hk(facility.get('nrv_hkd'))}. "
            f"Contract LTV {ratio_pct(facility.get('ltv'))} and LTV on net realisable value {ratio_pct(facility.get('ltv_nrv'))}. "
            f"The balance secured against that record is {hk(facility.get('balance_hkd'))}."
        )
    return (
        f"Allowance on {contract}: PD {facility.get('pd') if facility.get('pd') is not None else 'not stated'}, "
        f"LGD {facility.get('lgd') if facility.get('lgd') is not None else 'not stated'}, "
        f"ECL {hk(facility.get('ecl_hkd'))}, nominal {hk(facility.get('nominal_hkd'))}. "
        f"Grade on the row is {facility.get('grade')}, original grade {facility.get('original_grade')}. "
        f"Status {status}. These fields are the ECL row, not a separate rating memo."
    )


def signed_hk(value) -> str:
    number = float(value or 0)
    sign = "+" if number > 0 else ""
    return f"{sign}HK${number / 1_000_000:.1f} million"


def movement_notes(customer: dict) -> list[str]:
    history = customer.get("history") or []
    notes = []
    for earlier, later in zip(history, history[1:]):
        notes.append(
            f"From {long_date(earlier['date'])} to {long_date(later['date'])}, drawn moved {signed_hk(float(later.get('drawn_hkd') or 0) - float(earlier.get('drawn_hkd') or 0))} "
            f"to {hk(later.get('drawn_hkd'))} and ECL moved {signed_hk(float(later.get('ecl_hkd') or 0) - float(earlier.get('ecl_hkd') or 0))} to {hk(later.get('ecl_hkd'))}. "
            f"Stage went from {earlier.get('stage')} to {later.get('stage')}, days past due from {earlier.get('dpd')} to {later.get('dpd')}, "
            f"and grade from {earlier.get('rating')} to {later.get('rating')}. "
            f"Collateral moved from {hk(earlier.get('collateral_hkd'))} to {hk(later.get('collateral_hkd'))}, "
            f"net realisable value from {hk(earlier.get('nrv_hkd'))} to {hk(later.get('nrv_hkd'))}, "
            f"EAD from {hk(earlier.get('ead_hkd'))} to {hk(later.get('ead_hkd'))}. "
            f"LTV moved from {ratio_pct(earlier.get('ltv'))} to {ratio_pct(later.get('ltv'))} and coverage from {multiple(earlier.get('coverage_ratio'))} to {multiple(later.get('coverage_ratio'))}. "
            f"The next obligation on the later month was {hk(later.get('next_due_hkd'))} due {nice_date(later.get('next_due_date'))}, {later.get('next_due_days')} days out, on {later.get('next_contract')}."
        )
    return notes


def history_text(customer: dict) -> str:
    parts = []
    history = customer.get("history") or []
    for month in history:
        parts.append(
            f"At {long_date(month['date'])} drawn was {hk(month.get('drawn_hkd'))}, "
            f"ECL {hk(month.get('ecl_hkd'))}, stage {month.get('stage')}, "
            f"{month.get('dpd')} days past due and grade {month.get('rating')}."
        )
    return " ".join(parts)


def statement_value(series, index: int) -> str:
    if not series or index >= len(series) or series[index] is None:
        return "not on the file"
    value = series[index]
    if isinstance(value, float) and value < 50:
        return f"{value:.1f}"
    return hk(value)


def build_monitoring(customer: dict, point: dict, actions: list[dict] | None = None) -> Document:
    """Detailed nine-section monitoring report from this obligor's own extract."""
    confirmed = accepted_actions(actions)
    name = customer.get("legal_name") or customer["customer_id"]
    if customer.get("customer_id") == APEX_ID:
        return apply_summaries(Document(str(TEMPLATE)), confirmed, name)
    document = Document()
    blank(document)
    write_monitoring(document, customer, point)
    extend_with_extract(document, customer, point, words(Document(str(TEMPLATE))))
    return apply_summaries(document, confirmed, name)


def save_monitoring(customer: dict, point: dict, actions: list[dict] | None, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if customer.get("customer_id") == APEX_ID and not accepted_actions(actions):
        if path.resolve() != TEMPLATE.resolve():
            shutil.copyfile(TEMPLATE, path)
        return
    build_monitoring(customer, point, actions).save(path)



def extend_with_extract(document: Document, customer: dict, point: dict, minimum: int) -> None:
    facilities = list(point.get("facilities") or [])
    sentences = []
    for facility in facilities:
        for mode in ("tenor", "security", "allowance"):
            sentences.append(facility_lines(facility, mode))
    sentences.append(history_text(customer))
    sentences.extend(movement_notes(customer))
    cursor = 0
    while words(document) < minimum and cursor < len(sentences):
        block = []
        while cursor < len(sentences) and len(" ".join(block).split()) < 110:
            block.append(sentences[cursor])
            cursor += 1
        add_paragraph(document, " ".join(block))


def monitor_heading(doc, text: str) -> None:
    add_paragraph(doc, text, bold=True, size=12, before=10, after=6)


def monitor_sub(doc, text: str) -> None:
    add_paragraph(doc, text, bold=True, size=11, before=8, after=4)


def write_monitoring(document: Document, customer: dict, point: dict) -> None:
    name = customer.get("legal_name") or customer["customer_id"]
    group = customer.get("group_name") or name
    industry = customer.get("industry") or "not stated"
    facilities = on_balance(point)
    secured = [item for item in point.get("facilities") or [] if item.get("market_hkd") or (item.get("address") or "").strip()]
    maturities = sorted(facilities, key=lambda item: str(item.get("maturity") or "9999"))
    final = nice_date(maturities[-1].get("maturity")) if maturities else "not on the extract"
    add_paragraph(document, f"{name} Credit Monitoring Report", bold=True, size=16, before=0, after=2)
    add_paragraph(document, f"Reporting Date: {short_date(point['date'])}", bold=True, size=11, before=0, after=8)
    monitor_heading(document, "1. Facility Information")
    add_table(
        document,
        ["Item", "Details"],
        [
            ["Customer Group", group],
            ["Borrower", name],
            ["Industry", industry],
            ["Outstanding Exposure", hk(point.get("drawn_hkd"))],
            ["Clean Exposure", clean_exposure(point)],
            ["ECL", hk(point.get("ecl_hkd"))],
            ["Borrower Grade", grade_label(point)],
            ["Loan Classification", classification(point)],
            ["Interest Rate", "Not stated on the RDW facility row"],
            ["Final Maturity", final],
        ],
        header_fill="F5F5F5",
        header_color="000000",
    )
    monitor_sub(document, "Repayment Schedule")
    schedule = [[nice_date(item.get("maturity")), f"{item.get('contract')} principal {hk(item.get('balance_hkd'))}"] for item in maturities]
    schedule.append([nice_date(point.get("next_due_date")), f"Next obligation {hk(point.get('next_due_hkd'))} on {point.get('next_contract')} ({point.get('next_method') or 'method not stated'})"])
    add_table(document, ["Due Date", "Amount"], schedule, header_fill="F5F5F5", header_color="000000")
    monitor_sub(document, "Assessment")
    add_paragraph(document, (
        f"At {long_date(point['date'])} {name} has drawn {hk(point.get('drawn_hkd'))} against committed {hk(point.get('committed_hkd'))}. "
        f"ECL is {hk(point.get('ecl_hkd'))}, from {hk(point.get('prior_ecl_hkd'))} at the prior month. "
        f"Grade on the extract is {grade_label(point)} against original grade {customer.get('prior_rating')}. "
        f"Classification on these rows is {classification(point)}. Stage {point.get('stage')}, {point.get('dpd')} days past due. "
        f"The next cash date is {nice_date(point.get('next_due_date'))}, {hk(point.get('next_due_hkd'))}, {point.get('next_due_days')} days out, contract {point.get('next_contract')}. "
        f"Relationship manager: {person(customer)}. The facility rows do not carry a coupon, so this report does not state a margin."
    ))
    for item in facilities:
        add_paragraph(document, facility_lines(item, "tenor"))
    monitor_heading(document, "2. Maturity Profile")
    monitor_sub(document, "Group Debt Maturity Profile")
    creditors = [["This Bank", item.get("instrument") or "", hk(item.get("balance_hkd")), nice_date(item.get("maturity"))] for item in maturities]
    creditors.append(["Total on this extract", "", hk(point.get("drawn_hkd")), ""])
    add_table(document, ["Creditor", "Facility Type", "Outstanding Amount", "Maturity"], creditors, header_fill="F5F5F5", header_color="000000")
    monitor_sub(document, "Debt Maturity Breakdown")
    add_table(document, ["Year", "Amount", "% of Total Debt"], year_rows(point), header_fill="F5F5F5", header_color="000000")
    monitor_sub(document, "Assessment")
    off_balance = [item for item in point.get("facilities") or [] if item.get("instrument") == "Off-Bal"]
    add_paragraph(document, (
        f"The maturity profile uses this Bank's facility rows only. The RDW extract does not list other lenders' balances for {name}, "
        f"so no third-party creditor is added. On-balance contracts: {len(facilities)}. Off-balance rows: {len(off_balance)}. "
        f"Refinancing flag on the extract: {'yes' if point.get('refinancing') else 'no'}. "
        f"The first dated on-balance maturity is {nice_date(maturities[0].get('maturity')) if maturities else 'not on the extract'} "
        f"and the last is {final}."
    ))
    monitor_heading(document, "3. Security Position")
    monitor_sub(document, "Collateral Details")
    assets = [[place(item), hk(item.get("market_hkd"))] for item in secured] or [["No collateral row with an address or a market value", "not on the extract"]]
    assets.append(["Total collateral on the obligor extract", hk(point.get("collateral_hkd"))])
    add_table(document, ["Security", "Latest Valuation"], assets, header_fill="F5F5F5", header_color="000000")
    monitor_sub(document, "Security Metrics")
    add_table(
        document,
        ["Item", "Amount"],
        [
            ["Outstanding Exposure", hk(point.get("drawn_hkd"))],
            ["Collateral Value", hk(point.get("collateral_hkd"))],
            ["Net realisable value", hk(point.get("nrv_hkd"))],
            ["Security Coverage Ratio", multiple(point.get("coverage_ratio"))],
            ["LTV", ratio_pct(point.get("ltv"))],
            ["Clean Exposure", clean_exposure(point)],
            ["Guarantor", customer.get("guarantor") or "None on the extract"],
        ],
        header_fill="F5F5F5",
        header_color="000000",
    )
    monitor_sub(document, "Assessment")
    add_paragraph(document, (
        f"Collateral recorded for {name} is {hk(point.get('collateral_hkd'))}, type {customer.get('collateral_type') or 'not stated on the obligor'}. "
        f"Coverage of drawn exposure is {multiple(point.get('coverage_ratio'))}. Portfolio LTV on the extract is {ratio_pct(point.get('ltv'))}. "
        f"Clean exposure is {clean_exposure(point)}. Net realisable value is {hk(point.get('nrv_hkd'))}. "
        f"Row-level market values are listed above and are not forced to equal the obligor total where the extract keeps them separate. "
        f"Guarantor on the file: {customer.get('guarantor') or 'none'}."
    ))
    for item in point.get("facilities") or []:
        add_paragraph(document, facility_lines(item, "security"))
    monitor_heading(document, "4. Latest Development")
    monitor_sub(document, "Business Performance")
    add_paragraph(document, statement_paragraph(customer, point))
    monitor_sub(document, "Property Disposal Programme")
    add_paragraph(document, (
        f"The RDW, ECL and collateral extracts do not record a completed disposal for {name}. "
        f"No disposal proceeds are applied against the drawn balance of {hk(point.get('drawn_hkd'))} in this report."
    ))
    monitor_sub(document, "Refinancing Arrangement")
    add_paragraph(document, (
        f"The extract refinancing flag is {'set' if point.get('refinancing') else 'not set'}. "
        f"The next obligation is {hk(point.get('next_due_hkd'))} on {nice_date(point.get('next_due_date'))}. "
        f"No binding term sheet from another lender is on these files."
    ))
    monitor_sub(document, "Assessment")
    add_paragraph(document, (
        f"Development since {long_date(customer['history'][0]['date'])}: drawn {hk(customer['history'][0].get('drawn_hkd'))} to {hk(point.get('drawn_hkd'))}, "
        f"ECL {hk(customer['history'][0].get('ecl_hkd'))} to {hk(point.get('ecl_hkd'))}, "
        f"stage {customer['history'][0].get('stage')} to {point.get('stage')}, "
        f"days past due {customer['history'][0].get('dpd')} to {point.get('dpd')}. "
        f"{history_text(customer)}"
    ))
    monitor_heading(document, "5. Account Conduct")
    monitor_sub(document, "Assessment")
    worst = classification(point)
    add_table(
        document,
        ["Item", "Status"],
        [
            ["Interest Servicing", "No separate interest-past-due field on the extract"],
            ["Principal Repayment", f"{hk(point.get('next_due_hkd'))} due {nice_date(point.get('next_due_date'))}"],
            ["Past Due Record", f"{point.get('dpd')} days"],
            ["Stage", str(point.get("stage"))],
            ["ECL", hk(point.get("ecl_hkd"))],
            ["Worst classification", worst],
        ],
        header_fill="F5F5F5",
        header_color="000000",
    )
    warnings = [item.get("description") for item in (customer.get("warnings") or []) if item.get("description")]
    add_paragraph(document, (
        f"Conduct is read from stage {point.get('stage')} and {point.get('dpd')} days past due, not from a call report. "
        f"The worst label on the facility rows is {worst}. "
        + (" ".join(warnings) if warnings else "No warning text is stored beyond stage and days past due.")
    ))
    for item in facilities:
        add_paragraph(document, facility_lines(item, "allowance"))
    monitor_heading(document, "6. Account Strategy")
    posture = "restore conduct and keep the name under enhanced monitoring" if point.get("stage", 1) >= 2 or point.get("dpd", 0) > 0 or worst == "Default" else "maintain the facility and watch collateral and maturity"
    monitor_sub(document, f"Strategy: {posture[0].upper()}{posture[1:]}")
    add_paragraph(document, (
        f"The strategy for {name} is to {posture}. {grade_label(point)} stays the grade on the extract until a review changes it. "
        f"{rm_phrase(customer, leading=True)} is to track drawn {hk(point.get('drawn_hkd'))}, ECL {hk(point.get('ecl_hkd'))}, "
        f"collateral {hk(point.get('collateral_hkd'))} and the next date of {nice_date(point.get('next_due_date'))}. "
        f"No new money is proposed in this monitoring report."
    ))
    monitor_heading(document, "7. Other Market News")
    districts = sorted({item.get("district") for item in secured if item.get("district")})
    add_paragraph(document, (
        f"The collateral extract for {name} sits in {industry}. "
        f"Districts named on the rows: {', '.join(districts) if districts else 'none. Addresses are missing on the collateral rows that were checked'}. "
        f"Portfolio LTV is {ratio_pct(point.get('ltv'))}. Market commentary is limited to those collateral locations and this industry. "
        f"It does not replace the row-level valuations."
    ))
    monitor_heading(document, "8. Deposit Balance")
    monitor_sub(document, "Assessment")
    add_table(
        document,
        ["Account Type", "Balance"],
        [
            ["Operating Accounts", "Not on the RDW, ECL or collateral extract"],
            ["Time Deposit", "Not on the extract"],
            ["Total Deposits", "Not recorded, and not treated as security"],
        ],
        header_fill="F5F5F5",
        header_color="000000",
    )
    add_paragraph(document, (
        f"No deposit balance for {name} is on the RDW, ECL or collateral files used for this report. "
        f"Nothing is described as pledged, and deposits are not used to change LTV of {ratio_pct(point.get('ltv'))} or collateral of {hk(point.get('collateral_hkd'))}."
    ))
    monitor_heading(document, "9. Suggested Action Plan")
    monitor_sub(document, "RM Action Plan")
    actions = action_rows(customer, point)
    add_paragraph(document, (
        f"{rm_phrase(customer, leading=True)} should work from the extract at {long_date(point['date'])}. "
        f"Drawn {hk(point.get('drawn_hkd'))}, ECL {hk(point.get('ecl_hkd'))}, grade {grade_label(point)}, "
        f"stage {point.get('stage')}, {point.get('dpd')} days past due, next cash {hk(point.get('next_due_hkd'))} on {nice_date(point.get('next_due_date'))}."
    ))
    for step, _priority in actions:
        add_paragraph(document, step, after=2)
    add_table(document, ["Action Item", "Priority"], actions, header_fill="F5F5F5", header_color="000000")
    monitor_sub(document, "Overall Conclusion")
    add_paragraph(document, (
        f"{name} is {grade_label(point)}, classification {worst}, with drawn {hk(point.get('drawn_hkd'))} and collateral {hk(point.get('collateral_hkd'))}. "
        f"Clean exposure is {clean_exposure(point)}. The points to watch are days past due {point.get('dpd')}, LTV {ratio_pct(point.get('ltv'))}, "
        f"ECL {hk(point.get('ecl_hkd'))} and maturity through {final}. This report does not change a grade or a limit."
    ))


def statement_paragraph(customer: dict, point: dict) -> str:
    revenue = customer.get("revenue_hkd") or []
    if not revenue or all(item is None for item in revenue):
        return (
            f"The obligor file for {customer.get('legal_name')} has no revenue or interest-cover series. "
            f"Operating performance is therefore not taken from statements. The latest ECL is {hk(point.get('ecl_hkd'))} on drawn {hk(point.get('drawn_hkd'))}."
        )
    return (
        f"The statement series stored for {customer.get('legal_name')} — separate from the RDW balance — runs "
        f"{series_text(revenue, money=True)}. Interest cover on that series is {series_text(customer.get('interest_coverage'))} times. "
        f"Leverage {series_text(customer.get('leverage'))}. Liquidity {series_text(customer.get('liquidity_ratio'))}. "
        f"Margin {series_text(customer.get('margin_pct'))}. "
        f"These figures are not a substitute for the drawn balance of {hk(point.get('drawn_hkd'))}."
    )


def action_rows(customer: dict, point: dict) -> list[list[str]]:
    rows = []
    if point.get("dpd", 0):
        rows.append([f"Follow up {point.get('dpd')} days past due on the extract.", "High"])
    if point.get("stage", 1) >= 2:
        rows.append([f"Review the stage {point.get('stage')} classification before the next month-end.", "High"])
    if any(item.get("status") == "Defaulted" for item in point.get("facilities") or []):
        rows.append(["Confirm the defaulted facility rows and the related collateral.", "High"])
    rows.append([f"Check the next obligation of {hk(point.get('next_due_hkd'))} due {nice_date(point.get('next_due_date'))}.", "High"])
    rows.append([f"Update the valuation behind collateral of {hk(point.get('collateral_hkd'))}.", "High"])
    if float(point.get("ecl_hkd") or 0) != float(point.get("prior_ecl_hkd") or 0):
        rows.append([f"Explain the ECL move from {hk(point.get('prior_ecl_hkd'))} to {hk(point.get('ecl_hkd'))}.", "High"])
    missing = [item.get("contract") for item in point.get("facilities") or [] if not (item.get("address") or "").strip()]
    if missing:
        rows.append([f"Obtain addresses for {', '.join(missing[:4])}.", "Medium"])
    if not missing:
        rows.append(["Reconcile each collateral address already on the extract to the valuation.", "Medium"])
    if not point.get("dpd", 0):
        rows.append(["Confirm days past due remain nil on the next month's extract.", "Medium"])
    if point.get("stage", 1) < 2 and not any(item.get("status") == "Defaulted" for item in point.get("facilities") or []):
        rows.append([f"Keep stage {point.get('stage')} under the ordinary annual review.", "Medium"])
    if float(point.get("ecl_hkd") or 0) == float(point.get("prior_ecl_hkd") or 0):
        rows.append([f"ECL is unchanged at {hk(point.get('ecl_hkd'))}. Record the reason on the file.", "Medium"])
    rows.append([f"File the next call note by {rm_phrase(customer)}.", "Medium"])
    return rows


def write_proposal(document: Document, customer: dict, point: dict) -> None:
    name = customer.get("legal_name") or customer["customer_id"]
    industry = customer.get("industry") or "not stated"
    guarantor = customer.get("guarantor") or "None on the extract"
    facilities = on_balance(point)
    secured = [item for item in point.get("facilities") or [] if item.get("market_hkd") or (item.get("address") or "").strip() or item.get("collateral_type")]
    first = customer["history"][0]
    as_of = long_date(point["date"])
    grade = grade_label(point)
    add_paragraph(document, "SUBJECT CREDIT PROPOSAL", bold=True, size=9, color=NAVY, before=0, after=2)
    add_paragraph(document, f"Annual Review — {name}", bold=True, size=20, color=NAVY, before=0, after=2)
    add_paragraph(document, f"Credit memo date {as_of}  ·  {customer['customer_id']}", size=12, color=AMBER, before=0, after=8)
    add_paragraph(document, (
        f"Figures are the {as_of} month on the RDW, ECL and collateral extracts for {name}. "
        f"Where a coupon, a deposit balance or another lender's debt is absent from those files, the paper says so."
    ), italic=True, size=9, color="666666")
    heading(document, "Proposal type")
    add_table(document, ["Type", "Selected"], [
        ["New application", "No"],
        ["Limit increase", "No"],
        ["Annual renewal / review", "Yes"],
        ["Others", f"Annual review of the {hk(point.get('drawn_hkd'))} drawn balance"],
    ])
    heading(document, "Signing section")
    add_table(document, ["Role", "Name"], [
        ["Borrower", name],
        ["Group on the extract", customer.get("group_name") or name],
        ["Industry", industry],
        ["Jurisdiction", customer.get("jurisdiction") or "not stated"],
        ["Guarantor", guarantor],
        ["Relationship manager", person(customer)],
        ["Current grade", grade],
        ["Original grade", str(customer.get("prior_rating"))],
        ["Stage", str(point.get("stage"))],
        ["Days past due", str(point.get("dpd"))],
        ["Drawn exposure", hk(point.get("drawn_hkd"))],
        ["ECL", hk(point.get("ecl_hkd"))],
        ["Collateral", hk(point.get("collateral_hkd"))],
        ["Prepared for", "BEA - Risk Intelligence"],
    ])
    heading(document, "Approval section")
    add_paragraph(document, (
        f"This annual review of {name} uses the extract at {as_of}. Drawn {hk(point.get('drawn_hkd'))}, "
        f"committed {hk(point.get('committed_hkd'))}, ECL {hk(point.get('ecl_hkd'))}, grade to be maintained {grade}. "
        f"Classification {classification(point)}. Clean exposure {clean_exposure(point)}."
    ))
    add_table(document, ["Item", "Date"], [
        ["Position used for this paper", as_of],
        ["Opening month on the history file", long_date(first["date"])],
        ["Proposed next review", "One year after the position date"],
        ["Next obligation", f"{hk(point.get('next_due_hkd'))} on {nice_date(point.get('next_due_date'))}"],
    ])
    heading(document, "A. Facility section")
    subhead(document, "Nature of proposal")
    add_paragraph(document, (
        f"The request is an annual review of the existing facilities for {name}. There is no new money. "
        f"On-balance contracts on the extract: {len(facilities)}. "
        f"The limit discussion stays at drawn {hk(point.get('drawn_hkd'))} and committed {hk(point.get('committed_hkd'))}."
    ))
    subhead(document, "A1 : Facility overviews")
    overview = [[
        name,
        item.get("instrument") or "",
        hk(item.get("limit_hkd")),
        hk(item.get("balance_hkd")),
        hk(item.get("balance_hkd")),
        "No change",
    ] for item in facilities] or [[name, "No on-balance row", "not on the extract", hk(point.get("drawn_hkd")), hk(point.get("drawn_hkd")), "No change"]]
    add_table(document, ["Borrower", "Type", "Committed", "Existing (HK$ m)", "Proposed (HK$ m)", "Change"], overview)
    add_paragraph(document, f"The overview is the on-balance RDW rows. Obligor drawn is {hk(point.get('drawn_hkd'))} and obligor ECL is {hk(point.get('ecl_hkd'))}.")
    for item in facilities:
        add_paragraph(document, facility_lines(item, "tenor"))
    add_table(document, ["Item", f"Position at {as_of}"], [
        ["Borrower", name],
        ["Industry", industry],
        ["Grade", grade],
        ["Stage", str(point.get("stage"))],
        ["Drawn", hk(point.get("drawn_hkd"))],
        ["ECL", hk(point.get("ecl_hkd"))],
        ["Collateral", hk(point.get("collateral_hkd"))],
    ])
    subhead(document, "Repayment schedule, as recorded on the extract.")
    dues = [[nice_date(item.get("maturity")), f"{item.get('contract')} {hk(item.get('balance_hkd'))}"] for item in facilities]
    dues.append([nice_date(point.get("next_due_date")), f"Next obligation {hk(point.get('next_due_hkd'))} ({point.get('next_method') or 'method not stated'})"])
    add_table(document, ["Due date", "Amount"], dues)
    subhead(document, "A2 : Deviation from guideline")
    add_table(document, ["Item", "Position"], [
        ["New money", "None in this paper"],
        ["Pricing", "Coupon is not on the RDW facility row. Existing margin stands."],
    ])
    subhead(document, "A3 : Controller group exposure")
    add_paragraph(document, (
        f"The extract records the group name as {customer.get('group_name') or name}. "
        f"This paper does not add other obligors' balances into {name}."
    ))
    add_table(document, ["Item", "Existing", "Proposed"], [
        ["Borrower drawn", hk(point.get("drawn_hkd")), hk(point.get("drawn_hkd"))],
        ["Committed", hk(point.get("committed_hkd")), hk(point.get("committed_hkd"))],
        ["ECL", hk(point.get("ecl_hkd")), hk(point.get("ecl_hkd"))],
        ["Collateral", hk(point.get("collateral_hkd")), hk(point.get("collateral_hkd"))],
        ["Grade", grade, f"{grade}, maintained"],
        ["Stage", str(point.get("stage")), str(point.get("stage"))],
        ["Guarantor", guarantor, guarantor],
        ["Industry", industry, industry],
    ])
    subhead(document, "A4 : Facility details")
    subhead(document, "Background")
    subhead(document, "Purpose")
    subhead(document, "Assessment of size, type, tenor and purpose")
    add_paragraph(document, (
        f"{name} is on the {industry} file in {customer.get('jurisdiction') or 'the jurisdiction on the extract'}. "
        f"Size is drawn {hk(point.get('drawn_hkd'))}. Tenor is the maturity on each contract, the latest being "
        f"{nice_date(max((str(item.get('maturity') or '') for item in facilities), default=''))}. "
        f"Purpose is continuation of those contracts, not an increase."
    ))
    subhead(document, "A5 : Security details and coverage")
    properties = [[
        item.get("collateral_type") or "Type not stated",
        place(item),
        item.get("collateral_type") or "",
        hk(item.get("market_hkd")),
        f"Charge {item.get('charge') or 'not stated'}",
    ] for item in secured] or [["No collateral row", "Address not on the extract", "", "not on the extract", ""]]
    add_table(document, ["Property", "Address", "Property type", "Latest valuation", "Mortgage ranking"], properties)
    for item in secured:
        add_paragraph(document, facility_lines(item, "security"))
    add_paragraph(document, (
        f"Obligor collateral total {hk(point.get('collateral_hkd'))}, net realisable value {hk(point.get('nrv_hkd'))}, "
        f"coverage {multiple(point.get('coverage_ratio'))}, LTV {ratio_pct(point.get('ltv'))}, clean exposure {clean_exposure(point)}. "
        f"The property rows are the facility collateral records and are not adjusted to force a match to the obligor total."
    ))
    add_table(document, ["Item", "Amount"], [
        ["Outstanding exposure", hk(point.get("drawn_hkd"))],
        ["Collateral value", hk(point.get("collateral_hkd"))],
        ["Net realisable value", hk(point.get("nrv_hkd"))],
        ["Coverage", multiple(point.get("coverage_ratio"))],
        ["LTV", ratio_pct(point.get("ltv"))],
        ["Guarantor", guarantor],
        ["Clean exposure", clean_exposure(point)],
        ["ECL", hk(point.get("ecl_hkd"))],
        ["Grade", grade],
    ])
    subhead(document, "A6 : Loan classification and internal rating")
    add_paragraph(document, (
        f"Grade on the extract is {grade}. Original grade {customer.get('prior_rating')}. "
        f"Stage {point.get('stage')}, {point.get('dpd')} days past due, classification {classification(point)}. "
        f"This review does not propose a downgrade or an upgrade."
    ))
    for item in facilities:
        add_paragraph(document, facility_lines(item, "allowance"))
    add_table(document, ["Item", "Position"], [
        ["Current grade", grade],
        ["Original grade", str(customer.get("prior_rating"))],
        ["Stage", str(point.get("stage"))],
        ["Days past due", str(point.get("dpd"))],
        ["ECL", hk(point.get("ecl_hkd"))],
        ["Proposed grade", f"{grade}, maintained"],
    ])
    subhead(document, "A6.1 : Capital requirement")
    add_table(document, ["Facility", "Exposure", "Treatment on this paper"], [
        [item.get("contract") or name, hk(item.get("balance_hkd")), "Existing facility, no increase"] for item in facilities
    ] or [[name, hk(point.get("drawn_hkd")), "Existing facility, no increase"]])
    subhead(document, "A6.2 : RORWA")
    add_paragraph(document, (
        f"Return is discussed against drawn {hk(point.get('drawn_hkd'))} and ECL {hk(point.get('ecl_hkd'))}. "
        f"The RDW rows do not state fee income, so none is added for {name}."
    ))
    subhead(document, "A7 : Account performance")
    add_paragraph(document, (
        f"At {as_of}, stage {point.get('stage')}, {point.get('dpd')} days past due. "
        f"Next cash date {nice_date(point.get('next_due_date'))} for {hk(point.get('next_due_hkd'))}."
    ))
    subhead(document, "A8 : Actions from the previous approval")
    add_table(document, ["Previous condition", "Status at this review"], [
        ["Keep the annual review current", f"This paper, dated {as_of}"],
        ["Watch collateral", f"{hk(point.get('collateral_hkd'))} on the extract, LTV {ratio_pct(point.get('ltv'))}"],
        ["Watch maturity", f"{hk(point.get('next_due_hkd'))} due {nice_date(point.get('next_due_date'))}"],
        ["Grade", f"{grade} maintained in this paper"],
    ])
    subhead(document, "A9 : Credit commentary")
    subhead(document, "1. Comments from Business Unit")
    subhead(document, f"Credit strategy: {'Enhanced monitoring.' if point.get('stage', 1) >= 2 or point.get('dpd', 0) else 'Maintain.'}")
    subhead(document, "Pros")
    pros = []
    if clean_exposure(point) == "Nil":
        pros.append(f"Collateral of {hk(point.get('collateral_hkd'))} covers drawn {hk(point.get('drawn_hkd'))}, so clean exposure is nil.")
    else:
        pros.append(f"The shortfall of collateral to drawn is stated as clean exposure {clean_exposure(point)}, not left blank.")
    if point.get("dpd", 0) == 0:
        pros.append("Days past due on the extract are nil.")
    addresses = [place(item) for item in secured if (item.get("address") or "").strip()]
    if addresses:
        pros.append(f"Collateral addresses are on the extract, including {addresses[0]}.")
    if not pros:
        pros.append(f"The relationship remains on file with {person(customer)}.")
    for item in pros:
        add_paragraph(document, item)
    subhead(document, "Cons")
    cons = []
    if point.get("dpd", 0):
        cons.append(f"The extract shows {point.get('dpd')} days past due.")
    if point.get("stage", 1) >= 2:
        cons.append(f"Stage is {point.get('stage')}.")
    if any(item.get("status") == "Defaulted" for item in point.get("facilities") or []):
        cons.append("At least one facility row is marked Defaulted.")
    try:
        if float(point.get("ltv") or 0) > 0.5:
            cons.append(f"Portfolio LTV on the extract is {ratio_pct(point.get('ltv'))}, above 50% as a numerical reading of exposure over collateral.")
    except (TypeError, ValueError):
        pass
    if float(point.get("ecl_hkd") or 0) > float(point.get("prior_ecl_hkd") or 0):
        cons.append(f"ECL rose from {hk(point.get('prior_ecl_hkd'))} to {hk(point.get('ecl_hkd'))}.")
    missing = [item.get("contract") for item in point.get("facilities") or [] if not (item.get("address") or "").strip()]
    if missing:
        cons.append(f"Collateral address is missing for {', '.join(str(item) for item in missing)}.")
    if not cons:
        cons.append("No stage, past-due or default flag is set on the latest extract. Maturity and valuation still need watching.")
    for item in cons:
        add_paragraph(document, item)
    subhead(document, "Risk mitigation")
    add_paragraph(document, (
        f"Mitigation is monitoring by {person(customer)}: the next repayment, the collateral value of {hk(point.get('collateral_hkd'))}, "
        f"and the ECL of {hk(point.get('ecl_hkd'))}. Unrecorded deposits are not treated as mitigation."
    ))
    subhead(document, "Recommendation")
    decision = "enhanced monitoring, no new money" if point.get("stage", 1) >= 2 or point.get("dpd", 0) or classification(point) == "Default" else "approval of the annual review with the facilities maintained"
    add_paragraph(document, (
        f"We recommend {decision} for {name}. Grade {grade} is maintained. "
        f"Drawn stays {hk(point.get('drawn_hkd'))}. No waiver is written for a covenant the extract does not state."
    ))
    for bullet in (
        "the annual review;",
        f"continuation of the on-balance facilities totalling {hk(point.get('drawn_hkd'))};",
        f"maintenance of borrower grade {grade};",
        "continued monitoring of the collateral rows, the next maturity and ECL; and",
        "no treatment of an unrecorded deposit as security.",
    ):
        add_paragraph(document, "•  " + bullet, after=2)
    subhead(document, "2. Comments from Department Head")
    add_paragraph(document, f"For the department head responsible for {industry}, on the {as_of} extract.")
    subhead(document, "3. Comments from CRCD (Risk Control Section)")
    add_paragraph(document, (
        f"Risk control notes grade {grade}, ECL {hk(point.get('ecl_hkd'))}, LTV {ratio_pct(point.get('ltv'))}, "
        f"stage {point.get('stage')} and {point.get('dpd')} days past due for {name}."
    ))
    subhead(document, "4. Comments from Division Head")
    add_paragraph(document, f"For the division head, on the {as_of} position of {name}.")
    heading(document, "B. Borrower section")
    add_paragraph(document, f"{name} is the borrower. Industry: {industry}. Group name on the extract: {customer.get('group_name') or name}.")
    subhead(document, "B1 : Company background")
    add_paragraph(document, (
        f"{name} is the obligor. Jurisdiction {customer.get('jurisdiction') or 'not stated'}. "
        f"Relationship manager {person(customer)}. Original grade {customer.get('prior_rating')}, current {grade}."
    ))
    subhead(document, "B2 : Business operation")
    add_paragraph(document, (
        f"Operations are those of a {industry} borrower. Debt service is tested against the repayment schedule, "
        f"next {hk(point.get('next_due_hkd'))} on {nice_date(point.get('next_due_date'))}."
    ))
    subhead(document, f"B3 : Financial analysis — {name}")
    add_paragraph(document, statement_paragraph(customer, point))
    add_paragraph(document, history_text(customer))
    subhead(document, "Month-to-month movement on the extract")
    for note in movement_notes(customer):
        add_paragraph(document, note)
    revenue = list(customer.get("revenue_hkd") or [])
    add_table(document, ["Item", as_of], [
        ["Drawn exposure", hk(point.get("drawn_hkd"))],
        ["ECL", hk(point.get("ecl_hkd"))],
        ["Collateral", hk(point.get("collateral_hkd"))],
        ["Grade", grade],
        ["Stage / days past due", f"{point.get('stage')} / {point.get('dpd')}"],
        ["Revenue series, latest", hk(revenue[-1]) if revenue and revenue[-1] is not None else "not on the file"],
    ])
    subhead(document, "B4 : Net worth of the borrower")
    add_paragraph(document, f"No personal net-worth statement is on the extract. The balance-sheet items used here are drawn {hk(point.get('drawn_hkd'))} and collateral {hk(point.get('collateral_hkd'))}.")
    subhead(document, "B5 : Relationship with other banks")
    add_paragraph(document, (
        f"Other lenders are not itemised on the RDW extract for {name}. "
        f"The table is this Bank's book of {hk(point.get('drawn_hkd'))}. Invented syndicate balances are not added."
    ))
    others = [["This Bank", f"{item.get('contract')} {item.get('instrument')}", hk(item.get("balance_hkd")), nice_date(item.get("maturity"))] for item in facilities]
    others.append(["Total on this extract", "", hk(point.get("drawn_hkd")), ""])
    add_table(document, ["Creditor", "Facility", "Outstanding", "Maturity"], others)
    add_table(document, ["Year", "Amount", "Share of total debt"], year_rows(point))
    subhead(document, "B6 : Warning signals / adverse news of the borrower")
    add_table(document, ["Signal", "Yes / No"], [
        ["Change of auditor", "Not on the extract"],
        ["Qualified audit opinion", "Not on the extract"],
        ["Change of senior management", "Not on the extract"],
        ["Failure to refinance", "Not recorded. Refinancing flag: " + ("yes" if point.get("refinancing") else "no")],
        ["Rating", f"{grade} on the extract, original {customer.get('prior_rating')}"],
        ["Litigation", "Not on the extract"],
        ["Regulator investigation", "Not on the extract"],
        ["LTV", ratio_pct(point.get("ltv"))],
        ["Days past due", str(point.get("dpd"))],
        ["Stage", str(point.get("stage"))],
        ["Defaulted row", "Yes" if any(item.get("status") == "Defaulted" for item in point.get("facilities") or []) else "No"],
        ["Adverse news actions", "Summarised in section 7 and section 9 of the monitoring report when confirmed"],
        ["Guarantor", guarantor],
    ])
    subhead(document, "B7 : Country risk")
    add_table(document, ["Item", "Position"], [
        ["Borrower", name],
        ["Jurisdiction", customer.get("jurisdiction") or "not stated"],
        ["Industry", industry],
        ["Watch-list", "No separate country watch-list is on the extract"],
        ["Transfer risk", "Not added unless the extract shows a foreign cash flow. It does not."],
    ])
    subhead(document, "B8 : ESG and climate risk")
    add_paragraph(document, f"No ESG incident is on the RDW or collateral extract for {name}. The collateral type on file is {customer.get('collateral_type') or 'not stated'}.")
    subhead(document, "B9 : Tax risk")
    add_paragraph(document, "No tax dispute is on the extract.")
    subhead(document, "B10 : Prevailing risk")
    add_paragraph(document, (
        f"The prevailing risks from the extract are LTV {ratio_pct(point.get('ltv'))}, "
        f"{point.get('dpd')} days past due, stage {point.get('stage')}, and the maturity on {nice_date(point.get('next_due_date'))}."
    ))
    subhead(document, "B11 : Site visit / call report")
    add_paragraph(document, f"No call report is attached. {rm_phrase(customer, leading=True)} is to place the next note before {nice_date(point.get('next_due_date'))}.")
    heading(document, "C. Guarantor section")
    add_paragraph(document, f"The guarantor line on the extract is: {guarantor}.")
    subhead(document, "C1 : Company background")
    add_paragraph(document, f"No separate guarantor financial file is attached. Support is limited to the words on the obligor extract: {guarantor}.")
    subhead(document, "C2 : Business operation")
    add_paragraph(document, f"The operating business remains that of {name} in {industry}.")
    subhead(document, f"C3 : Financial analysis — {guarantor}")
    add_paragraph(document, statement_paragraph(customer, point))
    revenue = list(customer.get("revenue_hkd") or [None, None, None])
    cover = list(customer.get("interest_coverage") or [None, None, None])
    leverage = list(customer.get("leverage") or [None, None, None])
    liquidity = list(customer.get("liquidity_ratio") or [None, None, None])
    while len(revenue) < 3:
        revenue.append(None)
    while len(cover) < 3:
        cover.append(None)
    while len(leverage) < 3:
        leverage.append(None)
    while len(liquidity) < 3:
        liquidity.append(None)

    def cell(value, kind="hk"):
        if value is None:
            return "not on the file"
        if kind == "hk":
            return hk(value)
        return f"{value:.1f}"

    def delta(latest, prior):
        if latest is None or prior in (None, 0):
            return "n.a."
        return f"{(float(latest) - float(prior)) / float(prior):+.1%}"

    add_table(document, ["", "Latest", "Change", "Prior", "Earlier"], [
        ["Revenue", cell(revenue[2]), delta(revenue[2], revenue[1]), cell(revenue[1]), cell(revenue[0])],
        ["Interest cover", cell(cover[2], "num"), delta(cover[2], cover[1]), cell(cover[1], "num"), cell(cover[0], "num")],
        ["Leverage", cell(leverage[2], "num"), delta(leverage[2], leverage[1]), cell(leverage[1], "num"), cell(leverage[0], "num")],
        ["Liquidity", cell(liquidity[2], "num"), delta(liquidity[2], liquidity[1]), cell(liquidity[1], "num"), cell(liquidity[0], "num")],
        ["Drawn", hk(point.get("drawn_hkd")), delta(point.get("drawn_hkd"), first.get("drawn_hkd")), hk(first.get("drawn_hkd")), "see history"],
        ["ECL", hk(point.get("ecl_hkd")), delta(point.get("ecl_hkd"), first.get("ecl_hkd")), hk(first.get("ecl_hkd")), "see history"],
        ["Collateral", hk(point.get("collateral_hkd")), "position", hk(first.get("collateral_hkd")), "see history"],
        ["Grade", grade, "maintained in this paper", grade_label(first), str(customer.get("prior_rating"))],
        ["Stage", str(point.get("stage")), "position", str(first.get("stage")), ""],
    ])
    subhead(document, "Profitability")
    add_paragraph(document, f"Profitability uses the statement series above where it exists. It is not taken from the RDW balance of {hk(point.get('drawn_hkd'))}.")
    subhead(document, "Liquidity and capital")
    add_paragraph(document, f"Liquidity for debt service is the question for {nice_date(point.get('next_due_date'))}, when {hk(point.get('next_due_hkd'))} falls due.")
    subhead(document, "Earlier years, for the comparison.")
    add_table(document, ["", "Earlier", "Prior", "Latest"], [
        ["Revenue", cell(revenue[0]), cell(revenue[1]), cell(revenue[2])],
        ["Interest cover", cell(cover[0], "num"), cell(cover[1], "num"), cell(cover[2], "num")],
        ["Leverage", cell(leverage[0], "num"), cell(leverage[1], "num"), cell(leverage[2], "num")],
        ["Drawn", hk(first.get("drawn_hkd")), hk(first.get("drawn_hkd")), hk(point.get("drawn_hkd"))],
        ["ECL", hk(first.get("ecl_hkd")), hk(point.get("prior_ecl_hkd")), hk(point.get("ecl_hkd"))],
        ["Collateral", hk(first.get("collateral_hkd")), hk(point.get("collateral_hkd")), hk(point.get("collateral_hkd"))],
        ["Grade", grade_label(first), grade, grade],
        ["Stage", str(first.get("stage")), str(point.get("stage")), str(point.get("stage"))],
        ["Days past due", str(first.get("dpd")), str(point.get("dpd")), str(point.get("dpd"))],
    ])
    subhead(document, "C4 : Net worth of the guarantor")
    add_paragraph(document, f"No separate guarantor net-worth statement. The extract line is: {guarantor}.")
    subhead(document, "C5 : Relationship with the Bank")
    add_paragraph(document, f"The relationship is managed by {person(customer)} and is reviewed at {as_of}. On-balance facilities: {len(facilities)}.")
    subhead(document, "C6 : Warning signals and market news")
    add_paragraph(document, (
        f"Market news specific to {name} is not copied from another obligor. "
        f"Collateral districts on this extract are used in the monitoring report. "
        f"Confirmed news, when accepted on the news page, is summarised in section 7 of that report, and the actions under section 9."
    ))
    subhead(document, "C7 : Country risk")
    add_paragraph(document, f"Same reading as section B7. Jurisdiction: {customer.get('jurisdiction') or 'not stated'}.")
    subhead(document, "C8 : ESG and climate")
    add_paragraph(document, f"No environmental enforcement record is on the collateral extract. Collateral type: {customer.get('collateral_type') or 'not stated'}.")
    subhead(document, "C9 : Tax risk")
    add_paragraph(document, "No tax dispute is recorded on the extract.")
    heading(document, "D. Particulars, ownership and credit checking")
    subhead(document, f"D1.1 : Particulars of the borrower — {name}")
    add_table(document, ["Item", "Details"], [
        ["Borrower", name],
        ["Customer id", customer["customer_id"]],
        ["Industry", industry],
        ["Jurisdiction", customer.get("jurisdiction") or "not stated"],
        ["Grade", grade],
        ["Stage", str(point.get("stage"))],
        ["Days past due", str(point.get("dpd"))],
        ["Drawn", hk(point.get("drawn_hkd"))],
        ["ECL", hk(point.get("ecl_hkd"))],
    ])
    subhead(document, f"D1.2 : Particulars of the guarantor — {guarantor}")
    add_table(document, ["Item", "Details"], [
        ["Guarantor", guarantor],
        ["Borrower supported", name],
        ["Collateral type", customer.get("collateral_type") or "not stated"],
        ["Coverage", multiple(point.get("coverage_ratio"))],
        ["LTV", ratio_pct(point.get("ltv"))],
        ["Pledge of deposits", "Not on the extract. Not assumed."],
        ["Next obligation", f"{hk(point.get('next_due_hkd'))} on {nice_date(point.get('next_due_date'))}"],
        ["Grade supported", grade],
    ])
    subhead(document, "D1.3 : Ownership")
    add_paragraph(document, "Shareholding percentages are not on the RDW extract, so none are stated.")
    add_table(document, ["Entity", "Role", "Holding"], [
        [name, "Borrower", "Obligor on the extract"],
        [guarantor, "Guarantor line", "As written on the extract"],
        [person(customer), "Relationship manager", "Bank"],
        [customer.get("group_name") or name, "Group name", "Extract"],
        [industry, "Industry", "Extract"],
        [grade, "Grade", "Maintained in this paper"],
        [customer.get("collateral_type") or "Collateral", "Security", hk(point.get("collateral_hkd"))],
        ["On-balance facilities", str(len(facilities)), hk(point.get("drawn_hkd"))],
        ["ECL", "Allowance", hk(point.get("ecl_hkd"))],
        ["Review", as_of, "Annual"],
    ])
    subhead(document, "D2.1 : Credit checking")
    add_table(document, ["Check", "Result"], [
        ["Grade", grade],
        ["Stage", str(point.get("stage"))],
        ["Days past due", str(point.get("dpd"))],
        ["LTV", ratio_pct(point.get("ltv"))],
        ["Classification", classification(point)],
    ])
    heading(document, "E. General information")
    subhead(document, "E1 : Group exposure table")
    add_paragraph(document, f"Group exposure in this paper is the borrower exposure of {hk(point.get('drawn_hkd'))}. See section B5. Other obligors are not added.")
    subhead(document, "E2 : Terms and conditions")
    add_table(document, ["Term", "Position proposed"], [
        ["Facility", "Existing, no increase"],
        ["Borrower", name],
        ["Amount discussed", hk(point.get("drawn_hkd"))],
        ["Committed", hk(point.get("committed_hkd"))],
        ["ECL", hk(point.get("ecl_hkd"))],
        ["Grade", grade],
        ["Tenor", nice_date(point.get("next_due_date"))],
        ["Security", customer.get("collateral_type") or "as on the collateral rows"],
        ["Collateral value", hk(point.get("collateral_hkd"))],
        ["LTV", ratio_pct(point.get("ltv"))],
        ["Guarantor", guarantor],
        ["Margin", "Not restated. Coupon is not on the RDW row."],
        ["Review", "Annual"],
        ["New money", "None"],
        ["Deposits", "Not on the extract. Not security."],
        ["News actions", "Monitoring report, section 7 summary and section 9 summary"],
    ])
    subhead(document, "E3 : Account performance")
    add_paragraph(document, f"Performance on the latest extract is stage {point.get('stage')} and {point.get('dpd')} days past due.")
    add_table(document, ["Item", "Status"], [
        ["Stage", str(point.get("stage"))],
        ["Days past due", str(point.get("dpd"))],
        ["ECL", hk(point.get("ecl_hkd"))],
        ["Next obligation", f"{hk(point.get('next_due_hkd'))} on {nice_date(point.get('next_due_date'))}"],
        ["Grade", grade],
        ["Collateral", hk(point.get("collateral_hkd"))],
    ])
    subhead(document, "E4 : Site visit / call report")
    add_paragraph(document, f"Not attached. {rm_phrase(customer, leading=True)} is to complete the next call note before {nice_date(point.get('next_due_date'))}.")
    subhead(document, "E5 : Checklists")
    add_table(document, ["Checklist", "Status on this paper"], [
        ["Annual review", "This paper"],
        ["Facility maintained", hk(point.get("drawn_hkd"))],
        ["Grade", grade],
        ["Security described", hk(point.get("collateral_hkd"))],
        ["Maturity described", nice_date(point.get("next_due_date"))],
        ["No new money", "Yes"],
        ["Figures sourced from this obligor's extract", "Yes"],
    ])
    heading(document, "Recommendation to Credit Committee")
    add_paragraph(document, (
        f"Approve the annual review of {name} on the terms in section E2, with {decision}. "
        f"Maintain grade {grade}. Drawn {hk(point.get('drawn_hkd'))}, collateral {hk(point.get('collateral_hkd'))}, "
        f"ECL {hk(point.get('ecl_hkd'))}. Do not treat a deposit the extract does not record as a covenant remedy."
    ))


def build_proposal(customer: dict, point: dict) -> Document:
    """Annual-review proposal using this obligor's RDW, ECL and collateral rows."""
    document = Document()
    blank(document)
    if customer.get("customer_id") == APEX_ID:
        return Document(str(APEX_PROPOSAL))
    write_proposal(document, customer, point)
    extend_with_extract(document, customer, point, words(Document(str(APEX_PROPOSAL))))
    return document


def save_proposal(customer: dict, point: dict, path: Path) -> None:
    if customer.get("customer_id") == APEX_ID:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    build_proposal(customer, point).save(path)


def publish(customer: dict, point: dict, folder: Path, *, write_proposal: bool) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    if write_proposal:
        save_proposal(customer, point, folder / "proposal.docx")
    save_monitoring(customer, point, [], folder / "report.docx")


def refresh_apex_base(source: Path) -> None:
    TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != TEMPLATE.resolve():
        shutil.copyfile(source, TEMPLATE)
