"""Same-origin demonstration of the business-case screens. No separate API client."""

from __future__ import annotations

import json
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
BOOK = json.loads((ROOT / "book.json").read_text(encoding="utf-8"))
NOTIFY = BOOK["notify_to"]
THRESHOLD = BOOK["threshold_hkd"]

SCENARIOS = {
    "base": "Latest extract, no shock",
    "revenue_decline": "Revenue down 15 percent, as in the trade-friction case",
    "margin_compression": "Margin down 2 percentage points",
    "funding_cost": "Borrowing cost up 1 percentage point",
    "liquidity": "Liquidity ratio down 0.15",
}
SHIFTS = {"base": 0.0, "revenue_decline": -0.6, "margin_compression": -0.4, "funding_cost": -0.3, "liquidity": -0.2}


def money(value: float | int | None) -> str:
    if value is None:
        return "—"
    return f"HKD {value:,.0f}"


def customer(cid: str | None) -> dict | None:
    if not cid:
        return None
    return next((row for row in BOOK["customers"] if row["customer_id"] == cid), None)


def project(row: dict, scenario: str) -> float:
    return round(row["interest_coverage"][-1] + SHIFTS.get(scenario, 0.0), 1)


def page(title: str, active: str, body: str) -> bytes:
    nav = [
        ("dashboard", "Portfolio"),
        ("news", "Adverse news"),
        ("industry", "Industry review"),
        ("repayment", "Repayments"),
        ("financial", "Financials and covenants"),
        ("reports", "Reports"),
        ("assistant", "Knowledge assistant"),
        ("drafts", "Email drafts"),
    ]
    links = []
    for key, label in nav:
        cls = "active" if key == active else ""
        links.append(f'<a class="{cls}" href="/{key}">{escape(label)}</a>')
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
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
.lead {{ color:var(--muted); max-width:760px; line-height:1.5; }}
.metrics {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:16px 0; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }}
.metric {{ border-top:3px solid var(--orange); }}
.metric.alert {{ border-top-color:var(--red); }}
.label {{ font-size:.7rem; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); font-weight:700; }}
.value {{ font-size:1.35rem; font-weight:700; margin-top:6px; }}
.grid {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
.grid3 {{ display:grid; grid-template-columns:1.2fr .8fr; gap:12px; }}
table {{ width:100%; border-collapse:collapse; font-size:.92rem; }}
th {{ text-align:left; font-size:.68rem; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); padding:8px; border-bottom:1px solid var(--line); }}
td {{ padding:10px 8px; border-bottom:1px solid var(--line); vertical-align:top; }}
tr.click:hover td {{ background:#FBF7F2; }}
.tag {{ display:inline-block; padding:2px 8px; border-radius:99px; font-size:.75rem; font-weight:700; }}
.tag-red {{ background:var(--wash); color:var(--red); }}
.tag-orange {{ background:#FDE8D4; color:var(--deep); }}
.tag-grey {{ background:#F7F4F0; color:var(--muted); border:1px solid var(--line); }}
.bar {{ height:8px; background:#F7F4F0; border-radius:99px; overflow:hidden; }}
.bar span {{ display:block; height:100%; background:var(--orange); }}
.bar.hot span {{ background:var(--red); }}
button, .btn {{ font:inherit; background:var(--orange); color:#fff; border:0; border-radius:8px; padding:8px 12px; font-weight:700; cursor:pointer; }}
.btn.ghost {{ background:#F7F4F0; color:var(--ink); border:1px solid var(--line); }}
textarea {{ width:100%; min-height:420px; font:14px/1.45 ui-monospace,monospace; border:1px solid var(--line); border-radius:10px; padding:12px; background:#fff; color:var(--ink); }}
.cite {{ font-size:.82rem; color:var(--muted); border-left:3px solid var(--orange); padding-left:10px; margin:8px 0; }}
form.inline {{ display:flex; gap:8px; flex-wrap:wrap; align-items:end; }}
select, input[type=number] {{ font:inherit; padding:8px; border:1px solid var(--line); border-radius:8px; background:#fff; }}
@media (max-width:900px) {{
  .shell, .metrics, .grid, .grid3 {{ grid-template-columns:1fr; }}
}}
</style>
</head>
<body>
<div class="shell">
  <nav>
    <div class="mark">RIP <span>review</span></div>
    <p>Business-case demonstration on the synthetic book. Position date 30 Sep 2026.</p>
    {''.join(links)}
  </nav>
  <main>
    <div class="banner">{escape(BOOK["banner"])}</div>
    {body}
  </main>
</div>
</body>
</html>"""
    return html.encode("utf-8")


def metrics(items: list[tuple[str, str, bool]]) -> str:
    cards = []
    for label, value, alert in items:
        cards.append(
            f'<div class="card metric {"alert" if alert else ""}"><div class="label">{escape(label)}</div><div class="value">{value}</div></div>'
        )
    return f'<div class="metrics">{"".join(cards)}</div>'


def bars(rows: list[tuple[str, float]], hot: bool = False) -> str:
    peak = max([value for _, value in rows] + [1])
    lines = []
    for label, value in rows:
        width = max(2, round(value / peak * 100))
        lines.append(
            f'<div style="display:grid;grid-template-columns:168px 1fr 132px;gap:8px;align-items:center;margin:8px 0">'
            f'<div>{escape(label)}</div><div class="bar {"hot" if hot else ""}"><span style="width:{width}%"></span></div>'
            f'<div style="text-align:right;color:var(--muted)">{money(value)}</div></div>'
        )
    return "".join(lines)


def dashboard() -> str:
    port = BOOK["portfolio"]
    stage_rows = [(f"Stage {key}", port["stages"][str(key)]["drawn_hkd"] if isinstance(port["stages"], dict) and str(key) in port["stages"] else port["stages"][key]["drawn_hkd"]) for key in (1, 2, 3)]
    # stages keys may be int from json load - json dumps int keys as strings
    stages = port["stages"]
    stage_rows = []
    for key in (1, 2, 3):
        slot = stages.get(str(key), stages.get(key))
        stage_rows.append((f"Stage {key}", slot["drawn_hkd"]))
    dpd_rows = [(name, slot["drawn_hkd"]) for name, slot in port["dpd"].items()]
    coll_rows = list(port["collateral"].items())
    mat = port["maturity"]
    industry_rows = [(row["industry"], row["drawn_hkd"]) for row in BOOK["industries"][:6]]
    top = sorted(BOOK["customers"], key=lambda row: row["drawn_hkd"], reverse=True)[:8]
    table = "".join(
        f'<tr class="click"><td><a href="/customer?id={escape(row["customer_id"])}">{escape(row["legal_name"])}</a><div style="color:var(--muted);font-size:.8rem">{escape(row["rm"])}</div></td>'
        f'<td>{escape(row["industry"])}</td><td>Stage {row["stage"]}</td>'
        f'<td>{row["prior_rating"]} → {row["rating"]}</td><td>{money(row["drawn_hkd"])}</td>'
        f'<td>{row["dpd"]}</td></tr>'
        for row in top
    )
    body = f"""
    <div class="label">Portfolio</div><h1>Management dashboard</h1>
    <p class="lead">Synthetic book as at 30 Sep 2026. Charts use the seeded customers, with demonstration fields for stage, ECL, LTV, maturity and days past due.</p>
    {metrics([
        ("Customers", str(port["customers"]), False),
        ("Drawn exposure", money(port["drawn_hkd"]), False),
        ("ECL", money(port["ecl_hkd"]), True),
        ("Stage migrations", str(port["migrations"]), True),
    ])}
    <div class="grid">
      <div class="card"><div class="label">Stage distribution by drawn exposure</div>{bars(stage_rows, hot=True)}</div>
      <div class="card"><div class="label">Days past due by drawn exposure</div>{bars(dpd_rows)}</div>
      <div class="card"><div class="label">Maturity of next obligations</div>{bars([("Within 30 days", mat["month"]), ("31 to 90 days", mat["quarter"]), ("After 90 days", mat["later"])])}<p class="lead">Input is the maturity profile on each loan. Amounts are the next obligation, not the whole drawn balance.</p></div>
      <div class="card"><div class="label">Collateral by type</div>{bars(coll_rows)}</div>
      <div class="card"><div class="label">Largest industries</div>{bars(industry_rows, hot=True)}<p><a href="/industry?name=Wholesale%20trade">Open the wholesale-trade review</a></p></div>
      <div class="card"><div class="label">ECL and LTV</div>
        <p>ECL coverage of drawn exposure is {port["ecl_coverage"]:.2%}. Provision movement versus the prior rating base is {money(port["ecl_hkd"] - port["prior_ecl_hkd"])}.</p>
        <p>Portfolio LTV is exposure divided by recorded collateral. Open a customer to see the ratio used in news materiality.</p>
      </div>
    </div>
    <div class="card" style="margin-top:12px">
      <div class="label">Largest names</div>
      <table><thead><tr><th>Customer</th><th>Industry</th><th>Stage</th><th>Rating</th><th>Drawn</th><th>DPD</th></tr></thead><tbody>{table}</tbody></table>
    </div>"""
    return body


def news_page(selected: list[str]) -> str:
    rows = []
    for item in BOOK["news"]:
        factors = item["factors"]
        checked = "checked" if item["id"] in selected else ""
        flag = '<span class="tag tag-red">Material</span>' if factors["material"] else '<span class="tag tag-grey">Below threshold</span>'
        rows.append(
            f'<tr><td><label><input type="checkbox" name="selected" value="{escape(item["id"])}" {checked}> {escape(item["headline"])}</label>'
            f'<div style="color:var(--muted);font-size:.8rem">{escape(item["date"])} · {escape(item["source"])}</div></td>'
            f'<td>{escape(item["industry"])}</td><td>{factors["score"]}</td><td>{flag}</td></tr>'
            f'<tr><td colspan="4" style="color:var(--muted)">{escape(item["body"])} '
            f'Exposure {money(factors["exposure_hkd"])}. Coverage {factors["security_coverage"]}. '
            f'Guarantor {factors["guarantor_support"]}. Strength {factors["financial_strength"]}. '
            f'Warnings {factors["warning_signals"]}.</td></tr>'
        )
    follow = ""
    if selected:
        chosen = [item for item in BOOK["news"] if item["id"] in selected]
        blocks = []
        for item in chosen:
            if item["customer_id"]:
                row = customer(item["customer_id"])
                blocks.append(
                    f'<div class="card" style="margin-top:12px"><div class="label">Group review</div><h2>{escape(row["legal_name"])}</h2>'
                    f'<p>{escape(item["body"])}</p>'
                    f'<p>Drawn {money(row["drawn_hkd"])}. Rating {row["prior_rating"]} to {row["rating"]}. '
                    f'Collateral {escape(row["collateral_type"])} {money(row["collateral_hkd"])}. RM {escape(row["rm"])}.</p>'
                    f'<p><a href="/email?id=MAIL-NEWS-APEX">Open the adverse-news email draft</a> · '
                    f'<a href="/industry?name={escape(row["industry"])}">Continue to the {escape(row["industry"])} industry review</a></p></div>'
                )
            else:
                blocks.append(
                    f'<div class="card" style="margin-top:12px"><div class="label">Selected sector news</div>'
                    f'<p>{escape(item["headline"])}</p><p><a href="/industry?name=Wholesale%20trade">Continue to the wholesale-trade review</a> · '
                    f'<a href="/email?id=MAIL-IND-WHOLESALE">Open the industry email draft</a></p></div>'
                )
        follow = "".join(blocks)
    return f"""
    <div class="label">Step 1 of 3</div><h1>Adverse news</h1>
    <p class="lead">The feed is a demonstration stand-in for the Credit Risk Alert Portal. Materiality uses exposure, security coverage, guarantor support, financial strength and open warnings. Select a news item to open the group review, then the industry review.</p>
    <form method="get" action="/news">
      <table><thead><tr><th>Item</th><th>Industry</th><th>Score</th><th></th></tr></thead><tbody>{''.join(rows)}</tbody></table>
      <p><button type="submit">Review selected news</button></p>
    </form>
    {follow}
    """


def industry_page(name: str) -> str:
    row = next((item for item in BOOK["industries"] if item["industry"] == name), BOOK["industries"][0])
    members = [item for item in BOOK["customers"] if item["industry"] == row["industry"]]
    members.sort(key=lambda item: item["drawn_hkd"], reverse=True)
    body_rows = "".join(
        f'<tr><td><a href="/customer?id={escape(item["customer_id"])}">{escape(item["legal_name"])}</a></td>'
        f'<td>{item["prior_rating"]} → {item["rating"]}</td><td>Stage {item["stage"]}</td>'
        f'<td>{money(item["drawn_hkd"])}</td><td>{item["coverage_ratio"]}</td><td>{len(item["warnings"])}</td>'
        f'<td>{item["dpd"]}</td></tr>'
        for item in members
    )
    options = "".join(
        f'<option {"selected" if item["industry"]==row["industry"] else ""}>{escape(item["industry"])}</option>'
        for item in BOOK["industries"]
    )
    return f"""
    <div class="label">Industry</div><h1>{escape(row["industry"])}</h1>
    <p class="lead">Signals are read against this industry's drawn exposure and collateral, so a sector headline is judged by what the book actually holds.</p>
    <form class="inline" method="get" action="/industry"><label>Industry<br><select name="name" onchange="this.form.submit()">{options}</select></label></form>
    {metrics([
        ("Drawn", money(row["drawn_hkd"]), False),
        ("Stage 2 names", str(row["stage2"]), True),
        ("Migrations", str(row["migrations"]), row["migrations"] > 0),
        ("Open warnings", str(row["open_warnings"]), row["open_warnings"] > 0),
    ])}
    <div class="card">
      <table><thead><tr><th>Customer</th><th>Rating</th><th>Stage</th><th>Drawn</th><th>Coverage</th><th>Warnings</th><th>DPD</th></tr></thead>
      <tbody>{body_rows}</tbody></table>
    </div>
    <p><a class="btn" href="/email?id=MAIL-IND-WHOLESALE">Open the industry email draft</a></p>
    """


def repayment_page(window: int) -> str:
    rows = []
    for item in BOOK["customers"]:
        if item["next_due_hkd"] < THRESHOLD or item["next_due_days"] > window:
            continue
        rows.append(item)
    rows.sort(key=lambda item: item["next_due_days"])
    body = "".join(
        f'<tr><td><a href="/customer?id={escape(item["customer_id"])}">{escape(item["legal_name"])}</a><div style="color:var(--muted);font-size:.8rem">{escape(item["rm"])} · {escape(item["group_name"])}</div></td>'
        f'<td>{money(item["next_due_hkd"])}</td><td>{item["next_due_days"]} days</td><td>{escape(item["next_due_source"])}</td>'
        f'<td>{"Refinancing" if item["refinancing"] else "Instalment"}</td>'
        f'<td>{("<a href='/email?id=MAIL-REPAY-LANTERN'>Draft</a>") if item["customer_id"]=="CUS-LFLL-0003" else "—"}</td></tr>'
        for item in rows
    ) or '<tr><td colspan="6">No obligation above HKD 5,000,000 falls in this window.</td></tr>'
    ageing = "".join(
        f'<tr><td><a href="/customer?id={escape(item["customer_id"])}">{escape(item["legal_name"])}</a></td><td>{item["dpd"]}</td><td>{escape(item["dpd_component"])}</td><td>{money(item["drawn_hkd"])}</td></tr>'
        for item in sorted(BOOK["customers"], key=lambda row: row["dpd"], reverse=True)[:6]
        if item["dpd"] > 0
    )
    return f"""
    <div class="label">Repayment</div><h1>Obligations above HKD 5,000,000</h1>
    <p class="lead">Dates and amounts come from the watchlist or the credit proposal. The window is {window} days.</p>
    <form class="inline" method="get" action="/repayment">
      <label>Window (days)<br><input type="number" name="window" min="7" max="365" value="{window}"></label>
      <button type="submit">Apply</button>
      <a class="btn ghost" href="/repayment?window=30">One month</a>
      <a class="btn ghost" href="/repayment?window=90">One quarter</a>
    </form>
    <div class="card" style="margin-top:12px"><table><thead><tr><th>Customer</th><th>Amount</th><th>Due</th><th>Source</th><th>Type</th><th></th></tr></thead><tbody>{body}</tbody></table></div>
    <div class="card" style="margin-top:12px"><div class="label">Approaching 30, 60, 90 and 180 days</div>
      <table><thead><tr><th>Customer</th><th>DPD</th><th>Component</th><th>Drawn</th></tr></thead><tbody>{ageing}</tbody></table>
      <p><a href="/email?id=MAIL-DPD-LANTERN">Open the Lantern Ferry ageing draft</a></p>
    </div>"""


def financial_page(cid: str, scenario: str) -> str:
    row = customer(cid) or customer("CUS-AHTL-0001")
    projected = project(row, scenario)
    threshold = row["coverage_threshold"]
    status = "Inside covenant" if row["interest_coverage"][-1] >= threshold else "Outside covenant"
    scenario_status = "Headroom remains" if projected >= threshold else "Projected breach"
    options = "".join(
        f'<option value="{escape(item["customer_id"])}" {"selected" if item["customer_id"]==row["customer_id"] else ""}>{escape(item["legal_name"])}</option>'
        for item in BOOK["customers"] if item["full_file"]
    )
    shocks = "".join(
        f'<option value="{key}" {"selected" if key==scenario else ""}>{escape(label)}</option>'
        for key, label in SCENARIOS.items()
    )
    years = ["2024", "2025", "2026"]
    fin_rows = "".join(
        f'<tr><td>{label}</td>' + "".join(f"<td>{value}</td>" for value in values) + "</tr>"
        for label, values in (
            ("Revenue", [money(v) for v in row["revenue_hkd"]]),
            ("Margin", [f"{v:.1f}%" for v in row["margin_pct"]]),
            ("Liquidity ratio", [f"{v:.2f}" for v in row["liquidity_ratio"]]),
            ("Leverage", [f"{v:.1f}x" for v in row["leverage"]]),
            ("Interest coverage", [f"{v:.1f}x" for v in row["interest_coverage"]]),
        )
    )
    return f"""
    <div class="label">Financial analysis</div><h1>{escape(row["legal_name"])}</h1>
    <p class="lead">Figures are extracted from the demonstration financial statements. The Google financial-analysis agent is the intended reader of uploaded or HKEX statements. This screen shows the same tests on the synthetic file.</p>
    <form class="inline" method="get" action="/financial">
      <label>Customer<br><select name="customer">{options}</select></label>
      <label>Scenario<br><select name="scenario">{shocks}</select></label>
      <button type="submit">Run</button>
    </form>
    {metrics([
        ("Latest coverage", f'{row["interest_coverage"][-1]:.1f}x', False),
        ("Covenant", f'{threshold:.1f}x', False),
        ("Today", status, row["interest_coverage"][-1] < threshold),
        ("Scenario", f"{projected:.1f}x", projected < threshold),
    ])}
    <div class="card"><table><thead><tr><th>Measure</th>{"".join(f"<th>{year}</th>" for year in years)}</tr></thead><tbody>{fin_rows}</tbody></table>
      <p>Credit assumption at approval: {row["coverage_assumption"]:.1f}x. Scenario: {escape(SCENARIOS[scenario])}. Result: {scenario_status}.</p>
      <p>Statement extract: {escape(row["documents"]["financials"]["passage"])}</p>
      <p>{'<a href="/email?id=MAIL-COV-APEX">Open the covenant email draft</a>' if row["customer_id"]=="CUS-AHTL-0001" else "The worked covenant letter is written for Apex Harbour Trading."}</p>
    </div>"""


def reports_page(kind: str, detail: str, cid: str) -> str:
    row = customer(cid) or customer("CUS-AHTL-0001")
    port = BOOK["portfolio"]
    if kind == "customer":
        title = f"Customer Status Report — {row['legal_name']}"
        summary = (
            f"<p>{escape(row['legal_name'])} is rating {row['rating']} (from {row['prior_rating']}), stage {row['stage']}, "
            f"drawn {money(row['drawn_hkd'])}. Relationship manager {escape(row['rm'])}.</p>"
            f"<p>Next obligation {money(row['next_due_hkd'])} in {row['next_due_days']} days. Days past due {row['dpd']}.</p>"
        )
        extra = (
            f"<h2>Sources</h2><p class='cite'>{escape(row['documents']['review']['title'])}. {escape(row['documents']['review']['passage'])}</p>"
            f"<p class='cite'>{escape(row['documents']['financials']['title'])}. {escape(row['documents']['financials']['passage'])}</p>"
            f"<p class='cite'>{escape(row['documents']['repayment']['title'])}. {escape(row['documents']['repayment']['passage'])}</p>"
        ) if detail == "full" else ""
    else:
        title = "Management Information Report"
        summary = (
            f"<p>Drawn exposure {money(port['drawn_hkd'])} across {port['customers']} customers. "
            f"ECL {money(port['ecl_hkd'])}. Stage migrations {port['migrations']}. "
            f"Obligations above HKD 5,000,000 inside 90 days: {len(port['large_due'])}.</p>"
            f"<p>Wholesale trade is the industry carried into the review because of rating migration and the sector news of 2 Oct 2026.</p>"
        )
        extra = "<h2>Stage and DPD</h2>" + bars(
            [(f"Stage {key}", port["stages"][str(key)]["drawn_hkd"]) for key in (1, 2, 3)],
            hot=True,
        ) if detail == "full" else ""
    customers = "".join(
        f'<option value="{escape(item["customer_id"])}" {"selected" if item["customer_id"]==row["customer_id"] else ""}>{escape(item["legal_name"])}</option>'
        for item in BOOK["customers"] if item["full_file"]
    )
    return f"""
    <div class="label">Reports</div><h1>{escape(title)}</h1>
    <p class="lead">Draft for discussion. A person still reviews it. The draft is not an approval.</p>
    <form class="inline" method="get" action="/reports">
      <label>Report<br><select name="kind">
        <option value="mir" {"selected" if kind=="mir" else ""}>Management Information Report</option>
        <option value="customer" {"selected" if kind=="customer" else ""}>Customer Status Report</option>
      </select></label>
      <label>Detail<br><select name="detail">
        <option value="summary" {"selected" if detail=="summary" else ""}>Summary</option>
        <option value="full" {"selected" if detail=="full" else ""}>Detailed, with sources</option>
      </select></label>
      <label>Customer<br><select name="customer">{customers}</select></label>
      <button type="submit">Prepare</button>
    </form>
    <div class="card" style="margin-top:12px">{summary}{extra}</div>"""


def assistant_page(question: str, cid: str) -> str:
    row = customer(cid) or customer("CUS-AHTL-0001")
    answer, cites = answer_for(row, question)
    options = "".join(
        f'<option value="{escape(item["customer_id"])}" {"selected" if item["customer_id"]==row["customer_id"] else ""}>{escape(item["legal_name"])}</option>'
        for item in BOOK["customers"] if item["full_file"]
    )
    prompts = [
        "What are the key risks for this customer?",
        "Why did the rating change?",
        "What has changed since the last review?",
        "What repayments are coming due?",
    ]
    chips = " ".join(
        f'<a class="btn ghost" href="/assistant?customer={escape(row["customer_id"])}&q={escape(prompt)}">{escape(prompt)}</a>'
        for prompt in prompts
    )
    cite_html = "".join(
        f'<p class="cite"><strong>{escape(doc["title"])}</strong> · {escape(doc["locator"])}<br>{escape(doc["passage"])}</p>'
        for doc in cites
    )
    return f"""
    <div class="label">Knowledge assistant</div><h1>Ask the file</h1>
    <p class="lead">This first version answers four questions. Sources are the credit paper, the credit review, the financial statements and the repayment schedule. News, approval minutes and internal mail are not searched yet.</p>
    <form class="inline" method="get" action="/assistant">
      <label>Customer<br><select name="customer">{options}</select></label>
      <label>Question<br><input name="q" value="{escape(question)}" style="width:420px"></label>
      <button type="submit">Ask</button>
    </form>
    <p>{chips}</p>
    <div class="card"><p>{answer}</p>{cite_html}</div>"""


def answer_for(row: dict, question: str) -> tuple[str, list[dict]]:
    text = question.lower()
    docs = row["documents"]
    if any(word in text for word in ("rating", "downgrade", "notch", "why")):
        return (
            f"The internal rating moved from {row['prior_rating']} on {row['prior_rating_date']} to {row['rating']} on 30 Sep 2026. "
            f"Stage is now {row['stage']}, from {row['prior_stage']}.",
            [docs["review"], docs["credit_paper"]],
        )
    if any(word in text for word in ("repay", "due", "maturity", "instal")):
        return (
            f"The next obligation is {money(row['next_due_hkd'])} in {row['next_due_days']} days, from the {row['next_due_source']}. "
            f"Days past due are {row['dpd']} on {row['dpd_component']}. The monitoring threshold is HKD 5,000,000.",
            [docs["repayment"]],
        )
    if any(word in text for word in ("since", "develop", "change", "latest", "review")):
        return (
            f"Since the prior rating point, coverage is {row['interest_coverage'][-1]:.1f} times against a covenant of {row['coverage_threshold']:.1f} times. "
            f"Revenue in the latest year is {money(row['revenue_hkd'][-1])}. Drawn exposure is {money(row['drawn_hkd'])}.",
            [docs["review"], docs["financials"]],
        )
    if any(word in text for word in ("risk", "key", "concern", "group")):
        warnings = "; ".join(item["description"] for item in row["warnings"]) or "No open early-warning register item is on this name."
        return (
            f"The main credit points on file are rating {row['rating']}, stage {row['stage']}, drawn {money(row['drawn_hkd'])}, "
            f"and collateral coverage {row['coverage_ratio']}. {warnings}",
            [docs["credit_paper"], docs["review"], docs["financials"]],
        )
    return (
        "This version answers four questions: key risks, why the rating changed, what changed since the last review, and which repayments are coming due. "
        "It reads the credit paper, the review, the financial statements and the repayment schedule.",
        [],
    )


def drafts_page() -> str:
    rows = "".join(
        f'<tr><td><a href="/email?id={escape(item["id"])}">{escape(item["subject"])}</a></td><td>{escape(item["kind"])}</td><td>{escape(NOTIFY)}</td></tr>'
        for item in BOOK["drafts"]
    )
    return f"""
    <div class="label">Outbox</div><h1>Email drafts</h1>
    <p class="lead">Each letter is complete and written from the analysis. They are not sent from this site. Open one, copy it or download the .eml file, and send it yourself to {escape(NOTIFY)}.</p>
    <div class="card"><table><thead><tr><th>Subject</th><th>Kind</th><th>To</th></tr></thead><tbody>{rows}</tbody></table></div>"""


def email_page(draft_id: str) -> str:
    draft = next((item for item in BOOK["drafts"] if item["id"] == draft_id), BOOK["drafts"][0])
    return f"""
    <div class="label">{escape(draft["kind"])}</div><h1>{escape(draft["subject"])}</h1>
    <p class="lead">To {escape(NOTIFY)}. Download the draft and send it from your own mailbox.</p>
    <p><a class="btn" href="/email.eml?id={escape(draft["id"])}">Download .eml</a></p>
    <textarea readonly>{escape(draft["body"])}</textarea>"""


def customer_page(cid: str) -> str:
    row = customer(cid)
    if not row:
        return "<h1>Customer not in the book</h1>"
    docs = "".join(
        f'<p class="cite"><strong>{escape(doc["title"])}</strong> · {escape(doc["locator"])}<br>{escape(doc["passage"])}</p>'
        for doc in row["documents"].values()
    )
    return f"""
    <div class="label">Customer</div><h1>{escape(row["legal_name"])}</h1>
    <p class="lead">{escape(row["summary"])}</p>
    {metrics([
        ("Drawn", money(row["drawn_hkd"]), False),
        ("Rating", f'{row["prior_rating"]} → {row["rating"]}', row["rating"] > row["prior_rating"]),
        ("LTV", str(row["ltv"]), (row["ltv"] or 0) > 1),
        ("DPD", str(row["dpd"]), row["dpd"] >= 30),
    ])}
    <div class="card"><p>Industry {escape(row["industry"])}. Stage {row["prior_stage"]} to {row["stage"]}. RM {escape(row["rm"])}.</p>
    <p>Collateral {escape(row["collateral_type"])} {money(row["collateral_hkd"])}. Coverage {row["coverage_ratio"]}.</p>
    <p>Next obligation {money(row["next_due_hkd"])} in {row["next_due_days"]} days, from the {escape(row["next_due_source"])}.</p>
    {docs}
    <p><a href="/assistant?customer={escape(row["customer_id"])}&q=What+are+the+key+risks+for+this+customer%3F">Ask about this customer</a></p></div>"""


ROUTES = {
    "dashboard": lambda q: dashboard(),
    "news": lambda q: news_page(q.get("selected", [])),
    "industry": lambda q: industry_page((q.get("name") or ["Wholesale trade"])[0]),
    "repayment": lambda q: repayment_page(int((q.get("window") or ["90"])[0] or 90)),
    "financial": lambda q: financial_page((q.get("customer") or ["CUS-AHTL-0001"])[0], (q.get("scenario") or ["revenue_decline"])[0]),
    "reports": lambda q: reports_page((q.get("kind") or ["mir"])[0], (q.get("detail") or ["summary"])[0], (q.get("customer") or ["CUS-AHTL-0001"])[0]),
    "assistant": lambda q: assistant_page((q.get("q") or ["What are the key risks for this customer?"])[0], (q.get("customer") or ["CUS-AHTL-0001"])[0]),
    "drafts": lambda q: drafts_page(),
    "email": lambda q: email_page((q.get("id") or ["MAIL-NEWS-APEX"])[0]),
    "customer": lambda q: customer_page((q.get("id") or [""])[0]),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        key = parsed.path.strip("/") or "dashboard"
        query = parse_qs(parsed.query)
        if key == "email.eml":
            draft = next((item for item in BOOK["drafts"] if item["id"] == (query.get("id") or [""])[0]), BOOK["drafts"][0])
            payload = draft["body"].encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "message/rfc822")
            self.send_header("Content-Disposition", f'attachment; filename="{draft["id"]}.eml"')
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if key not in ROUTES:
            key = "dashboard"
        body = page(key, "drafts" if key == "email" else key, ROUTES[key](query))
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", 8766), Handler)
    print("http://127.0.0.1:8766")
    server.serve_forever()


if __name__ == "__main__":
    main()
