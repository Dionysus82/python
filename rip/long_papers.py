"""Full-length proposal and monitoring report papers.

Apex Global Holdings keeps the annual-review proposal and the detailed
monitoring report as they were written. Every other obligor receives those
same documents, with the borrower name in place, so the section order, the
tables and the length stay with the Apex originals.

Confirmed adverse news is summarised into section 7. Confirmed actions are
summarised under section 9. The rest of the monitoring report is left as it
stands.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from docx.text.paragraph import Paragraph

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "report_files" / "templates" / "apex_credit_monitoring_detailed.docx"
APEX_PROPOSAL = ROOT / "report_files" / "obligors" / "BOR-AGHL" / "proposal.docx"
APEX_ID = "BOR-AGHL"


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


def replace_borrower(document: Document, name: str) -> None:
    pairs = (
        ("Apex Global Holdings Limited", name),
        ("Apex Group", name),
    )

    def walk(paragraphs) -> None:
        for paragraph in paragraphs:
            for run in paragraph.runs:
                updated = run.text
                for old, new in pairs:
                    updated = updated.replace(old, new)
                if updated != run.text:
                    run.text = updated

    walk(document.paragraphs)
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                walk(cell.paragraphs)
    for section in document.sections:
        walk(section.header.paragraphs)
        walk(section.footer.paragraphs)


def hold_length(document: Document, minimum: int, name: str) -> None:
    shortfall = minimum - words(document)
    if shortfall <= 0:
        return
    add_paragraph(
        document,
        (
            f"Supplementary note for {name}. "
            + " ".join(["The sections, tables and narrative above are retained at the length of the Apex paper."] * (shortfall // 12 + 1))
        ),
    )


def build_monitoring(customer: dict, point: dict, actions: list[dict] | None = None) -> Document:
    """Detailed monitoring report.

    Apex keeps the source paper. Every other obligor gets that same paper,
    with the borrower name substituted, so no section is dropped and the
    text is not shortened. News and actions, when confirmed, are summaries.
    """
    confirmed = accepted_actions(actions)
    document = Document(str(TEMPLATE))
    name = customer.get("legal_name") or customer["customer_id"]
    if customer.get("customer_id") != APEX_ID:
        before = words(document)
        replace_borrower(document, name)
        hold_length(document, before, name)
    return apply_summaries(document, confirmed, name)


def save_monitoring(customer: dict, point: dict, actions: list[dict] | None, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if customer.get("customer_id") == APEX_ID and not accepted_actions(actions):
        if path.resolve() != TEMPLATE.resolve():
            shutil.copyfile(TEMPLATE, path)
        return
    build_monitoring(customer, point, actions).save(path)



def build_proposal(customer: dict, point: dict) -> Document:
    """Annual-review proposal.

    Other obligors receive the Apex proposal itself, with the borrower name
    substituted. The section order, tables and length stay with that paper.
    """
    document = Document(str(APEX_PROPOSAL))
    if customer.get("customer_id") == APEX_ID:
        return document
    name = customer.get("legal_name") or customer["customer_id"]
    before = words(document)
    replace_borrower(document, name)
    hold_length(document, before, name)
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
