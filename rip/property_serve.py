"""Property portfolio screens fed by the collateral extract and cash flow tables."""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "property_data"
BANNER = (
    "SYNTHETIC HACKATHON DATA - NOT FOR CUSTOMER, CREDIT, COMPLIANCE, "
    "RISK, REGULATORY OR BUSINESS DECISION-MAKING"
)


def parse_date(text: str):
    return datetime.strptime(text.strip(), "%d/%m/%Y").date()


def money(value: float) -> str:
    return f"HKD {value:,.0f}"


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


COLLATERAL = load_rows(DATA / "COLLATERAL_ALL_2026.csv")
CASHFLOWS = load_rows(DATA / "CASH_FLOW_ALL_2026.csv")

BY_MONTH: dict[str, list[dict]] = defaultdict(list)
for row in COLLATERAL:
    BY_MONTH[row["REPORTING_DATE"]].append(row)
MONTHS = sorted(BY_MONTH, key=parse_date)

FLOWS: dict[tuple[str, str], list[dict]] = defaultdict(list)
TERMS: dict[tuple[str, str], dict] = {}
for row in CASHFLOWS:
    key = (row["REPORTING_DATE"], row["CONTRACT_REFERENCE"])
    FLOWS[key].append(row)
    TERMS.setdefault(key, row)
for rows in FLOWS.values():
    rows.sort(key=lambda item: parse_date(item["CASH_FLOW_DATE"]))


def facilities(asof: str) -> list[dict]:
    rows = []
    for source in BY_MONTH[asof]:
        key = (asof, source["CONTRACT_REFERENCE"])
        term = TERMS.get(key)
        flows = FLOWS.get(key, [])
        principal_dates = [item for item in flows if item["CASH_FLOW_TYPE"] == "N" and float(item["CASH_FLOW_AMOUNT"]) > 0]
        next_flow = flows[0] if flows else None
        maturity = flows[-1]["CASH_FLOW_DATE"] if flows else ""
        rows.append(
            {
                **source,
                "balance": float(source["BAL_OUTSTD_HKD"]),
                "market": float(source["MARKET_VALUE_HKD"]),
                "net": float(source["NET_REALIZABLE_VALUE_HKD"]),
                "ltv": float(source["LTV"]),
                "ltv_nrv": float(source["LTV_ON_NRV"]),
                "on_book": source["INSTRUMENT"] == "Customer Loan",
                "grade": term["CURRENT_PD_GRADE"] if term else "",
                "rate": float(term["DISCOUNT_RATE"]) if term else None,
                "method": term["AMORTIZATION_METHOD"] if term else "",
                "next_date": next_flow["CASH_FLOW_DATE"] if next_flow else "",
                "next_type": next_flow["CASH_FLOW_TYPE"] if next_flow else "",
                "next_amount": float(next_flow["CASH_FLOW_AMOUNT"]) if next_flow else 0,
                "maturity": maturity,
                "principal_due": sum(float(item["CASH_FLOW_AMOUNT"]) for item in principal_dates[:1]) if principal_dates else 0,
                "principal_date": principal_dates[0]["CASH_FLOW_DATE"] if principal_dates else "",
                "flows": flows,
            }
        )
    rows.sort(key=lambda item: item["balance"], reverse=True)
    return rows


def month_totals() -> list[tuple[str, float, float]]:
    series = []
    for asof in MONTHS:
        book = facilities(asof)
        loans = [row for row in book if row["on_book"]]
        series.append((asof, sum(row["balance"] for row in loans), sum(row["market"] for row in loans)))
    return series


SERIES = month_totals()


def page(title: str, active: str, body: str) -> bytes:
    nav = [
        ("dashboard", "Portfolio"),
        ("collateral", "Collateral"),
        ("cashflow", "Cash flows"),
    ]
    links = "".join(
        f'<a class="{"active" if key == active else ""}" href="/{key}">{escape(label)}</a>'
        for key, label in nav
    )
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<link href="https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600;700&family=Source+Serif+4:opsz,wght@8..60,560&display=swap" rel="stylesheet">
<style>
:root {{
  --orange:#E36F1E; --deep:#C45112; --red:#B42318; --wash:#F8E8E4;
  --ink:#2C2825; --title:#8C3E16; --muted:#6F6862; --line:#E4DDD6;
  --ground:#F3EFEA; --card:#FFFCF9; --rail:#3A342F;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:"Source Sans 3",sans-serif; color:var(--ink); background:var(--ground); }}
a {{ color:var(--deep); text-decoration:none; }}
.shell {{ display:grid; grid-template-columns:232px 1fr; min-height:100vh; }}
nav {{ background:var(--rail); color:#E7E0D8; padding:22px 16px; }}
nav .mark {{ font-family:"Source Serif 4",serif; color:#fff; font-size:1.25rem; }}
nav .mark span {{ color:var(--orange); }}
nav p {{ color:#C8BEB4; font-size:.78rem; line-height:1.4; }}
nav a {{ display:block; color:#E7E0D8; padding:9px 10px; border-left:3px solid transparent; border-radius:8px; margin:2px 0; }}
nav a.active {{ background:rgba(227,111,30,.18); color:#fff; border-left-color:var(--orange); }}
main {{ padding:28px 32px 64px; }}
.banner {{ background:var(--wash); color:var(--red); border-radius:10px; padding:10px 12px; font-size:.84rem; margin-bottom:16px; }}
h1 {{ font-family:"Source Serif 4",serif; color:var(--title); font-weight:560; margin:0 0 8px; }}
.lead {{ color:var(--muted); max-width:820px; line-height:1.5; }}
.metrics {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:16px 0; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }}
.metric {{ border-top:3px solid var(--orange); }}
.metric.alert {{ border-top-color:var(--red); }}
.label {{ font-size:.7rem; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); font-weight:700; }}
.value {{ font-size:1.35rem; font-weight:700; margin-top:6px; }}
.grid {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
table {{ width:100%; border-collapse:collapse; font-size:.92rem; }}
th {{ text-align:left; font-size:.68rem; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); padding:8px; border-bottom:1px solid var(--line); }}
td {{ padding:10px 8px; border-bottom:1px solid var(--line); vertical-align:top; }}
td.num, th.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
.bar {{ height:8px; background:#F7F4F0; border-radius:99px; overflow:hidden; }}
.bar span {{ display:block; height:100%; background:var(--orange); }}
.bar.hot span {{ background:var(--red); }}
select {{ font:inherit; padding:8px; border:1px solid var(--line); border-radius:8px; background:#fff; }}
.tag {{ display:inline-block; padding:2px 8px; border-radius:99px; font-size:.75rem; font-weight:700; }}
.tag-orange {{ background:#FDE8D4; color:var(--deep); }}
.tag-grey {{ background:#F7F4F0; color:var(--muted); border:1px solid var(--line); }}
@media (max-width:900px) {{
  .shell, .metrics, .grid {{ grid-template-columns:1fr; }}
}}
</style>
</head>
<body>
<div class="shell">
  <nav>
    <div class="mark">RIP <span>property</span></div>
    <p>Property portfolio, collateral and contractual cash flow. Twelve month-ends in 2026.</p>
    {links}
  </nav>
  <main>
    <div class="banner">{escape(BANNER)}</div>
    {body}
  </main>
</div>
</body>
</html>"""
    return html.encode("utf-8")


def bars(rows: list[tuple[str, float]], hot: bool = False) -> str:
    peak = max([value for _, value in rows] + [1])
    lines = []
    for label, value in rows:
        width = max(2, round(value / peak * 100))
        lines.append(
            '<div style="display:grid;grid-template-columns:minmax(180px,260px) 1fr 176px;gap:8px;align-items:center;margin:8px 0">'
            f"<div>{escape(label)}</div>"
            f'<div class="bar {"hot" if hot else ""}"><span style="width:{width}%"></span></div>'
            f'<div style="text-align:right;color:var(--muted);white-space:nowrap">{money(value)}</div></div>'
        )
    return "".join(lines)


def metric_cards(items: list[tuple[str, str, bool]]) -> str:
    cards = []
    for label, value, alert in items:
        cards.append(
            f'<div class="card metric {"alert" if alert else ""}"><div class="label">{escape(label)}</div><div class="value">{value}</div></div>'
        )
    return f'<div class="metrics">{"".join(cards)}</div>'


def month_picker(asof: str, path: str, extra: dict[str, str] | None = None) -> str:
    options = []
    for month in MONTHS:
        selected = "selected" if month == asof else ""
        options.append(f'<option value="{escape(month)}" {selected}>{escape(month)}</option>')
    hidden = ""
    for key, value in (extra or {}).items():
        hidden += f'<input type="hidden" name="{escape(key)}" value="{escape(value)}">'
    return (
        f'<form class="inline" method="get" action="{escape(path)}" style="margin:12px 0">'
        f"<label>Reporting date<br><select name=\"asof\" onchange=\"this.form.submit()\">{''.join(options)}</select></label>"
        f"{hidden}</form>"
    )


def chosen_month(query: dict) -> str:
    requested = (query.get("asof") or [MONTHS[-1]])[0]
    return requested if requested in BY_MONTH else MONTHS[-1]


def dashboard(asof: str) -> str:
    book = facilities(asof)
    loans = [row for row in book if row["on_book"]]
    off = [row for row in book if not row["on_book"]]
    outstanding = sum(row["balance"] for row in loans)
    market = sum(row["market"] for row in loans)
    all_market = sum(row["market"] for row in book)
    weighted = outstanding / market if market else 0
    by_borrower: dict[str, float] = defaultdict(float)
    by_type: dict[str, float] = defaultdict(float)
    by_method: dict[str, float] = defaultdict(float)
    for row in loans:
        by_borrower[row["BORROWER_NAME"]] += row["balance"]
        by_type[row["COLLATERAL_TYPE"]] += row["market"]
        by_method[(row["method"] or "No schedule").replace("_", " ").title()] += row["balance"]
    trend = [(month[3:5] + "/" + month[6:], balance) for month, balance, _market in SERIES]
    top = "".join(
        "<tr>"
        f'<td><a href="/contract?asof={escape(asof)}&ref={escape(row["CONTRACT_REFERENCE"])}">{escape(row["CONTRACT_REFERENCE"])}</a>'
        f'<div style="color:var(--muted);font-size:.8rem">{escape(row["BORROWER_NAME"])}</div></td>'
        f'<td>{escape(row["COLLATERAL_TYPE"])}</td>'
        f'<td class="num">{money(row["balance"])}</td>'
        f'<td class="num">{pct(row["ltv"])}</td>'
        f'<td>{escape(row["method"].replace("_", " ").title())}</td>'
        f'<td>{escape(row["maturity"])}</td>'
        "</tr>"
        for row in loans[:8]
    )
    return f"""
    <div class="label">Property portfolio</div>
    <h1>Management dashboard</h1>
    <p class="lead">Position {escape(asof)}. Outstanding, market value and LTV come from the collateral extract of the uploaded portfolio. Cash flow dates and grades come from the generated schedules. Off-balance facilities stay in the collateral book and have no contractual cash flow.</p>
    {month_picker(asof, "/dashboard")}
    {metric_cards([
        ("On-balance facilities", str(len(loans)), False),
        ("Outstanding", money(outstanding), False),
        ("Portfolio LTV", pct(weighted), weighted >= 0.6),
        ("Off-balance facilities", str(len(off)), False),
    ])}
    <div class="grid">
      <div class="card"><div class="label">Outstanding by borrower</div>{bars(sorted(by_borrower.items(), key=lambda item: item[1], reverse=True), hot=True)}</div>
      <div class="card"><div class="label">On-balance collateral by type</div>{bars(sorted(by_type.items()))}<p class="lead">Market value securing drawn balances is {money(market)}. Market value of every property, including off-balance facilities, is {money(all_market)}.</p></div>
      <div class="card"><div class="label">Outstanding by amortisation</div>{bars(sorted(by_method.items(), key=lambda item: item[1], reverse=True))}</div>
      <div class="card"><div class="label">On-balance outstanding through 2026</div>{bars(trend)}</div>
    </div>
    <div class="card" style="margin-top:12px">
      <div class="label">Largest on-balance names</div>
      <table>
        <thead><tr><th>Contract</th><th>Collateral</th><th class="num">Outstanding</th><th class="num">LTV</th><th>Schedule</th><th>Maturity</th></tr></thead>
        <tbody>{top}</tbody>
      </table>
    </div>
    """


def collateral_page(asof: str, district: str) -> str:
    book = facilities(asof)
    districts = sorted({row["DISTRICT"] for row in book})
    shown = [row for row in book if not district or row["DISTRICT"] == district]
    shown.sort(key=lambda row: row["market"], reverse=True)
    options = '<option value="">All districts</option>' + "".join(
        f'<option value="{escape(name)}" {"selected" if name == district else ""}>{escape(name)}</option>'
        for name in districts
    )
    body = "".join(
        "<tr>"
        f'<td><a href="/contract?asof={escape(asof)}&ref={escape(row["CONTRACT_REFERENCE"])}">{escape(row["COLLATERAL_REFERENCE"])}</a>'
        f'<div style="color:var(--muted);font-size:.8rem">{escape(row["PROPERTY_ADDRESS"])}</div></td>'
        f'<td>{escape(row["COLLATERAL_TYPE"])}<div style="color:var(--muted);font-size:.8rem">{escape(row["DISTRICT"])}</div></td>'
        f'<td>{escape(row["BORROWER_NAME"])}</td>'
        f'<td class="num">{money(row["market"])}</td>'
        f'<td class="num">{money(row["net"])}</td>'
        f'<td class="num">{pct(row["ltv"]) if row["on_book"] else "0.00%"}</td>'
        f'<td>{"1st"}</td>'
        "</tr>"
        for row in shown
    )
    return f"""
    <div class="label">Collateral</div>
    <h1>Properties securing the book</h1>
    <p class="lead">{len(shown)} properties at {escape(asof)}. Addresses stay with the collateral reference across the year. Charge rank is first. LTV uses outstanding divided by market value.</p>
    {month_picker(asof, "/collateral")}
    <form method="get" action="/collateral" style="margin-bottom:12px">
      <input type="hidden" name="asof" value="{escape(asof)}">
      <label>District<br><select name="district" onchange="this.form.submit()">{options}</select></label>
    </form>
    <div class="card">
      <table>
        <thead><tr><th>Collateral</th><th>Type</th><th>Borrower</th><th class="num">Market value</th><th class="num">Net realizable</th><th class="num">LTV</th><th>Rank</th></tr></thead>
        <tbody>{body}</tbody>
      </table>
    </div>
    """


def cashflow_page(asof: str) -> str:
    book = [row for row in facilities(asof) if row["flows"]]
    soon = []
    reporting = parse_date(asof)
    for row in book:
        for flow in row["flows"]:
            when = parse_date(flow["CASH_FLOW_DATE"])
            if (when - reporting).days <= 183:
                soon.append((when, row, flow))
    soon.sort(key=lambda item: (item[0], -item[1]["balance"]))
    lines = "".join(
        "<tr>"
        f'<td><a href="/contract?asof={escape(asof)}&ref={escape(row["CONTRACT_REFERENCE"])}">{escape(row["CONTRACT_REFERENCE"])}</a>'
        f'<div style="color:var(--muted);font-size:.8rem">{escape(row["BORROWER_NAME"])}</div></td>'
        f'<td>{escape(flow["CASH_FLOW_DATE"])}</td>'
        f'<td>{"Interest" if flow["CASH_FLOW_TYPE"] == "I" else "Principal"}</td>'
        f'<td class="num">{money(float(flow["CASH_FLOW_AMOUNT"]))}</td>'
        f'<td>{escape(row["method"].replace("_", " ").title())}</td>'
        f'<td class="num">{money(float(flow["OUTSTANDING"]))}</td>'
        "</tr>"
        for _when, row, flow in soon
    )
    principal = sum(float(flow["CASH_FLOW_AMOUNT"]) for _when, _row, flow in soon if flow["CASH_FLOW_TYPE"] == "N")
    interest = sum(float(flow["CASH_FLOW_AMOUNT"]) for _when, _row, flow in soon if flow["CASH_FLOW_TYPE"] == "I")
    return f"""
    <div class="label">Cash flow</div>
    <h1>Contractual amounts inside six months</h1>
    <p class="lead">Schedules are the semiannual cash flows generated for {escape(asof)}. Interest and principal are on separate rows. Off-balance facilities are absent because their outstanding was zero.</p>
    {month_picker(asof, "/cashflow")}
    {metric_cards([
        ("Interest inside six months", money(interest), False),
        ("Principal inside six months", money(principal), principal > 0),
        ("Rows", str(len(soon)), False),
        ("Contracts with a schedule", str(len(book)), False),
    ])}
    <div class="card">
      <table>
        <thead><tr><th>Contract</th><th>Date</th><th>Type</th><th class="num">Amount</th><th>Method</th><th class="num">Outstanding after</th></tr></thead>
        <tbody>{lines}</tbody>
      </table>
    </div>
    """


def contract_page(asof: str, ref: str) -> str:
    book = {row["CONTRACT_REFERENCE"]: row for row in facilities(asof)}
    row = book.get(ref)
    if row is None:
        return f"<h1>Contract {escape(ref)} is not in the {escape(asof)} extract</h1>"
    flows = "".join(
        "<tr>"
        f"<td>{escape(flow['CASH_FLOW_DATE'])}</td>"
        f"<td>{'Interest' if flow['CASH_FLOW_TYPE'] == 'I' else 'Principal'}</td>"
        f'<td class="num">{money(float(flow["CASH_FLOW_AMOUNT"]))}</td>'
        f'<td class="num">{money(float(flow["OUTSTANDING"]))}</td>'
        "</tr>"
        for flow in row["flows"]
    ) or "<tr><td colspan='4'>No contractual cash flow. Outstanding on this facility is zero.</td></tr>"
    rate = f"{row['rate'] * 100:.1f}%" if row["rate"] is not None else "—"
    method = row["method"].replace("_", " ").title() if row["method"] else "—"
    return f"""
    <div class="label">Contract</div>
    <h1>{escape(row["CONTRACT_REFERENCE"])}</h1>
    <p class="lead">{escape(row["BORROWER_NAME"])}. Grade {escape(row["grade"] or "—")}. {escape(row["INSTRUMENT"])}.</p>
    {month_picker(asof, "/contract", {"ref": ref})}
    {metric_cards([
        ("Outstanding", money(row["balance"]), False),
        ("LTV", pct(row["ltv"]), row["on_book"] and row["ltv"] >= 0.6),
        ("Market value", money(row["market"]), False),
        ("Coupon", rate, False),
    ])}
    <div class="grid">
      <div class="card">
        <div class="label">Collateral {escape(row["COLLATERAL_REFERENCE"])}</div>
        <p>{escape(row["PROPERTY_ADDRESS"])}</p>
        <p>{escape(row["COLLATERAL_TYPE"])}, {escape(row["DISTRICT"])}. First charge. Valuation {escape(row["VALUATION_DATE"])}.</p>
        <p>Net realizable value {money(row["net"])}. LTV on that value {pct(row["ltv_nrv"])}.</p>
      </div>
      <div class="card">
        <div class="label">Schedule</div>
        <p>Method {escape(method)}. Maturity {escape(row["maturity"] or "—")}.</p>
        <p>Next cash flow {escape(row["next_date"] or "—")} {"interest" if row["next_type"] == "I" else "principal" if row["next_type"] else ""} {money(row["next_amount"]) if row["next_date"] else ""}.</p>
      </div>
    </div>
    <div class="card" style="margin-top:12px">
      <div class="label">Remaining cash flows</div>
      <table>
        <thead><tr><th>Date</th><th>Type</th><th class="num">Amount</th><th class="num">Outstanding</th></tr></thead>
        <tbody>{flows}</tbody>
      </table>
    </div>
    """


def respond(path: str, query: dict) -> tuple[str, str]:
    asof = chosen_month(query)
    key = path.strip("/") or "dashboard"
    if key == "collateral":
        return "collateral", collateral_page(asof, (query.get("district") or [""])[0])
    if key == "cashflow":
        return "cashflow", cashflow_page(asof)
    if key == "contract":
        return "dashboard", contract_page(asof, (query.get("ref") or [""])[0])
    return "dashboard", dashboard(asof)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        active, body = respond(parsed.path, parse_qs(parsed.query))
        payload = page(active, active, body)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", 8767), Handler)
    print("http://127.0.0.1:8767")
    server.serve_forever()


if __name__ == "__main__":
    main()
