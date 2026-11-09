"""Simulated Apex Group credit monitoring report for review. Not loaded into the platform.

Requires python-docx. From the repository root:

    python3 reports/apex_credit_monitoring/build_apex_report.py
"""

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "Apex_Group_Credit_Monitoring_Report_31Oct2026.docx"
CHART = ROOT / "Org_Chart_for_Apex.jfif"
NAVY = "1F4E79"
AMBER = "8C3E16"
CLOSE = (
    "While the account's risk profile has deteriorated compared with the position at loan origination, "
    "the account remains performing, fully secured and supported by stable operating cash flow. "
    "Continued support is considered acceptable subject to enhanced monitoring and successful execution "
    "of the borrower's deleveraging and refinancing plans."
)


def shade(cell, hex_color):
    tc = cell._tePr if hasattr(cell, "_tePr") else cell._tc
    tc_pr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), hex_color)
    shd.set(qn("w:val"), "clear")
    tc_pr.append(shd)


def set_run(run, text, *, bold=False, size=10.5, color=None, italic=False):
    run.text = text
    run.bold = bold
    run.italic = italic
    run.font.size = Pt(size)
    run.font.name = "Calibri"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def para(doc, text, *, bold=False, size=10.5, space_after=8, italic=False, color=None):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.line_spacing = 1.08
    set_run(p.add_run(), text, bold=bold, size=size, italic=italic, color=color)
    return p


def heading(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(6)
    set_run(p.add_run(), text, bold=True, size=13, color=NAVY)
    return p


def assessment(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.line_spacing = 1.08
    set_run(p.add_run(), "Assessment. ", bold=True, size=10.5, italic=True, color=AMBER)
    set_run(p.add_run(), text, size=10.5)


def table(doc, headers, rows, widths=None):
    tbl = doc.add_table(rows=1 + len(rows), cols=len(headers))
    tbl.style = "Table Grid"
    tbl.autofit = True
    for i, header in enumerate(headers):
        cell = tbl.rows[0].cells[i]
        cell.text = ""
        shade(cell, NAVY)
        p = cell.paragraphs[0]
        set_run(p.add_run(), header, bold=True, size=9, color="FFFFFF")
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            cell = tbl.rows[r + 1].cells[c]
            cell.text = ""
            if r % 2 == 1:
                shade(cell, "F4F7FB")
            p = cell.paragraphs[0]
            last = r == len(rows) - 1 and str(row[0]).startswith("Total")
            set_run(p.add_run(), str(value), bold=last or c == 0, size=9)
    if widths:
        for row in tbl.rows:
            for cell, width in zip(row.cells, widths):
                cell.width = Cm(width)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return tbl


def build():
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Cm(1.6)
    section.bottom_margin = Cm(1.6)
    section.left_margin = Cm(1.7)
    section.right_margin = Cm(1.7)
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)

    kicker = doc.add_paragraph()
    kicker.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_run(kicker.add_run(), "CORPORATE BANKING  ·  ANNUAL REVIEW", bold=True, size=9, color=NAVY)
    title = doc.add_paragraph()
    title.paragraph_format.space_after = Pt(2)
    set_run(title.add_run(), "Apex Group Credit Monitoring Report", bold=True, size=20, color=NAVY)
    sub = doc.add_paragraph()
    sub.paragraph_format.space_after = Pt(2)
    set_run(sub.add_run(), "Detailed level  ·  Reporting date 31 October 2026", size=12, color=AMBER)
    para(
        doc,
        "Simulated report for internal review. It is not a credit, compliance or business decision.",
        italic=True,
        size=9,
        color="666666",
    )

    heading(doc, "Approval page")
    table(
        doc,
        ["Item", "Details"],
        [
            ["Nature of proposal", "Annual review. No new money."],
            ["Credit memo date", "31 October 2026"],
            ["Borrower", "Apex Global Holdings Limited (“Apex Global”)"],
            ["Guarantor", "Apex Property Limited (“Apex Property”), stock code 3768.HK"],
            ["Controller group", "Apex Group"],
            ["Worst borrower grade", "Pass-14"],
            ["Loan classification", "Pass"],
            ["Reference", "FL/1158A"],
            ["Business unit", "Corporate Banking Department"],
            ["Division", "Wholesale Banking Division"],
            ["Facilities granted since", "December 2020"],
            ["This review due", "October 2026"],
            ["Proposed next review", "31 October 2027"],
            ["Prepared by", "Sophie Chan (RM Code: 01S9005) / Chole Lee"],
            ["Recommended by (Business Unit)", "Harriet Wong"],
            ["Recommended by (Department Head)", "Christine Wong"],
            ["Recommended by (Division Head)", "Kelvin Au"],
            ["CRCD / Credit Risk Management", "For assessment and review"],
            ["Credit Committee", "For approval"],
        ],
        [7.2, 10.4],
    )
    para(
        doc,
        "This paper seeks approval for the annual review, maintenance of the existing facilities, "
        "maintenance of the borrower grade at Pass-14, a waiver of the 50% LTV covenant breach, "
        "continuation of the lending relationship and continuation of the enhanced monitoring requirements.",
    )

    heading(doc, "1. Facility information")
    table(
        doc,
        ["Item", "Details"],
        [
            ["Customer group", "Apex Group"],
            ["Borrower", "Apex Global Holdings Limited"],
            ["Industry", "Commercial property investment and development"],
            ["Outstanding exposure", "HK$425.0 million"],
            ["Clean exposure", "Nil"],
            ["ECL", "HK$12.8 million"],
            ["Borrower grade", "Pass-14"],
            ["Loan classification", "Pass"],
            ["Interest rate", "HIBOR + 4.3%"],
            ["Final maturity", "30 September 2027"],
        ],
    )
    para(doc, "Repayment schedule", bold=True, size=11, space_after=4)
    table(
        doc,
        ["Due date", "Amount"],
        [
            ["Monthly interest", "HIBOR + 4.3%, approximately HK$2.3 million"],
            ["30 December 2026", "Principal HK$25.0 million"],
            ["30 March 2027", "Principal HK$25.0 million"],
            ["30 June 2027", "Principal HK$25.0 million"],
            ["30 September 2027", "Principal HK$325.0 million"],
        ],
    )
    assessment(
        doc,
        "The facility was originally approved in 2020 as a secured term loan of HK$500 million on a bullet "
        "repayment. At the previous review the structure was amended, and quarterly principal repayments were "
        "introduced for the three-year extension, in response to higher leverage and refinancing risk. "
        "Repayment performance has remained satisfactory. There is no past-due record and interest has been "
        "serviced on time. The account is nonetheless on heightened watch, as reflected by Pass-14. "
        "The amortisation that starts in December 2026 is the near-term test of liquidity and of the "
        "borrower's deleveraging plan.",
    )

    heading(doc, "2. Group structure")
    para(
        doc,
        "The chart supplied with this review is the ownership chain used for this paper. Apex Global, the Hong Kong "
        "borrower, is wholly owned by the listed operating company. That company is the corporate guarantor.",
    )
    table(
        doc,
        ["Role", "Entity", "Holding"],
        [
            ["Ultimate shareholder", "Metro Gov Authority A", "90.0% of Apex Infrastructure"],
            ["Ultimate shareholder", "State Treasury Bureau B", "10.0% of Apex Infrastructure"],
            ["Holding company / major shareholder", "Apex Infrastructure Investment Corp.", "65.0% of Apex Property"],
            ["Operating entity and corporate guarantor", "Apex Property Limited (3768.HK)", "100% of the borrower"],
            ["Borrower, Hong Kong", "Apex Global Holdings Limited", "—"],
        ],
    )
    para(doc, "Other shareholders of Apex Property Limited", bold=True, size=11, space_after=4)
    table(
        doc,
        ["Shareholder", "Stake in Apex Property"],
        [
            ["Apex Infrastructure Investment Corp.", "65.0%"],
            ["Public float", "15.0%"],
            ["Provincial Capital Holdings", "6.0%"],
            ["Industrial Development Investment Corp.", "5.5%"],
            ["Global Property Investment Holdings Ltd.", "4.5%"],
            ["Municipal Asset Mgmt Holdings", "4.0%"],
            ["Total", "100%"],
        ],
    )
    doc.add_picture(str(CHART), width=Inches(6.4))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    assessment(
        doc,
        "Listed-parent support is Apex Property Limited. The majority of that company sits under Apex Infrastructure, "
        "which is held by Metro Gov Authority A and State Treasury Bureau B. Support is therefore from a listed "
        "property company with a government-linked holding company, not from a personal guarantee. "
        "The names and percentages above are taken from the organisation chart and replace the guarantor description "
        "in the earlier draft proposal.",
    )

    heading(doc, "3. Credit background since origination")
    table(
        doc,
        ["Position", "At approval in 2020", "At this review"],
        [
            ["Property market", "Stable", "Office and retail values lower"],
            ["Portfolio occupancy", "Strong, about 92%", "Above 80%; prime assets 92%–96%"],
            ["LTV on charged property", "49.0%", "51.8%"],
            ["LTV covenant", "Maximum 50%, inside", "Maximum 50%, breached"],
            ["Repayment", "Bullet at maturity", "Quarterly principal, then a residual"],
            ["Account conduct", "New facility", "Performing, no overdue"],
            ["Clean exposure", "Nil", "Nil"],
        ],
    )
    assessment(
        doc,
        "Since 2020 the Group has expanded through debt-funded acquisitions. Over the same period, Hong Kong office "
        "values weakened, Central Grade-A valuations declined and Tsim Sha Tsui retail valuations declined. "
        "Asset values softened, leverage rose and refinancing risk rose. The account is still performing. "
        "Interest is current, there is no overdue record, there is no clean exposure and the Bank remains fully secured. "
        "Operating performance is satisfactory against that market. The recommendation is to keep the account performing "
        "and under enhanced monitoring, rather than to change the grade.",
    )

    heading(doc, "4. Security position")
    para(doc, "Group investment portfolio, 2025", bold=True, size=11, space_after=4)
    table(
        doc,
        ["Property", "Type and location", "Valuation", "Occupancy"],
        [
            ["Apex Central Tower", "Grade-A office, Central", "HK$620 million", "96%"],
            ["Harbour Retail Plaza", "Prime retail, Tsim Sha Tsui", "HK$200 million", "95%"],
            ["Kowloon East Business Centre", "Office / commercial, Kowloon East", "HK$280 million", "92%"],
            ["Other commercial assets", "Retail units, car parks and strata", "HK$350 million", "Softer than the prime assets"],
            ["Total portfolio", "", "HK$1,650 million", "Above 80%"],
        ],
    )
    para(
        doc,
        "Major tenants in Apex Central Tower are international banks, law firms and professional services firms. "
        "A new anchor tenant has been signed for that tower.",
    )
    para(doc, "Charged to the Bank", bold=True, size=11, space_after=4)
    table(
        doc,
        ["", "2020 at origination", "Latest"],
        [
            ["Facility / outstanding", "HK$500 million approved", "HK$425.0 million outstanding"],
            ["Grade-A office, Central", "Part of the charged pool", "HK$620.0 million"],
            ["Retail shops, Tsim Sha Tsui", "Part of the charged pool", "HK$200.0 million"],
            ["Charged property value", "HK$1,020 million", "HK$820.0 million"],
            ["LTV", "49.0%", "51.8%"],
            ["LTV covenant", "Maximum 50.0%", "Maximum 50.0%"],
            ["Security coverage", "2.04x", "1.93x"],
            ["Clean exposure", "Nil", "Nil"],
            ["Covenant status", "Complied", "Breached"],
        ],
    )
    assessment(
        doc,
        "The 2020 approval sat inside the 50% LTV covenant, with charged property of HK$1,020 million against a "
        "HK$500 million facility. Charged value has since fallen. Over the latest year it moved from HK$870 million "
        "to HK$820 million, and LTV on the current outstanding of HK$425 million moved from about 48.9% to 51.8%. "
        "The breach comes from the valuation decline, not from a failure to service debt. Coverage of 1.93x still "
        "leaves the Bank fully secured, and the buffer against a further fall in values is thinner than at origination. "
        "After the 2025 breach the borrower placed HK$50 million of deposits with the Bank. The deposits are not pledged, "
        "can be withdrawn, and are not counted for covenant compliance.",
    )

    heading(doc, "5. Financial performance")
    para(
        doc,
        "Figures for FY2017 to FY2019 are the historical years specified for this review. FY2020 to FY2025 continue "
        "that series on the same basis: recurring rent, then debt-funded expansion, then softer valuations. "
        "The year-end used here is 31 March, consistent with the Group's reporting convention in the draft proposal. "
        "HK$ million.",
    )
    table(
        doc,
        ["", "FY17", "FY18", "FY19", "FY20", "FY21", "FY22", "FY23", "FY24", "FY25"],
        [
            ["Revenue", "780", "865", "950", "990", "1,080", "1,160", "1,220", "1,180", "1,140"],
            ["EBITDA", "520", "585", "650", "675", "710", "730", "700", "670", "650"],
            ["Net profit", "280", "330", "390", "355", "310", "240", "160", "110", "95"],
            ["Total assets", "5,850", "6,200", "6,750", "8,100", "9,600", "11,400", "12,800", "12,400", "11,900"],
            ["Shareholders' funds", "2,350", "2,580", "2,930", "3,200", "3,500", "3,850", "4,050", "3,950", "3,880"],
            ["Interest-bearing debt", "2,650", "2,850", "3,100", "3,900", "5,100", "6,300", "7,050", "7,350", "7,175"],
        ],
    )
    para(doc, "Credit metrics", bold=True, size=11, space_after=4)
    table(
        doc,
        ["Metric", "FY2019", "FY2022", "FY2024", "FY2025"],
        [
            ["Net gearing", "1.1x", "1.6x", "1.9x", "1.8x"],
            ["Interest coverage", "4.8x", "2.9x", "2.3x", "2.2x"],
            ["Occupancy", "92%", "89%", "87%", "86%"],
            ["Rental collection", "98%+", "98%", "97%", "97%"],
        ],
    )
    assessment(
        doc,
        "Up to origination the book was stable and improving, carried by recurring rent, with healthy liquidity and "
        "leverage that was conservative for the sector. From FY2020 the Group added assets with debt. Revenue and EBITDA "
        "kept growing into FY2023, then eased. Net profit fell faster than EBITDA because fair-value adjustments and "
        "higher interest cost sat below EBITDA. FY2025 interest cover of 2.2x is still above the 2.0x covenant. "
        "Net gearing has risen from 1.1x to 1.8x. Debt of HK$7,175 million at FY2025 matches the maturity table below. "
        "The Kowloon East disposal closed after that balance-sheet date, so its debt reduction is a latest development "
        "rather than a FY2025 year-end figure.",
    )

    heading(doc, "6. Maturity profile")
    para(doc, "Debt at origination, 2020", bold=True, size=11, space_after=4)
    table(
        doc,
        ["Creditor", "Outstanding"],
        [
            ["Bank A", "HK$800 million"],
            ["Bank B", "HK$650 million"],
            ["Bank C", "HK$550 million"],
            ["Syndicated facility", "HK$750 million"],
            ["Other facilities", "HK$350 million"],
            ["Total debt", "HK$3,100 million"],
        ],
    )
    para(
        doc,
        "At origination the creditor list was diversified. The debt was manageable against recurring cash flow and "
        "against interest cover of 4.8x.",
    )
    para(doc, "Group debt maturity profile, current", bold=True, size=11, space_after=4)
    table(
        doc,
        ["Creditor", "Facility type", "Outstanding", "Maturity"],
        [
            ["Our Bank", "Term loan", "HK$25.0 million", "Dec 2026"],
            ["Our Bank", "Term loan", "HK$400.0 million", "2027"],
            ["Bank X", "Secured term loan", "HK$280.0 million", "Jun 2027"],
            ["Bank Y", "Revolving facility", "HK$150.0 million", "Dec 2027"],
            ["Bank Z", "Working capital facility", "HK$80.0 million", "Mar 2028"],
            ["10 syndicated lenders", "Syndicated facility", "HK$6,240 million", "Dec 2028"],
            ["Total debt", "", "HK$7,175.0 million", ""],
        ],
    )
    para(doc, "The Bank is agent on the syndicated facility.", size=10)
    para(doc, "Debt maturity breakdown", bold=True, size=11, space_after=4)
    table(
        doc,
        ["Year", "Amount", "% of total debt"],
        [
            ["2026", "HK$25.0 million", "0.0%"],
            ["2027", "HK$830.0 million", "11.6%"],
            ["2028 and beyond", "HK$6,320.0 million", "88.1%"],
            ["Total", "HK$7,175.0 million", "100%"],
        ],
    )
    assessment(
        doc,
        "The amount due by the end of 2027 is HK$855 million, of which the Bank's own exposure is HK$425 million "
        "and other lenders account for HK$430 million. That is the refinancing window that matters for this review. "
        "The larger stock, 88.1%, matures in 2028, almost all of it the syndicated facility. "
        "Management intends to meet the nearer maturities from property disposals and refinancing. "
        "That plan is credible only if the December 2026 instalment of HK$25 million is paid from liquidity already "
        "in hand, and if the 2027 discussions with other banks become commitments. Market conditions for commercial "
        "property remain weak, so execution risk on the 2027 slice is the point to watch. The 2028 syndicated maturity "
        "is large, but it is not the near-term test.",
    )

    heading(doc, "7. Financial covenants")
    table(
        doc,
        ["Covenant", "Term", "Latest position"],
        [
            ["Maximum LTV", "50%", "51.8%. Breached."],
            ["Minimum interest coverage", "2.0x", "2.2x at FY2025. Inside."],
            ["Net worth", "Minimum shareholders' funds as agreed at origination", "HK$3,880 million. Monitored. No breach reported."],
            ["Negative pledge", "In force", "Complied on the information received"],
            ["Pari passu", "In force", "Complied on the information received"],
        ],
    )
    assessment(
        doc,
        "The covenant package at origination is the same package against which the 2025 LTV breach is measured. "
        "Interest cover has compressed from 4.8x to 2.2x and remains inside 2.0x. The waiver requested in this paper "
        "is limited to the LTV breach. It is not a waiver of the interest-cover, net-worth, negative-pledge or "
        "pari passu terms.",
    )

    heading(doc, "8. Latest development")
    para(doc, "Operating performance", bold=True, size=11, space_after=4)
    para(
        doc,
        "Management reports that occupancy remains above 80%. On the three principal assets it is 96%, 95% and 92%. "
        "Rental income is stable. Profit for 3Q2025/2026 is expected to decline by 2% to 5%, mainly from fair-value "
        "adjustments. Core rental operations remain healthy.",
    )
    para(doc, "Asset disposal", bold=True, size=11, space_after=4)
    para(
        doc,
        "The Group has announced an asset disposal programme of about HK$1.2 billion. Disposal of a Kowloon East "
        "property, separate from the Kowloon East Business Centre that remains in the retained portfolio, has completed "
        "at about HK$480 million. That price is approximately 17% below book value of about HK$578 million. "
        "Proceeds are being applied to debt reduction.",
    )
    para(doc, "Refinancing", bold=True, size=11, space_after=4)
    para(
        doc,
        "The borrower has indicative refinancing proposals from two regional banks for facilities maturing in 2027. "
        "Discussions continue. There is no binding commitment at the reporting date.",
    )
    assessment(
        doc,
        "The operating business is resilient. The open items are execution: completion of the rest of the disposal "
        "programme, application of proceeds to debt, and conversion of the two indicative refinancing proposals into "
        "commitments before the 2027 maturities. Both the disposal and the refinancing stay on the monitoring list.",
    )

    heading(doc, "9. Account conduct")
    table(
        doc,
        ["Item", "Status"],
        [
            ["Interest servicing", "Up to date"],
            ["Principal repayment", "Not yet due. First scheduled principal is 30 December 2026."],
            ["Past-due record", "Nil"],
            ["Excesses", "Nil"],
            ["LTV covenant", "Breached"],
        ],
    )
    assessment(
        doc,
        "Conduct over the review period is satisfactory. Contractual interest has been paid on schedule. "
        "The LTV covenant remains breached. Leaving HK$50 million on deposit, without a pledge, is not a remedy "
        "and gives only limited comfort.",
    )

    heading(doc, "10. Market news")
    para(doc, "Company", bold=True, size=11, space_after=4)
    table(
        doc,
        ["Item", "Status"],
        [
            ["Moody's", "Baa1 maintained on the listed parent. Outlook revised to Negative."],
            ["S&P", "BBB maintained on the listed parent. Outlook revised to Negative."],
            ["Near-term earnings", "3Q2025/2026 profit expected 2%–5% lower, mainly fair value."],
            ["Disposals", "HK$1.2 billion programme announced. Kowloon East tranche completed."],
            ["Leasing", "New anchor tenant signed at the Central flagship tower."],
        ],
    )
    para(doc, "Sector", bold=True, size=11, space_after=4)
    table(
        doc,
        ["Item", "Movement"],
        [
            ["Central Grade-A office prices", "Down about 15%–18%"],
            ["Tsim Sha Tsui retail prices", "Down about 12%–16%"],
            ["Commercial property transactions", "Volume modestly better in 2H2025/2026"],
            ["Refinancing for quality sponsors", "Still available"],
        ],
    )
    assessment(
        doc,
        "The fall in collateral value is explained first by the market, not by a vacancy crisis in the charged assets. "
        "Central office is about 76% of charged value (HK$620 million of HK$820 million), so a further decline in "
        "Central Grade-A prices would tighten LTV again. Underlying rent collection and occupancy on the prime assets "
        "are relatively stable, and the refinancing market has not closed for a sponsor of this quality.",
    )

    heading(doc, "11. Deposit balance")
    table(
        doc,
        ["Account type", "Balance"],
        [
            ["Operating accounts", "HK$46.0 million"],
            ["Time deposit", "HK$50.0 million"],
            ["Total deposits with the Bank", "HK$96.0 million"],
        ],
    )
    assessment(
        doc,
        "The HK$50 million time deposit was placed after the covenant breach and shows a wish to keep the relationship. "
        "It is not pledged. It is not enforceable credit support and it does not cure the LTV covenant. "
        "The unpledged deposit is a monitoring point, not a mitigant.",
    )

    heading(doc, "12. Strengths, concerns and risk mitigation")
    para(doc, "Strengths", bold=True, size=11, space_after=4)
    for line in [
        "Recurring rental income, with collection still around 97%.",
        "A diversified portfolio: Central office, Tsim Sha Tsui retail, Kowloon East and other commercial assets, valued at HK$1.65 billion.",
        "Listed parent, Apex Property Limited (3768.HK), majority-held through Apex Infrastructure by Metro Gov Authority A and State Treasury Bureau B.",
        "Occupancy on the principal assets at 92%–96%, and group occupancy still above 80%.",
        "Full collateral coverage of 1.93x and no clean exposure.",
        "Disposals already under way, with the Kowloon East tranche completed and proceeds directed to debt.",
        "Refinancing access still open: two regional banks have given indicative terms, and the Bank is agent on the syndicated facility.",
    ]:
        para(doc, "•  " + line, space_after=2)
    para(doc, "Concerns", bold=True, size=11, space_after=4)
    for line in [
        "LTV covenant breached at 51.8% against a 50% maximum.",
        "Leverage higher than at origination: net gearing 1.8x against 1.1x in FY2019, and group debt HK$7,175 million against HK$3,100 million in 2020.",
        "A concentrated maturity in 2027 of HK$830 million, before the much larger 2028 syndicated maturity.",
        "Pressure on commercial property valuations, in particular Central Grade-A office, which dominates the charged pool.",
        "The HK$50 million deposit remains unpledged.",
        "Rating outlooks on the listed parent are Negative at both Moody's and S&P, despite the ratings being maintained.",
        "The disposal programme and the refinancing discussions are not yet fully executed.",
    ]:
        para(doc, "•  " + line, space_after=2)
    para(doc, "Risk mitigation", bold=True, size=11, space_after=4)
    assessment(
        doc,
        "The grade remains Pass-14 and the classification remains Pass. Mitigants already in place are full security, "
        "nil clean exposure, interest cover still above 2.0x, and a repayment record with no arrears. "
        "The bullet structure has already been replaced with quarterly principal from December 2026, which reduces "
        "the refinancing lump at final maturity. Disposal proceeds are to be applied to debt, which is the direct "
        "route back toward the 50% LTV: on collateral of HK$820 million the covenant allows about HK$410 million, "
        "so a reduction of about HK$15 million from the HK$425 million outstanding would restore compliance if values "
        "do not fall further. Two banks are already in refinancing discussions. Enhanced monitoring covers the "
        "December 2026 instalment, the 2027 refinancing timetable and the remainder of the HK$1.2 billion disposal "
        "programme. The relationship manager will keep asking for the HK$50 million deposit to be pledged. "
        "Support from the listed parent is noted and is not treated as a guarantee beyond the corporate guarantee "
        "already given by Apex Property Limited. " + CLOSE,
    )

    heading(doc, "13. Account strategy and action plan")
    para(
        doc,
        "Strategy: covenant remediation and refinancing-risk management. The aim is to restore the 50% LTV covenant "
        "and to have the 2027 maturities funded before they fall due. Pass-14 remains the right grade until remediation "
        "and refinancing have moved from intention to evidence.",
        bold=False,
    )
    table(
        doc,
        ["Action", "Priority"],
        [
            ["Obtain a formal covenant remediation plan.", "High"],
            ["Require disposal proceeds, including the Kowloon East proceeds, to be applied to debt reduction.", "High"],
            ["Continue discussions to pledge the HK$50 million deposit.", "High"],
            ["Explore additional collateral and any further support from Apex Property Limited.", "High"],
            ["Obtain monthly updates on refinancing progress and on the HK$1.2 billion disposal programme.", "High"],
            ["Monitor the 30 December 2026 principal of HK$25 million.", "High"],
            ["Update the collateral valuation within six months.", "Medium"],
        ],
    )
    para(doc, "Relationship manager", bold=True, size=11, space_after=4)
    para(
        doc,
        "On collateral of HK$820.0 million, debt of about HK$410.0 million would sit on the 50% covenant. "
        "Outstanding of HK$425.0 million is about HK$15.0 million above that level. "
        "Sophie Chan will focus on applying disposal proceeds to that reduction, obtaining a written refinancing "
        "timetable from the borrower, identifying any additional collateral, and converting the HK$50.0 million "
        "deposit into a pledge or other enforceable security.",
    )

    heading(doc, "14. Recommendation")
    para(doc, "Credit has weakened since the 2020 approval. The LTV breach is mainly a valuation event. Repayment performance is satisfactory. There is no clean exposure. Security coverage remains adequate. Business performance remains acceptable. Debt maturities are manageable if the refinancing and disposal plans are executed.", space_after=6)
    para(doc, "Approval is recommended for the following.", bold=True, space_after=4)
    for line in [
        "The annual review.",
        "Continuation of the existing facilities, outstanding HK$425.0 million, at HIBOR + 4.3%.",
        "Maintenance of borrower grade Pass-14 and loan classification Pass.",
        "A waiver of the 50% LTV covenant breach, limited to that covenant.",
        "Continuation of the revised amortisation schedule through 30 September 2027.",
        "Application of disposal proceeds toward debt reduction.",
        "Enhanced monitoring of refinancing and of the disposal programme.",
        "Continued engagement on a pledge of the HK$50 million deposit.",
    ]:
        para(doc, "•  " + line, space_after=2)
    assessment(doc, CLOSE)

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_run(
        footer.add_run(),
        "Apex Group  ·  FL/1158A  ·  Simulated annual review at 31 October 2026  ·  Not a credit decision",
        size=8,
        color="888888",
    )
    doc.save(OUT)
    print(OUT)


if __name__ == "__main__":
    build()
