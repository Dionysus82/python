# BEA Risk Intelligence — read this first

Port the live demo in `rip/`. Ignore `app/`, `site/`, and `synthetic_data/`. Those are earlier prototypes and a static export. They are not the product.

Synthetic demonstration only. Not for a credit, compliance, or business decision. Every mailbox is fake and ends in `@hkbea.example`. Do not put a real personal address anywhere.

## Run

```
cd rip
python3 serve.py
```

Open http://127.0.0.1:8766. Sign in with `cro.shum` / `Harbour-Demo-2026`. The server is the Python standard library. Rebuilding Word reports also needs `python-docx`. Rebuilding the news workbook needs `openpyxl`.

## Connect the agent here

This is the only integration point.

- Code: `rip/agent_slot.py`, function `ask()`.
- Caller: `rip/serve.py`, function `assistant_page()`. The screen is Agent portal, route `/assistant`.
- Until the endpoint exists, `ask()` returns `None` and the page uses the local answers in `answer_for()`.

Set these on the server. Do not write them into the repository.

- `RIP_AGENT_URL` — HTTPS endpoint Antigravity exposes for the Gemini agent built in Google Enterprise.
- `RIP_AGENT_KEY` — bearer token, only if that endpoint requires one.

`ask()` sends one JSON POST:

```json
{
  "question": "What are the key risks for this customer?",
  "as_of": "30 Nov 2026",
  "checked_dates": ["2025-12-31", "2026-11-30"],
  "borrower": {
    "customer_id": "BOR-AGHL",
    "legal_name": "Apex Global Holdings Limited",
    "industry": "Property Development",
    "rating": "14",
    "prior_rating": "13",
    "stage": 2,
    "drawn_hkd": 517465000,
    "ecl_hkd": 10731000,
    "dpd": 65,
    "collateral_type": "Commercial Property",
    "collateral_hkd": 788670000,
    "rm": "Chris Leung"
  }
}
```

Return JSON:

```json
{"answer": "...", "sources": [{"title": "", "locator": "", "passage": ""}]}
```

A missing URL, a failed call, or an empty `answer` keeps the local demonstration. The page says which one it used.

## Files an agent should open

| Path | Why |
| --- | --- |
| `rip/serve.py` | All screens, routes, and the mail rules. |
| `rip/agent_slot.py` | The agent hook above. |
| `rip/news_desk.py` | News file loader and saved severity edits. |
| `rip/book.json` | Portfolio, customers, facilities, drafts. Do not load the whole file into context. Query one customer. |
| `rip/property_data/apex_negative_news_v3.xlsx` | Live adverse-news source. It replaces `book.json` news at startup. |
| `rip/report_files/` | Internal report and proposal `.docx` files, plus `obligors.json`. |
| `reports/apex_credit_monitoring/build_apex_report.py` | Builder for the Apex 2025 annual-review proposal. |

`rip/build_property_book.py` and `rip/build_book.py` regenerate data. The running server does not need them.

## Screens

- `/` Portfolio. Own reporting-date checkboxes. Trend series has a separate month picker. Outstanding and ECL are in HKD million.
- `/industry` Industry review.
- `/financial` Financials and covenants.
- `/repayment` Title is **Repayment schedule**. Threshold defaults to HKD 5,000,000. One table only.
- `/news` Adverse news, split into obligor and industry. No date picker. Severity can be edited.
- `/reports` Internal report, and External report (HKEX search by borrower and year, no month picker).
- `/assistant` Agent portal. No date picker. This is where `ask()` is called.
- `/drafts` Email portal. No date picker. Sent is above Unsent Draft. Each row is collapsed until opened. Button **Send time, newest first** sorts the sent list.
- `/customer?id=` One borrower.

Each page keeps its own date cookie, except Agent portal and Email portal, which always use the full date range.

## Mail rules already in force

- News other than LOW is sent to the relationship manager. LOW is not sent.
- Apex group news without a direct customer link goes to Chris Leung (`BOR-AGHL`). Apex Infrastructure goes to Sophie Yip.
- A repayment of at least HKD 5,000,000 due within 92 days is sent to that borrower's RM.
- Addresses look like `chris.leung@hkbea.example`. Unlinked drafts use `credit.desk@hkbea.example`.
- The five composed drafts stay under Unsent Draft, except the large-repayment draft, which is now a sent notice.

## Apex annual review

Proposal type is a standard 2025 renewal. No new money. No covenant waiver and no property-valuation monitoring in the approval items. Net gearing is 1.85x (7,175 / 3,880). FY2025 EBITDA is HKD 770 million, finance cost HKD 350 million, interest cover 2.2x against a 2.0x covenant. Pass-14 is for leverage, a weaker market, and debt concentration, not a covenant breach.
