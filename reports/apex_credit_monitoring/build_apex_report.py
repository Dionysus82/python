"""Build the Apex Group annual-review proposal.

Input is the credit monitoring report (facility, security, conduct, maturity,
deposits and action plan) plus the organisation chart. The section order,
approval page and table style follow the source credit-proposal template.

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
OUT = ROOT / "Apex_Group_Annual_Review_Proposal.docx"
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
    tc_pr = cell._tc.get_or_add_tcPr()
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


def subhead(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(4)
    set_run(p.add_run(), text, bold=True, size=11, color=AMBER)
    return p


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


def build():
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Cm(1.6)
    section.bottom_margin = Cm(1.6)
    section.left_margin = Cm(1.6)
    section.right_margin = Cm(1.6)
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)

    kicker = doc.add_paragraph()
    set_run(kicker.add_run(), "SUBJECT CREDIT PROPOSAL", bold=True, size=9, color=NAVY)
    title = doc.add_paragraph()
    title.paragraph_format.space_after = Pt(2)
    set_run(title.add_run(), "Annual Review — Apex Group", bold=True, size=20, color=NAVY)
    sub = doc.add_paragraph()
    set_run(sub.add_run(), "Credit memo date 31 October 2026  ·  Reference FL/1158A", size=12, color=AMBER)
    para(
        doc,
        "Simulated annual review proposal prepared from the credit monitoring report and the organisation chart. Not a credit decision.",
        italic=True,
        size=9,
        color="666666",
    )

    heading(doc, "Proposal type")
    table(
        doc,
        ["Type", "Selected"],
        [
            ["New application", "No"],
            ["Limit increase", "No"],
            ["Annual renewal / review", "Yes"],
            ["Others", "Waiver of the 50% LTV covenant, and continuation of enhanced monitoring"],
        ],
    )

    heading(doc, "Signing section")
    table(
        doc,
        ["Role", "Name"],
        [
            ["Borrower", "Apex Global Holdings Limited (“Apex Global”)"],
            ["Guarantor", "Apex Property Limited (“Apex Property”), stock code 3768.HK"],
            ["Controller group", "Apex Group"],
            ["Worst PD of borrower group", "Pass-14"],
            ["Loan classification", "Pass"],
            ["Business unit", "Corporate Banking Department"],
            ["Division", "Wholesale Banking Division"],
            ["Prepared by", "Sophie Chan (RM Code: 01S9005) / Chole Lee"],
            ["Recommended by, Business Unit", "Harriet Wong"],
            ["Recommended by, Department Head", "Christine Wong"],
            ["Recommended by, Division Head", "Kelvin Au"],
            ["CRCD, Risk Control Section", "For assessment"],
            ["Credit Risk Management Department", "For review"],
            ["Credit Committee", "For approval"],
        ],
        [7.5, 10.0],
    )

    heading(doc, "Approval section")
    table(
        doc,
        ["Item", "Date"],
        [
            ["Facilities granted since", "December 2020"],
            ["This review due date", "31 October 2026"],
            ["Proposed next review due date", "31 October 2027"],
            ["Date of approval", "For Credit Committee"],
        ],
    )
    para(
        doc,
        "This paper seeks approval for the annual review, maintenance of the existing term loan, maintenance of "
        "borrower grade Pass-14, a waiver of the 50% loan-to-value covenant breach, continuation of the revised "
        "amortisation schedule, and continuation of enhanced monitoring. No new money is requested.",
    )

    heading(doc, "A. Facility section")
    subhead(doc, "Nature of proposal")
    para(
        doc,
        "Review and renewal of the existing secured term loan to Apex Global Holdings Limited. Outstanding exposure "
        "is HK$425.0 million. Clean exposure is nil. Pricing is unchanged at 4.3% p.a. over HIBOR. Final maturity "
        "is 30 September 2027. The corporate guarantor is Apex Property Limited. There is no personal guarantee and "
        "no derivative limit on this review.",
    )

    subhead(doc, "A1 : Facility overviews")
    table(
        doc,
        ["Borrower", "Type", "Committed", "Existing (HK$ m)", "Proposed (HK$ m)", "Change"],
        [
            ["Apex Global Holdings Limited", "Term loan", "Yes", "425.0", "425.0", "—"],
            ["Total", "", "", "425.0", "425.0", "—"],
        ],
    )
    table(
        doc,
        ["Item", "Position at 31 October 2026"],
        [
            ["Outstanding exposure", "HK$425.0 million"],
            ["Clean exposure", "Nil"],
            ["ECL", "HK$12.8 million"],
            ["Borrower grade", "Pass-14"],
            ["Loan classification", "Pass"],
            ["Interest", "HIBOR + 4.3%, about HK$2.3 million a month"],
            ["Final maturity", "30 September 2027"],
        ],
    )
    para(doc, "Repayment schedule, as amended at the previous review.", bold=True, space_after=4)
    table(
        doc,
        ["Due date", "Amount"],
        [
            ["Each month", "Interest at HIBOR + 4.3%"],
            ["30 December 2026", "Principal HK$25.0 million"],
            ["30 March 2027", "Principal HK$25.0 million"],
            ["30 June 2027", "Principal HK$25.0 million"],
            ["30 September 2027", "Principal HK$325.0 million"],
        ],
    )

    subhead(doc, "A2 : Deviation from guideline")
    table(
        doc,
        ["Item", "Position"],
        [
            ["Deviation", "Yes. LTV is 51.8% against a maximum covenant of 50%."],
            ["Risk assessment and justification", "Waiver is requested in A9. The breach comes from a lower valuation, not from missed interest. Coverage remains 1.93x and clean exposure is nil."],
        ],
    )

    subhead(doc, "A3 : Controller group exposure")
    table(
        doc,
        ["Item", "Existing", "Proposed"],
        [
            ["Ultimate controllers", "Metro Gov Authority A 90% and State Treasury Bureau B 10% of Apex Infrastructure Investment Corp.", "Unchanged"],
            ["Loan classification", "Pass", "No change"],
            ["Borrower exposure / (clean), HK$'000", "425,000 / (nil)", "425,000 / (nil)"],
            ["Group exposure / (clean), this Bank", "425,000 / (nil)", "425,000 / (nil)"],
            ["Related exposure outside the group", "Nil on this review", "Nil"],
            ["Under watch list", "Heightened monitoring at Pass-14. Not a classified loan.", "Unchanged"],
            ["Risky sector flag", "Commercial property. Monitored. Not a restricted sector on this paper.", "Unchanged"],
            ["Exposure within the controller cap", "To be confirmed by CRCD against prevailing tier 1 capital. This paper records secured exposure of HK$425 million and nil clean exposure.", "Unchanged"],
        ],
    )

    subhead(doc, "A4 : Facility details")
    para(doc, "Background", bold=True, space_after=4)
    para(
        doc,
        "The account was approved in 2020 as a secured term loan of HK$500 million, on a bullet repayment, when the "
        "property market was stable, occupancy was strong and LTV on charged property of HK$1,020 million was 49%, "
        "inside the 50% covenant. Security coverage at origination was 2.04x. Since then the Group has expanded with "
        "debt. Central Grade-A and Tsim Sha Tsui retail values have fallen. At the previous review the bullet was "
        "replaced with quarterly principal, because leverage and refinancing risk had risen. Outstanding is now "
        "HK$425.0 million. The account is still performing. Interest is current. There is no overdue record and no clean exposure.",
    )
    para(doc, "Purpose", bold=True, space_after=4)
    para(doc, "The term loan finances the Group's existing secured property exposure. This review does not add a new purpose or a new tranche.")
    para(doc, "Assessment of size, type, tenor and purpose", bold=True, space_after=4)
    para(
        doc,
        "Maintaining HK$425.0 million is justified as a renewal of the performing secured loan, not as new money. "
        "The outstanding is 51.8% of the latest charged value of HK$820.0 million, which is the point of the waiver, "
        "and 1.93x covered. The tenor runs to 30 September 2027 and now includes principal of HK$25 million in "
        "December 2026, March 2027 and June 2027, with HK$325 million at final maturity. That schedule is the "
        "response to refinancing risk. A derivative limit is not proposed.",
    )

    subhead(doc, "A5 : Security details and coverage")
    table(
        doc,
        ["Security", "Address", "Latest valuation"],
        [
            ["Grade-A office building, Central", "Apex Central Tower, Central, Hong Kong", "HK$620.0 million"],
            ["Retail shops, Tsim Sha Tsui", "Harbour Retail Plaza, Tsim Sha Tsui, Kowloon, Hong Kong", "HK$200.0 million"],
            ["Total collateral value", "", "HK$820.0 million"],
        ],
        [5.2, 8.2, 4.2],
    )
    table(
        doc,
        ["Item", "Amount"],
        [
            ["Outstanding exposure", "HK$425.0 million"],
            ["Collateral value", "HK$820.0 million"],
            ["Security coverage", "1.93x"],
            ["LTV", "51.8%"],
            ["LTV covenant", "50.0%"],
            ["Covenant status", "Breached"],
            ["Clean exposure", "Nil"],
            ["Prior-year collateral value", "HK$870.0 million"],
            ["Prior-year LTV", "About 48.9%"],
        ],
    )
    para(
        doc,
        "Charged value fell from HK$870.0 million to HK$820.0 million over the year, mainly with the Hong Kong office "
        "market. LTV therefore moved from about 48.9% to 51.8%. About 76% of charged value is the Central office. "
        "The Bank remains fully secured. The top-up clause remains: if LTV exceeds 50%, the borrower is to prepay or "
        "give additional security acceptable to the Bank so that LTV is not above the trigger. A waiver of the present "
        "breach is requested, together with a plan to restore compliance. On HK$820.0 million of collateral, debt of "
        "about HK$410.0 million would sit on the covenant, so about HK$15.0 million of reduction restores headroom if "
        "values do not fall further. After the breach the borrower placed HK$50.0 million on deposit. The deposit is "
        "not pledged, can be withdrawn, and is not counted for the covenant.",
    )

    subhead(doc, "A6 : Loan classification and internal rating")
    table(
        doc,
        ["Item", "Position"],
        [
            ["Borrower grade / Apex Global Holdings Limited", "Pass-14"],
            ["Guarantor", "Apex Property Limited, listed parent and corporate guarantor"],
            ["Loan classification", "Pass"],
            ["Change this review", "No downgrade. Pass-14 is maintained."],
            ["Override", "None requested"],
        ],
    )
    para(
        doc,
        "Pass-14 is the heightened performing grade. It is maintained because the LTV breach, the 2027 maturity "
        "cluster and the weaker leasing outlook are real, while interest is current and the loan is fully secured. "
        "The grade is not a classified exposure.",
    )

    subhead(doc, "A6.1 : Capital requirement")
    table(
        doc,
        ["Facility", "Exposure", "Treatment on this paper"],
        [["Term loan", "HK$425.0 million secured", "Standard secured weight. To be confirmed by CRCD on the live capital engine."]],
    )

    subhead(doc, "A6.2 : RORWA")
    para(
        doc,
        "Monthly interest is about HK$2.3 million, about HK$27.6 million a year, on HK$425.0 million outstanding. "
        "That is an indicative yield of about 6.5% before funding cost and before risk-weighted assets. A model RORWA "
        "is not produced in this simulated paper. Justification for a low RORWA is not required, because no exception "
        "to the pricing floor is requested. Pricing stays at HIBOR + 4.3%.",
    )

    subhead(doc, "A7 : Account performance")
    para(doc, "No payment irregularities were found. See section E3. The LTV covenant is the exception, and it is a valuation breach rather than a past-due item.")

    subhead(doc, "A8 : Actions from the previous approval")
    table(
        doc,
        ["Previous condition", "Status at this review"],
        [
            ["Replace the original bullet with quarterly principal through September 2027.", "In force. First principal of HK$25.0 million is due 30 December 2026 and is not yet due."],
            ["Monitor leasing of the charged properties.", "Office occupancy has moved from 89% to 83%. Average rents are down about 8%. Update is in section B2."],
            ["Follow the asset disposal plan and report any adversity.", "Two retail units were sold in 3Q2026 for net proceeds of HK$48.6 million, applied mainly to debt. Further assets of about HK$120.0 million are on the market. Progress is slower than planned."],
            ["Pursue refinancing of 2027 maturities.", "Indicative term sheets from two regional banks. No binding commitment at 31 October 2026."],
        ],
    )

    subhead(doc, "A9 : Credit commentary")
    para(doc, "1. Comments from Business Unit", bold=True, space_after=4)
    para(doc, "Credit strategy: Maintain.")
    para(doc, "Pros", bold=True, space_after=4)
    para(
        doc,
        "1. Fully secured, with nil clean exposure. Charged property is HK$820.0 million against HK$425.0 million, coverage 1.93x. The breach of the 50% covenant comes from the valuation, not from a failure to pay interest.",
    )
    para(
        doc,
        "2. Account conduct is satisfactory. Interest is up to date. Principal is not yet due. There is no past-due record and no excess.",
    )
    para(
        doc,
        "3. Listed parent support. Apex Property Limited (3768.HK) is the corporate guarantor and owns the borrower. Apex Infrastructure Investment Corp. holds 65% of Apex Property. Metro Gov Authority A and State Treasury Bureau B hold 90% and 10% of Apex Infrastructure.",
    )
    para(
        doc,
        "4. Deleveraging has started. Net proceeds of HK$48.6 million from two retail units in 3Q2026 were applied mainly to debt. A further HK$120.0 million is being marketed.",
    )
    para(
        doc,
        "5. Refinancing access is still open. Two regional banks have given indicative terms for 2027 maturities. The Bank is agent on the syndicated facility of HK$6,240 million maturing in December 2028.",
    )
    para(doc, "Cons", bold=True, space_after=4)
    para(
        doc,
        "1. LTV covenant breach. LTV is 51.8% against 50%. Collateral fell from HK$870.0 million to HK$820.0 million over the year. The unpledged HK$50.0 million deposit does not cure the covenant.",
    )
    para(
        doc,
        "2. Maturity concentration in 2027. Group debt is HK$7,175.0 million. HK$830.0 million, 11.6%, matures in 2027, including the Bank's HK$400.0 million. A further HK$25.0 million of our loan matures in December 2026. Other lenders account for HK$430.0 million of the 2026–2027 window. HK$6,320.0 million, 88.1%, matures in 2028 and beyond, mostly the syndicated facility.",
    )
    para(
        doc,
        "3. Weaker leasing. FY2026 revenue is expected to fall by about 12% year on year. Office occupancy has fallen from 89% to 83%. Average rents are down about 8%.",
    )
    para(
        doc,
        "4. Execution risk. The remaining disposals are slower than planned. The two refinancing discussions are not binding. Central Grade-A values are still under pressure, and that building is about 76% of our collateral.",
    )
    para(doc, "Risk mitigation", bold=True, space_after=4)
    para(
        doc,
        "The grade stays Pass-14 and the classification stays Pass. The loan is fully secured, clean exposure is nil, "
        "and interest has been paid on time. The original bullet has already been replaced with quarterly principal, "
        "which cuts the amount left for final maturity. Disposal proceeds are to be applied to debt. About HK$15.0 million "
        "of reduction would restore the 50% covenant at the present valuation. Enhanced monitoring covers the December 2026 "
        "instalment, the 2027 refinancing timetable and the disposal programme. The relationship manager will continue to "
        "ask for the HK$50.0 million deposit to be pledged. Support is the corporate guarantee of Apex Property Limited. "
        "It is not treated as an unlimited shareholder guarantee. " + CLOSE,
    )
    para(doc, "Recommendation", bold=True, space_after=4)
    para(doc, "We recommend that Credit Committee approve:")
    for line in [
        "the annual review;",
        "maintenance of the term loan at HK$425.0 million, priced at HIBOR + 4.3%;",
        "maintenance of borrower grade Pass-14 and loan classification Pass;",
        "a waiver of the 50% LTV covenant breach, limited to that covenant;",
        "continuation of the amortisation schedule through 30 September 2027;",
        "application of disposal proceeds to debt reduction;",
        "enhanced monitoring of refinancing and disposals; and",
        "continued engagement on a pledge of the HK$50.0 million deposit.",
    ]:
        para(doc, "•  " + line, space_after=2)
    para(
        doc,
        "While the account remains fully secured and supported by satisfactory account conduct, the key concerns are "
        "the continuing breach of the 50% LTV covenant, the debt maturing in 2027 and the borrower's reluctance to "
        "pledge the HK$50.0 million deposit. " + CLOSE,
    )
    para(doc, "2. Comments from Department Head", bold=True, space_after=2)
    para(doc, "For Christine Wong.", italic=True)
    para(doc, "3. Comments from CRCD (Risk Control Section)", bold=True, space_after=2)
    para(doc, "All sections in this proposal have been filled in: Yes. Matters for attention: LTV waiver, December 2026 principal, unpledged deposit, and the absence of a binding refinancing commitment.")
    para(doc, "4. Comments from Division Head", bold=True, space_after=2)
    para(doc, "For Kelvin Au.", italic=True)

    heading(doc, "B. Borrower section")
    para(
        doc,
        "Apex Global Holdings Limited is the Hong Kong borrower and a property holding company. It is wholly owned by "
        "Apex Property Limited. Credit judgement also rests on the guarantor and on the charged portfolio, because the "
        "monitoring report measures risk at group level.",
    )
    subhead(doc, "B1 : Company background")
    para(doc, "See section C1 and section D1.3. The borrower is the Hong Kong operating subsidiary at the bottom of the chart. It is not itself the listed company.")
    subhead(doc, "B2 : Business operation")
    para(
        doc,
        "Trading, manufacturing and retail operations are not the business. Income is rent from commercial property. "
        "Management advises that FY2026 revenue is expected to decline by about 12% year on year on weaker leasing "
        "demand and negative rental reversion. Office occupancy has fallen from 89% to 83%. Average rental rates have "
        "fallen by about 8%. Two retail units were sold in 3Q2026. Further properties of about HK$120.0 million are "
        "being marketed, more slowly than planned.",
    )
    subhead(doc, "B3 : Financial analysis — Apex Global Holdings Limited")
    para(
        doc,
        "The monitoring report does not attach a standalone audit of the borrower. The measurable position of the "
        "borrower on this paper is the secured loan and the charged property.",
    )
    table(
        doc,
        ["Item", "31 October 2026"],
        [
            ["Charged investment property, Bank valuation", "HK$820.0 million"],
            ["Term loan outstanding to this Bank", "HK$425.0 million"],
            ["LTV on charged property", "51.8%"],
            ["Clean bank debt of the borrower", "Nil, as informed for this review"],
            ["Other bank loans of the borrower", "Nil on the borrower's own name. Group debt is in section B5."],
        ],
    )
    para(
        doc,
        "Interest of about HK$2.3 million a month has been paid on time. The first principal instalment is not yet due. "
        "Standalone profitability of the SPV is not re-forecast here. The group outlook in section C3 is the one used "
        "for the revenue and occupancy comments above.",
    )
    subhead(doc, "B4 : Net worth of the borrower")
    para(doc, "Not separately stated in the monitoring report. Tangible support relied on in this paper is the charged property of HK$820.0 million and the corporate guarantee.")
    subhead(doc, "B5 : Relationship with other banks")
    para(doc, "The borrower has nil bilateral loans with other banks. Group debt, of which our HK$425.0 million is a part, is as follows.")
    table(
        doc,
        ["Creditor", "Facility", "Outstanding", "Maturity"],
        [
            ["Our Bank", "Term loan", "HK$25.0 million", "Dec 2026"],
            ["Our Bank", "Term loan", "HK$400.0 million", "2027"],
            ["Bank X", "Secured term loan", "HK$280.0 million", "Jun 2027"],
            ["Bank Y", "Revolving facility", "HK$150.0 million", "Dec 2027"],
            ["Bank Z", "Working capital facility", "HK$80.0 million", "Mar 2028"],
            ["10 syndicated lenders. Agent: our Bank", "Syndicated facility", "HK$6,240 million", "Dec 2028"],
            ["Total debt", "", "HK$7,175.0 million", ""],
        ],
    )
    table(
        doc,
        ["Year", "Amount", "Share of total debt"],
        [
            ["2026", "HK$25.0 million", "0.0%"],
            ["2027", "HK$830.0 million", "11.6%"],
            ["2028 and beyond", "HK$6,320.0 million", "88.1%"],
            ["Total", "HK$7,175.0 million", "100%"],
        ],
    )
    para(
        doc,
        "The 2027 bucket is HK$830.0 million, not the majority of the debt. The majority, 88.1%, matures in 2028, "
        "almost all of it the syndicated facility. The refinancing risk for this review is the nearer window: our "
        "HK$425.0 million plus HK$430.0 million of other lenders through 2027. The December 2026 instalment of "
        "HK$25.0 million is the first test.",
    )
    subhead(doc, "B6 : Warning signals / adverse news of the borrower")
    table(
        doc,
        ["Signal", "Yes / No"],
        [
            ["Change or resignation of auditor", "No, not reported"],
            ["Auditor refuses to sign or results are delayed", "No, not reported"],
            ["Qualified audit opinion", "Not stated in the monitoring report"],
            ["Change of directors or senior management", "No, not reported"],
            ["Failure to raise funds or refinance", "No failure yet. Discussions are open and not binding."],
            ["Abnormal share price or suspension", "Not applicable. The borrower is not listed."],
            ["Downgrade in the borrower's own credit rating", "Not applicable. Pass-14 is an internal grade and is maintained."],
            ["Merger or acquisition", "No, not reported"],
            ["Investigation by a regulator or law enforcement", "No, not reported"],
            ["Significant outstanding litigation", "No, not reported"],
            ["Other irregularity with a credit impact", "Yes. The 50% LTV covenant is breached."],
            ["Suspicious transaction / money laundering", "No, not reported"],
            ["Other adverse news", "Yes. Hong Kong office values remain under pressure. See section C6."],
        ],
    )
    subhead(doc, "B7 : Country risk")
    table(
        doc,
        ["Item", "Position"],
        [
            ["Country of operation", "Hong Kong"],
            ["Watch-list / restricted", "No"],
            ["Country risk scoring", "35, as for a Hong Kong operating company on the proposal template"],
            ["Country risk provision rate", "0"],
            ["Country limit", "Not applicable to this domestic exposure"],
        ],
    )
    subhead(doc, "B8 : ESG and climate risk")
    para(doc, "See section C8. The borrower holds commercial property in Hong Kong. No separate ESG incident is in the monitoring report.")
    subhead(doc, "B9 : Tax risk")
    para(doc, "See section C9.")
    subhead(doc, "B10 : Prevailing risk")
    para(doc, "The prevailing risks are the LTV breach, the 2027 refinancing window and the weaker leasing market. They are assessed above. They are not recorded as a second, unnamed prevailing risk.")
    subhead(doc, "B11 : Site visit / call report")
    para(doc, "No call report was attached to the credit monitoring report. The relationship manager is to place the next call note on file before the December 2026 instalment. See section E4.")

    heading(doc, "C. Guarantor section")
    subhead(doc, "C1 : Company background")
    para(
        doc,
        "Apex Property Limited is the operating company and the corporate guarantor. It is listed, stock code 3768.HK, "
        "and it owns 100% of Apex Global Holdings Limited. Apex Infrastructure Investment Corp. is the major shareholder, "
        "with 65%. The other shareholders are the public float 15.0%, Provincial Capital Holdings 6.0%, Industrial "
        "Development Investment Corp. 5.5%, Global Property Investment Holdings Ltd. 4.5% and Municipal Asset Mgmt Holdings 4.0%. "
        "Apex Infrastructure is held 90% by Metro Gov Authority A and 10% by State Treasury Bureau B.",
    )
    if CHART.exists():
        doc.add_picture(str(CHART), width=Inches(6.3))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    subhead(doc, "C2 : Business operation")
    para(
        doc,
        "The guarantor is a commercial property investor. The charged assets on our loan are a Central Grade-A office "
        "and Tsim Sha Tsui retail. Leasing demand is weaker. Occupancy of the office portfolio is 83%, from 89%. "
        "Rents are down about 8%. Management still expects the core book to produce rent, and the FY2026 revenue "
        "decline of about 12% is the planning case used in this review. Disposal of non-core retail units is the "
        "deleveraging tool.",
    )
    subhead(doc, "C3 : Financial analysis — Apex Property Limited, consolidated")
    para(
        doc,
        "The monitoring report states the FY2026 operating outlook and does not attach a three-year audit pack. "
        "The figures below complete the proposal's financial table. FY2024 and FY2025 are the simulated base against "
        "which the report's expected 12% revenue decline is applied. HK$ million.",
    )
    table(
        doc,
        ["", "FY2026 expected", "Change", "FY2025", "FY2024"],
        [
            ["Revenue", "1,003", "-12.0%", "1,140", "1,180"],
            ["EBITDA", "560", "-13.8%", "650", "670"],
            ["Net profit", "70", "-26.3%", "95", "110"],
            ["Total assets", "11,500", "-3.4%", "11,900", "12,400"],
            ["Shareholders' funds", "3,800", "-2.1%", "3,880", "3,950"],
            ["Interest-bearing debt", "7,100", "-1.0%", "7,175", "7,350"],
            ["Net gearing", "1.9x", "", "1.8x", "1.9x"],
            ["Interest coverage", "2.0x", "", "2.2x", "2.3x"],
            ["Occupancy", "83%", "", "86%", "87%"],
        ],
    )
    para(doc, "Profitability", bold=True, space_after=4)
    para(
        doc,
        "Revenue in the expected FY2026 column is 12% below FY2025, which is the figure given in the monitoring report. "
        "The decline is leasing and rental reversion, not a stoppage of rent. EBITDA is carried down with revenue. "
        "Net profit falls by more than EBITDA because softer valuations sit below EBITDA. Interest cover in the "
        "expected year is about 2.0x, at the covenant floor. FY2025 cover of 2.2x is inside the 2.0x minimum.",
    )
    para(doc, "Liquidity and capital", bold=True, space_after=4)
    para(
        doc,
        "Deposits with this Bank are HK$96.0 million, of which HK$50.0 million is the time deposit placed after the "
        "covenant breach and HK$46.0 million is in operating accounts. Group debt of HK$7,175 million at FY2025 is "
        "the maturity table. A small reduction is shown in the expected column because HK$48.6 million of disposal "
        "proceeds has already been applied. Gearing stays high relative to the 1.1x net gearing at origination-era "
        "FY2019. That increase is the debt-funded expansion since 2020.",
    )
    para(doc, "Earlier years, for the origination comparison. HK$ million.", bold=True, space_after=4)
    table(
        doc,
        ["", "FY2017", "FY2018", "FY2019"],
        [
            ["Revenue", "780", "865", "950"],
            ["EBITDA", "520", "585", "650"],
            ["Net profit", "280", "330", "390"],
            ["Total assets", "5,850", "6,200", "6,750"],
            ["Shareholders' funds", "2,350", "2,580", "2,930"],
            ["Interest-bearing debt", "2,650", "2,850", "3,100"],
            ["Net gearing", "1.1x", "1.1x", "1.1x"],
            ["Interest coverage", "—", "—", "4.8x"],
            ["Occupancy", "—", "—", "92%"],
        ],
    )
    para(doc, "At origination the book was recurring rent, with interest cover of 4.8x and gearing of 1.1x. Rental collection was above 98%. Those years explain why the 2020 LTV of 49% was an acceptable approval. They are not the current position.")
    subhead(doc, "C4 : Net worth of the guarantor")
    para(doc, "Shareholders' funds in the table above. The monitoring report does not add a separate personal net-worth statement. There is no personal guarantor on this review.")
    subhead(doc, "C5 : Relationship with the Bank")
    para(
        doc,
        "The relationship dates from the 2020 approval. Conduct since then has been satisfactory on payment. "
        "The Bank is also agent on the HK$6,240 million syndicated facility maturing in December 2028. "
        "Deposits of HK$96.0 million are held with us. Total operating income is not restated in the monitoring report.",
    )
    subhead(doc, "C6 : Warning signals and market news")
    para(
        doc,
        "The Hong Kong office market remained under pressure through 2026, with elevated vacancy and weak leasing. "
        "Transactions in Central Grade-A buildings have been completed at discounts to older valuation benchmarks. "
        "Because about 76% of our collateral is that Central office, a further decline would tighten LTV again. "
        "No rating action on the borrower is recorded in the monitoring report. No litigation or regulatory investigation is recorded.",
    )
    subhead(doc, "C7 : Country risk")
    para(doc, "Same as section B7. Hong Kong. No cross-border transfer risk on this facility.")
    subhead(doc, "C8 : ESG and climate")
    para(
        doc,
        "The collateral is an occupied commercial building in Central and retail units in Tsim Sha Tsui. Physical and "
        "transition risk is the ordinary risk of Hong Kong commercial property, already reflected in the valuation. "
        "No environmental enforcement action is in the monitoring report. Climate risk does not, on this paper, change the grade.",
    )
    subhead(doc, "C9 : Tax risk")
    para(
        doc,
        "The borrower is a Hong Kong company. The guarantor is listed in Hong Kong under stock code 3768.HK. "
        "No tax dispute is reported. Financial statements of the listed company are subject to audit and to the exchange's disclosure rules.",
    )

    heading(doc, "D. Particulars, ownership and credit checking")
    subhead(doc, "D1.1 : Particulars of the borrower — Apex Global Holdings Limited")
    table(
        doc,
        ["Item", "Details"],
        [
            ["Type of company", "Private limited company"],
            ["Listing", "Not listed"],
            ["Country of incorporation", "Hong Kong"],
            ["Country of operation", "Hong Kong"],
            ["Ultimate transfer of risk", "Hong Kong"],
            ["Related party of the Bank", "No, on the information in this review"],
            ["External credit rating", "Not stated"],
            ["Industry", "Commercial property investment and development"],
            ["BR / CI / paid-up capital / registered address", "Not stated in the monitoring report. To be taken from the KYC file."],
        ],
    )
    subhead(doc, "D1.2 : Particulars of the guarantor — Apex Property Limited")
    table(
        doc,
        ["Item", "Details"],
        [
            ["Type of company", "Public limited company"],
            ["Exchange", "Hong Kong"],
            ["Stock code", "3768.HK"],
            ["Country of incorporation and operation", "Hong Kong"],
            ["Ultimate controllers", "Metro Gov Authority A and State Treasury Bureau B, through Apex Infrastructure Investment Corp."],
            ["External credit rating", "Not stated in the monitoring report"],
            ["Industry", "Commercial property investment and development"],
            ["BR / CI / paid-up capital / registered address", "Not stated in the monitoring report. To be taken from the KYC file."],
        ],
    )
    subhead(doc, "D1.3 : Ownership")
    table(
        doc,
        ["Entity", "Role", "Holding"],
        [
            ["Metro Gov Authority A", "Ultimate shareholder", "90% of Apex Infrastructure"],
            ["State Treasury Bureau B", "Ultimate shareholder", "10% of Apex Infrastructure"],
            ["Apex Infrastructure Investment Corp.", "Holding company", "65% of Apex Property"],
            ["Public float", "Shareholder of Apex Property", "15.0%"],
            ["Provincial Capital Holdings", "Shareholder of Apex Property", "6.0%"],
            ["Industrial Development Investment Corp.", "Shareholder of Apex Property", "5.5%"],
            ["Global Property Investment Holdings Ltd.", "Shareholder of Apex Property", "4.5%"],
            ["Municipal Asset Mgmt Holdings", "Shareholder of Apex Property", "4.0%"],
            ["Apex Property Limited", "Guarantor", "100% of the borrower"],
            ["Apex Global Holdings Limited", "Borrower", "—"],
        ],
    )
    subhead(doc, "D2.1 : Credit checking")
    table(
        doc,
        ["Check", "Result"],
        [
            ["Terrorist list", "To be refreshed by KYC. No hit is recorded in the monitoring report."],
            ["PEP and jurisdictions", "Ultimate shareholders are government-linked entities on the organisation chart. Treat as a PEP review item for KYC, not as an adverse credit event."],
            ["AML risk level", "Normal, pending the KYC refresh. CARA owner and dates are on the KYC file, not in the monitoring report."],
            ["Litigation", "None recorded in the monitoring report."],
            ["Building orders on the charged properties", "None recorded in the monitoring report."],
        ],
    )

    heading(doc, "E. General information")
    subhead(doc, "E1 : Group exposure table")
    para(doc, "See section B5. Our exposure is HK$425.0 million, fully secured, clean nil. Group interest-bearing debt is HK$7,175.0 million.")
    subhead(doc, "E2 : Terms and conditions")
    table(
        doc,
        ["Term", "Position proposed"],
        [
            ["Borrower", "Apex Global Holdings Limited"],
            ["Guarantor", "Apex Property Limited"],
            ["Personal guarantor", "None"],
            ["Facility", "HK$425.0 million term loan"],
            ["Pricing", "HIBOR + 4.3%"],
            ["Maturity", "30 September 2027"],
            ["Repayment", "Interest monthly. Principal HK$25 million on 30 Dec 2026, 30 Mar 2027 and 30 Jun 2027. HK$325 million on 30 Sep 2027."],
            ["Security", "First charge over the Central Grade-A office and the Tsim Sha Tsui retail, latest value HK$820.0 million."],
            ["LTV covenant", "Maximum 50%. Presently 51.8%. Waiver requested for the current breach only."],
            ["Interest cover", "Minimum 2.0x. FY2025 at 2.2x. Not waived."],
            ["Net worth, negative pledge, pari passu", "Remain in force. No breach is reported."],
            ["Disposal proceeds", "100% of net proceeds from charged or agreed disposal assets to be applied to prepayment, unless Credit Committee agrees otherwise. The HK$48.6 million already received is to remain applied to debt."],
            ["Top-up", "If LTV is above 50% after this waiver period, the borrower prepays or delivers additional security so that LTV is back to 50% or below."],
            ["Deposit", "The HK$50.0 million time deposit is to be pursued as a pledge. Until pledged, it is not security."],
            ["Information", "Monthly update on refinancing and on the disposal of the remaining HK$120.0 million. Updated valuation within six months."],
            ["Review", "Next review 31 October 2027, or earlier if the December 2026 principal is missed or a binding refinancing fails."],
        ],
    )
    subhead(doc, "E3 : Account performance")
    table(
        doc,
        ["Item", "Status"],
        [
            ["Interest servicing", "Up to date"],
            ["Principal", "Not yet due"],
            ["Past-due record", "Nil"],
            ["Excesses", "Nil"],
            ["LTV covenant", "Breached"],
            ["Early warning", "Pass-14, enhanced monitoring"],
        ],
    )
    para(doc, "No payment irregularity was observed in the review period. The covenant breach is recorded here so that it is not mistaken for a missed instalment.")
    subhead(doc, "E4 : Site visit / call report")
    para(doc, "Not attached to the monitoring report. Action: relationship manager to complete a call report before 30 December 2026, covering the source of the HK$25.0 million principal, the pledge request, and the status of the two refinancing term sheets.")
    subhead(doc, "E5 : Checklists")
    table(
        doc,
        ["Checklist", "Status on this simulated paper"],
        [
            ["E5.1 Compliance checklist", "Annual review, no new money. Waiver is disclosed in A2 and A9."],
            ["E5.2 ESG and climate checklist", "Completed in C8. No grade impact."],
            ["E5.3 Assessment checklist", "Facility, security, conduct, group debt and guarantor are completed."],
            ["E5.4 KYC checklist", "Identifiers not in the monitoring report. KYC file to be attached before approval."],
            ["E5.5 Property lending mortgage checklist", "Two charged properties identified. Valuation date to be confirmed with the updated valuation due within six months."],
            ["E5.6 KYC template", "To be attached from the KYC file."],
            ["E5.7 Counterparty classification", "Corporate. Not a bank. Hong Kong."],
        ],
    )

    heading(doc, "Recommendation to Credit Committee")
    para(doc, "Approve the annual review on the terms in section E2.")
    para(doc, CLOSE)

    footer = section.footer.paragraphs[0]
    set_run(
        footer.add_run(),
        "Apex Group  ·  FL/1158A  ·  Annual review proposal at 31 October 2026  ·  Simulated, not a credit decision",
        size=8,
        color="888888",
    )
    doc.save(OUT)
    print(OUT)


if __name__ == "__main__":
    build()
