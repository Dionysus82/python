"""Same-origin demonstration of the business-case screens."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import sys
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from html import escape
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import agent_slot
import build_obligor_reports
import news_desk
BOOK = json.loads((ROOT / "book.json").read_text(encoding="utf-8"))
BOOK["news"] = news_desk.load_workbook_news(BOOK["customers"], ROOT / "property_data" / "apex_negative_news_v3.xlsx")
news_desk.apply_severity(BOOK["news"])
HKEX_FILINGS = [
    {
        "id": "3768-annual",
        "issuer": "Apex Water Solutions Ltd. (3768.HK)",
        "document": "Annual report 2025",
        "year": 2025,
        "names": [
            "Apex Water Solutions Ltd.",
            "Apex Water Solutions",
            "3768.HK",
            "3768",
            "Apex Global Holdings Limited",
            "Apex Global Holdings",
            "BOR-AGHL",
        ],
    },
    {
        "id": "3768-interim",
        "issuer": "Apex Water Solutions Ltd. (3768.HK)",
        "document": "Interim report 2026",
        "year": 2026,
        "names": [
            "Apex Water Solutions Ltd.",
            "Apex Water Solutions",
            "3768.HK",
            "3768",
            "Apex Global Holdings Limited",
            "Apex Global Holdings",
            "BOR-AGHL",
        ],
    },
]
REPORT_FILES = ROOT / "report_files"
OBLIGORS = json.loads((REPORT_FILES / "obligors.json").read_text(encoding="utf-8"))
UPLOADS = REPORT_FILES / "uploads"
UPLOAD_INDEX = UPLOADS / "index.json"
HK = timezone(timedelta(hours=8))
SEEDED_PROPOSALS = [
    {
        "id": "apex-annual-review",
        "title": "Annual Review — Apex Group",
        "rm": "Sophie Chan",
        "stored": "31 Oct 2026",
        "filename": "Apex_Group_Annual_Review_Proposal.docx",
        "file": "Apex_Group_Annual_Review_Proposal.docx",
        "output_title": "Apex Group Credit Monitoring Report",
        "output_file": "Apex_Group_Credit_Monitoring_Report_31Oct2026.docx",
        "output_name": "Apex_Group_Credit_Monitoring_Report_31Oct2026.docx",
    }
]
THRESHOLD = BOOK["threshold_hkd"]

DEMO_USER = "cro.shum"
DEMO_PASSWORD = "Harbour-Demo-2026"
SESSION = hashlib.sha256(b"rip-demo-session-v1").hexdigest()

SCENARIOS = {
    "base": "Latest extract, no shock",
    "revenue_decline": "Revenue down 15 percent, as in the trade-friction case",
    "margin_compression": "Margin down 2 percentage points",
    "funding_cost": "Borrowing cost up 1 percentage point",
    "liquidity": "Liquidity ratio down 0.15",
}
SHIFTS = {"base": 0.0, "revenue_decline": -0.6, "margin_compression": -0.4, "funding_cost": -0.3, "liquidity": -0.2}
VIEW: ContextVar["BookView"] = ContextVar("rip_view")
POINT_FIELDS = (
    "drawn_hkd", "committed_hkd", "ecl_hkd", "prior_ecl_hkd", "stage", "prior_stage", "dpd",
    "rating", "collateral_hkd", "ltv", "coverage_ratio", "next_due_days", "next_due_hkd",
    "next_due_date", "next_contract", "next_method", "refinancing",
)


class BookView:
    def __init__(self, dates: list[str], next_path: str):
        known = BOOK["dates"]
        chosen = [item for item in known if item in dates]
        self.dates = chosen or list(known)
        self.focus = self.dates[-1]
        self.next_path = next_path if next_path.startswith("/") and not next_path.startswith("//") else "/dashboard"

    def label(self, iso: str | None = None) -> str:
        return datetime.strptime(iso or self.focus, "%Y-%m-%d").strftime("%-d %b %Y")

    def point(self, raw: dict, iso: str) -> dict | None:
        return next((item for item in raw["history"] if item["date"] == iso), None)

    def project(self, raw: dict) -> dict:
        row = dict(raw)
        point = self.point(raw, self.focus)
        on_position = point is not None
        if point is None:
            earlier = [item for item in raw["history"] if item["date"] <= self.focus]
            point = earlier[-1] if earlier else raw["history"][-1]
        for key in POINT_FIELDS:
            row[key] = point[key]
        row["nrv_hkd"] = point["nrv_hkd"]
        row["ead_hkd"] = point["ead_hkd"]
        row["nominal_hkd"] = point["nominal_hkd"]
        row["series"] = [self.point(raw, date) or blank_observation(date) for date in self.dates]
        row["facilities"] = point["facilities"]
        row["on_position"] = on_position
        row["observed"] = point["date"]
        row["dpd_component"] = "Portfolio extract" if point["dpd"] else "None"
        row["position"] = point["date"]
        when = self.label(point["date"])
        extract = []
        if point["dpd"] > 0:
            extract.append({"description": f"Portfolio extract at {when}: {point['dpd']} days past due."})
        if point["stage"] >= 2:
            extract.append({"description": f"Stage {point['stage']} on the portfolio extract at {when}."})
        demo = [
            item for item in raw["warnings"]
            if not item["description"].startswith("Portfolio extract") and not item["description"].startswith("Stage ")
        ]
        row["warnings"] = extract + demo
        row["watchlist"] = point["stage"] >= 2 or point["dpd"] > 0
        return row

    def portfolio(self) -> dict:
        return next(item for item in BOOK["portfolio_history"] if item["date"] == self.focus)

    def portfolio_series(self) -> list[dict]:
        return [next(item for item in BOOK["portfolio_history"] if item["date"] == date) for date in self.dates]


def view() -> BookView:
    return VIEW.get()


def latest_iso() -> str:
    return BOOK["dates"][-1]


def portfolio_at(iso: str) -> dict:
    return next(item for item in BOOK["portfolio_history"] if item["date"] == iso)


def customer_at(cid: str, iso: str) -> dict | None:
    raw = next(row for row in BOOK["customers"] if row["customer_id"] == cid)
    point = next((item for item in raw["history"] if item["date"] == iso), None)
    if point is None:
        return None
    row = dict(raw)
    for key in POINT_FIELDS:
        row[key] = point[key]
    return row


def bind_view(dates: list[str], next_path: str) -> BookView:
    chosen = BookView(dates, next_path)
    VIEW.set(chosen)
    return chosen


def dates_from_cookie(header: str | None) -> list[str]:
    jar = SimpleCookie()
    jar.load(header or "")
    morsel = jar.get("rip-dates")
    if morsel is None or not morsel.value:
        return list(BOOK["dates"])
    return [item for item in morsel.value.split(",") if item in BOOK["dates"]]


def date_cookie(dates: list[str]) -> str:
    value = ",".join(dates)
    return f"rip-dates={value}; HttpOnly; SameSite=Lax; Path=/; Max-Age=31536000"


def blank_observation(iso: str) -> dict:
    return {
        "date": iso,
        "drawn_hkd": None,
        "committed_hkd": None,
        "ecl_hkd": None,
        "prior_ecl_hkd": None,
        "ead_hkd": None,
        "nominal_hkd": None,
        "stage": "—",
        "prior_stage": "—",
        "dpd": "—",
        "rating": "—",
        "collateral_hkd": None,
        "nrv_hkd": None,
        "ltv": "—",
        "coverage_ratio": "—",
        "next_due_days": "—",
        "next_due_hkd": None,
        "next_due_date": "—",
        "next_contract": "—",
        "next_method": "—",
        "refinancing": False,
        "facilities": [],
    }


def money(value: float | int | None) -> str:
    if value is None:
        return "—"
    return f"HKD {value:,.0f}"


def default_customer_id() -> str:
    return BOOK.get("default_customer_id") or BOOK["customers"][0]["customer_id"]


def default_industry() -> str:
    return BOOK.get("default_industry") or BOOK["industries"][0]["industry"]


def customer(cid: str | None) -> dict | None:
    if not cid:
        return None
    raw = next((row for row in BOOK["customers"] if row["customer_id"] == cid), None)
    if raw is None:
        return None
    return view().project(raw)


def project(row: dict, scenario: str) -> float | None:
    latest = row["interest_coverage"][-1]
    if latest is None:
        return None
    return round(latest + SHIFTS.get(scenario, 0.0), 1)


def measure(value, pattern: str) -> str:
    if value is None:
        return "—"
    return pattern.format(value)


def date_bar(where: str = "top") -> str:
    chosen = view()
    count = len(chosen.dates)
    if count == len(BOOK["dates"]):
        summary = f"All {count} months · position {chosen.label()}"
    elif count == 1:
        summary = chosen.label()
    else:
        summary = f"{count} months · position {chosen.label()}"
    boxes = []
    for iso in BOOK["dates"]:
        checked = "checked" if iso in chosen.dates else ""
        boxes.append(
            f'<label><input type="checkbox" name="d" value="{iso}" {checked}>{escape(chosen.label(iso))}</label>'
        )
    placed = "date-menu end" if where == "bottom" else "date-menu"
    return f"""
    <form class="{placed}" method="post" action="/dates">
      <input type="hidden" name="next" value="{escape(chosen.next_path)}">
      <button type="button" class="date-toggle" aria-expanded="false" aria-controls="date-panel">
        <span class="label">Reporting dates</span>
        <strong>{escape(summary)}</strong>
      </button>
      <div class="date-panel" id="date-panel">
        {''.join(boxes)}
        <p class="hint">Position {escape(chosen.label())}. The trend uses the {count} checked date{"s" if count != 1 else ""}.</p>
        <div class="date-actions">
          <button type="submit" name="preset" value="apply">Apply dates</button>
          <button type="submit" class="ghost" name="preset" value="all">All dates</button>
          <button type="submit" class="ghost" name="preset" value="latest">Latest only</button>
        </div>
      </div>
    </form>"""


def chart_month_menu() -> str:
    chosen = view()
    history = BOOK["portfolio_history"]
    boxes = []
    for index, item in enumerate(history):
        checked = "checked" if item["date"] in chosen.dates else ""
        label = chosen.label(item["date"])
        boxes.append(
            f'<label><input type="checkbox" name="d" value="{item["date"]}" data-month="{index}" {checked}>{escape(label)}</label>'
        )
    count = len(chosen.dates)
    if count == len(history):
        summary = f"All {count} months"
    elif count == 1:
        summary = chosen.label()
    else:
        summary = f"{count} months"
    return f"""
    <form class="date-menu corner" id="trend-months" method="post" action="/dates">
      <input type="hidden" name="next" value="/dashboard">
      <button type="button" class="date-toggle" aria-expanded="false" aria-controls="trend-month-panel">
        <span class="label">Chart months</span>
        <strong>{escape(summary)}</strong>
      </button>
      <div class="date-panel" id="trend-month-panel">
        {''.join(boxes)}
      </div>
    </form>"""


def trend_table(metrics: list[tuple[str, object]]) -> str:
    chosen = view()
    head = "".join(f"<th>{escape(chosen.label(iso))}</th>" for iso in chosen.dates)
    rows = []
    for label, getter in metrics:
        cells = "".join(f"<td>{getter(iso)}</td>" for iso in chosen.dates)
        rows.append(f"<tr><th>{escape(label)}</th>{cells}</tr>")
    return f'<div class="scroll"><table class="trend"><thead><tr><th></th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def trend_chart() -> str:
    history = BOOK["portfolio_history"]
    chosen = view()
    payload = {
        "labels": [datetime.strptime(item["date"], "%Y-%m-%d").strftime("%b %y") for item in history],
        "full": [chosen.label(item["date"]) for item in history],
        "series": [
            {"id": "ecl", "name": "ECL", "unit": "hkd", "on": True, "values": [item["ecl_hkd"] for item in history]},
            {"id": "dpd60", "name": "Drawn 60 days or more past due", "unit": "hkd", "on": False, "values": [item["dpd60_drawn"] for item in history]},
            {"id": "stage2", "name": "Drawn in stage 2", "unit": "hkd", "on": False, "values": [item["stage2_drawn"] for item in history]},
            {"id": "drawn", "name": "Drawn exposure", "unit": "hkd", "on": False, "values": [item["drawn_hkd"] for item in history]},
            {"id": "pastdue", "name": "Names past due", "unit": "count", "on": False, "values": [item["dpd_names"] for item in history]},
            {"id": "stage2n", "name": "Stage 2 names", "unit": "count", "on": False, "values": [item["stage2_names"] for item in history]},
            {"id": "cover", "name": "ECL coverage", "unit": "pct", "on": False, "values": [item["ecl_coverage"] for item in history]},
            {"id": "ltv", "name": "Portfolio LTV", "unit": "ratio", "on": False, "values": [item["ltv"] for item in history]},
            {"id": "large", "name": "Large repayments inside 90 days", "unit": "count", "on": False, "values": [len(item["large_due"]) for item in history]},
        ],
    }
    series_boxes = "".join(
        f'<label><input type="checkbox" data-series="{escape(item["id"])}" {"checked" if item["on"] else ""}>{escape(item["name"])}</label>'
        for item in payload["series"]
    )
    script = r"""
<script>
(function () {
  var data = window.TREND_DATA;
  var svg = document.getElementById("trend-svg");
  var note = document.getElementById("trend-note");
  var legend = document.getElementById("trend-legend");
  var colors = ["#E36F1E", "#B42318", "#8C3E16", "#2457A6", "#1F6B4A", "#6F6862", "#C45112", "#3A342F", "#8A6A2F"];
  function checked(selector) {
    return Array.prototype.filter.call(document.querySelectorAll(selector), function (box) { return box.checked; });
  }
  function fmt(unit, value) {
    if (unit === "hkd") {
      var abs = Math.abs(value);
      if (abs >= 1e9) return "HKD " + (value / 1e9).toFixed(2) + "bn";
      if (abs >= 1e6) return "HKD " + (value / 1e6).toFixed(1) + "m";
      return "HKD " + Math.round(value).toLocaleString("en-HK");
    }
    if (unit === "pct") return (value * 100).toFixed(2) + "%";
    if (unit === "ratio") return Number(value).toFixed(2);
    return String(Math.round(value));
  }
  function refreshMonthLabel() {
    var host = document.getElementById("trend-months");
    if (!host) return;
    var boxes = host.querySelectorAll("[data-month]");
    var on = Array.prototype.filter.call(boxes, function (box) { return box.checked; });
    var strong = host.querySelector("strong");
    if (!on.length) strong.textContent = "No months";
    else if (on.length === boxes.length) strong.textContent = "All " + boxes.length + " months";
    else if (on.length === 1) strong.textContent = on[0].parentNode.textContent.trim();
    else strong.textContent = on.length + " months";
  }
  function draw() {
    refreshMonthLabel();
    var series = checked("[data-series]").map(function (box) {
      return data.series.filter(function (item) { return item.id === box.getAttribute("data-series"); })[0];
    });
    var months = checked("[data-month]").map(function (box) { return Number(box.getAttribute("data-month")); });
    if (!series.length || !months.length) {
      svg.innerHTML = "";
      legend.innerHTML = "";
      note.textContent = "Check at least one series and one month.";
      return;
    }
    var W = 760, H = 280, left = 78, right = 16, top = 18, bottom = 36;
    var plotW = W - left - right, plotH = H - top - bottom;
    var units = {};
    series.forEach(function (item) { units[item.unit] = true; });
    var peaks = series.map(function (item) {
      return Math.max.apply(null, months.map(function (index) { return item.values[index]; }));
    });
    var positive = peaks.filter(function (value) { return value > 0; });
    var wide = positive.length > 1 && Math.max.apply(null, positive) / Math.min.apply(null, positive) > 20;
    var indexMode = Object.keys(units).length > 1 || wide;
    var prepared = series.map(function (item, order) {
      var slice = months.map(function (index) { return item.values[index]; });
      var peak = Math.max.apply(null, slice.concat([0]));
      var plot = indexMode ? slice.map(function (value) { return peak ? value / peak * 100 : 0; }) : slice;
      return { item: item, slice: slice, plot: plot, color: colors[order % colors.length], last: slice[slice.length - 1] };
    });
    var flat = [];
    prepared.forEach(function (line) { flat = flat.concat(line.plot); });
    var min = Math.min.apply(null, flat);
    var max = Math.max.apply(null, flat);
    if (min === max) { min = min - 1; max = max + 1; }
    if (!indexMode && min > 0) min = min - (max - min) * 0.08;
    if (min < 0 && Math.min.apply(null, flat) >= 0) min = 0;
    max = max + (max - min) * 0.08;
    function xAt(position) {
      if (months.length === 1) return left + plotW / 2;
      return left + plotW * position / (months.length - 1);
    }
    function yAt(value) { return top + plotH * (1 - (value - min) / (max - min)); }
    var parts = [];
    for (var tick = 0; tick < 4; tick += 1) {
      var value = min + (max - min) * tick / 3;
      var y = yAt(value);
      parts.push('<line x1="' + left + '" y1="' + y + '" x2="' + (W - right) + '" y2="' + y + '" stroke="#E4DDD6"/>');
      var axis = indexMode ? Math.round(value) : fmt(series[0].unit, value);
      parts.push('<text x="' + (left - 8) + '" y="' + (y + 4) + '" text-anchor="end" fill="#6F6862" font-size="11">' + axis + '</text>');
    }
    months.forEach(function (index, position) {
      parts.push('<text x="' + xAt(position) + '" y="' + (H - 10) + '" text-anchor="middle" fill="#6F6862" font-size="11">' + data.labels[index] + '</text>');
    });
    prepared.forEach(function (line) {
      var points = line.plot.map(function (value, position) { return xAt(position) + "," + yAt(value); }).join(" ");
      parts.push('<polyline fill="none" stroke="' + line.color + '" stroke-width="2.5" points="' + points + '"/>');
      line.plot.forEach(function (value, position) {
        var actual = fmt(line.item.unit, line.slice[position]);
        parts.push('<circle cx="' + xAt(position) + '" cy="' + yAt(value) + '" r="3.6" fill="' + line.color + '"><title>' + line.item.name + " " + data.full[months[position]] + " " + actual + '</title></circle>');
      });
    });
    svg.innerHTML = parts.join("");
    legend.innerHTML = prepared.map(function (line) {
      return '<span><i style="background:' + line.color + '"></i>' + line.item.name + " " + fmt(line.item.unit, line.last) + "</span>";
    }).join("");
    note.textContent = indexMode
      ? "These series are on different scales, so each line is drawn against its own peak in the checked months. 100 is that peak. The legend is the actual figure at the last checked month."
      : "The axis is the actual amount. The legend is the figure at the last checked month.";
  }
  document.getElementById("trend-filter").addEventListener("change", draw);
  var monthMenu = document.getElementById("trend-months");
  if (monthMenu) monthMenu.addEventListener("change", function () {
    draw();
    monthMenu.submit();
  });
  draw();
})();
</script>
"""
    return f"""
    <div class="card" style="margin-top:12px">
      <div class="label">Trend</div>
      <div class="dates" id="trend-filter">
        <div class="label">Series</div>
        {series_boxes}
      </div>
      <svg id="trend-svg" viewBox="0 0 760 280" role="img" aria-label="Portfolio trend"></svg>
      <div class="legend" id="trend-legend"></div>
      <p class="lead" id="trend-note"></p>
    </div>
    <script>window.TREND_DATA = {json.dumps(payload)};</script>
    {script}
    """


def page(title: str, active: str, body: str) -> bytes:
    nav = [
        ("dashboard", "Portfolio"),
        ("industry", "Industry review"),
        ("financial", "Financial and covenants"),
        ("repayment", "Repayment"),
        ("news", "Adverse news"),
        ("reports", "Report"),
        ("assistant", "Agent portal"),
        ("drafts", "Email portal"),
    ]
    links = []
    for key, label in nav:
        if key == "reports":
            opened = " open" if active in {"reports", "reports-external"} else ""
            current = " active" if active in {"reports", "reports-external"} else ""
            internal = "active" if active == "reports" else ""
            external = "active" if active == "reports-external" else ""
            links.append(
                f'<div class="nav-sub{opened}">'
                f'<button type="button" class="nav-parent{current}" aria-expanded="{"true" if opened else "false"}">Report</button>'
                f'<div class="nav-menu">'
                f'<a class="{internal}" href="/reports">Internal report</a>'
                f'<a class="{external}" href="/reports?source=external">External report</a>'
                f'</div></div>'
            )
            continue
        cls = "active" if key == active else ""
        links.append(f'<a class="{cls}" href="/{key}">{escape(label)}</a>')
    shown = dict(nav).get(title, title.replace("_", " ").title())
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(shown)} · BEA - Risk Intelligence</title>
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
.shell {{ display:grid; grid-template-columns:248px minmax(0,1fr); min-height:100vh; }}
nav {{ background:var(--rail); color:#E7E0D8; padding:22px 16px; position:sticky; top:0; height:100vh; overflow:auto; }}
.shell.collapsed {{ grid-template-columns:0 minmax(0,1fr); }}
.shell.collapsed nav {{ padding:0; overflow:hidden; }}
nav .mark {{ font-family:"Source Serif 4",serif; color:#fff; font-size:1.15rem; line-height:1.2; }}
nav .mark span {{ color:var(--orange); }}
nav p {{ color:#C8BEB4; font-size:.78rem; line-height:1.4; }}
nav a {{ display:block; color:#E7E0D8; padding:9px 10px; border-left:3px solid transparent; border-radius:8px; margin:2px 0; }}
nav a.active {{ background:rgba(227,111,30,.18); color:#fff; border-left-color:var(--orange); }}
nav button.nav-parent {{ display:block; width:100%; text-align:left; background:transparent; color:#E7E0D8; border:0; border-left:3px solid transparent; border-radius:8px; margin:2px 0; padding:9px 10px; font-weight:600; cursor:pointer; }}
nav button.nav-parent.active, .nav-sub.open > button.nav-parent {{ background:rgba(227,111,30,.18); color:#fff; border-left-color:var(--orange); }}
.nav-menu {{ display:none; margin:0 0 6px 14px; }}
.nav-sub.open .nav-menu {{ display:block; }}
.nav-menu a {{ font-size:.86rem; padding:7px 10px; }}
.sent-mail {{ padding:14px 0; border-top:1px solid var(--line); }}
.sent-mail:first-child {{ border-top:0; padding-top:0; }}
.sent-mail h2 {{ font-size:1.05rem; margin:4px 0 8px; }}
.sent-mail p {{ margin:2px 0; }}
.letter {{ white-space:pre-wrap; background:#fff; border:1px solid var(--line); border-radius:10px; padding:12px; margin-top:10px; font:14px/1.45 ui-monospace,monospace; }}
nav a.logout {{ margin-top:18px; color:#C8BEB4; }}
.nav-toggle {{ background:var(--rail); margin-bottom:12px; }}
.backdrop {{ display:none; }}
main {{ padding:28px 32px 64px; min-width:0; }}
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
tr.click:hover td, tr.news-item[data-open="1"] td {{ background:#FBF7F2; }}
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
label.draft-to {{ display:flex; gap:8px; align-items:center; max-width:560px; margin:12px 0; font-size:.78rem; font-weight:700; letter-spacing:.04em; text-transform:uppercase; color:var(--muted); }}
label.draft-to input {{ flex:1; min-width:0; font:inherit; font-weight:600; letter-spacing:0; text-transform:none; color:var(--ink); padding:10px 12px; border:1px solid var(--line); border-radius:8px; background:#fff; }}
.mail-list {{ display:grid; gap:0; }}
.mail-row {{ display:grid; grid-template-columns:minmax(0,1fr) auto; gap:8px 12px; align-items:center; padding:12px 0; border-bottom:1px solid var(--line); }}
.mail-row:first-child {{ padding-top:0; }}
.mail-subject {{ min-width:0; }}
.mail-subject strong {{ display:block; }}
.mail-subject span {{ display:block; color:var(--muted); font-size:.8rem; margin-top:2px; }}
.mail-send {{ display:flex; gap:8px; align-items:center; }}
.mail-send input {{ width:min(280px, 42vw); font:inherit; font-weight:600; padding:8px 10px; border:1px solid var(--line); border-radius:8px; background:#fff; color:var(--ink); }}
.mail-note {{ grid-column:1 / -1; margin:0; color:var(--red); font-size:.82rem; }}
.mail-note[hidden] {{ display:none; }}
.cite {{ font-size:.82rem; color:var(--muted); border-left:3px solid var(--orange); padding-left:10px; margin:8px 0; }}
form.inline {{ display:flex; gap:8px; flex-wrap:wrap; align-items:end; }}
.news-tools {{ display:flex; gap:12px; flex-wrap:wrap; align-items:end; justify-content:space-between; margin:8px 0 12px; }}
.news-filters {{ display:flex; gap:8px; flex-wrap:wrap; align-items:end; margin-left:auto; }}
select.sev {{ font:inherit; font-weight:700; font-size:.78rem; padding:4px 8px; border-radius:99px; max-width:9.5rem; }}
.sev-note {{ margin-left:6px; color:var(--muted); font-size:.75rem; }}
.sev-note[hidden] {{ display:none; }}
td.pick, th.pick {{ width:2.2rem; }}
td.pick input {{ width:auto; margin:4px 0 0; }}
textarea.action {{ display:block; width:100%; max-width:720px; min-height:120px; margin-top:4px; font-family:inherit; font:inherit; line-height:1.45; }}
.action-block {{ border-top:1px solid var(--line); margin-top:14px; padding-top:12px; }}
.action-block label {{ display:block; margin-top:8px; }}
.action-block select {{ display:block; width:100%; max-width:420px; margin-top:4px; }}
button.ghost {{ background:#F7F4F0; color:var(--ink); border:1px solid var(--line); }}
.news-read {{ color:var(--ink); line-height:1.55; display:grid; gap:14px; padding:6px 4px 10px; }}
.news-read p {{ margin:0; }}
.news-copy {{ max-width:78ch; }}
.news-read dl {{ display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:10px 18px; margin:0; }}
.news-read .label {{ margin-bottom:8px; }}
.news-read dt {{ font-size:.7rem; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); font-weight:700; }}
.news-read dl div.wide {{ grid-column:1 / -1; }}
.news-read dd {{ margin:2px 0 0; }}
.news-links {{ display:flex; flex-wrap:wrap; gap:8px 16px; }}
select, input[type=number] {{ font:inherit; padding:8px; border:1px solid var(--line); border-radius:8px; background:#fff; }}
form.dates {{ display:flex; flex-wrap:wrap; gap:8px 14px; align-items:center; background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px; margin-bottom:16px; }}
form.dates .label {{ width:100%; }}
form.dates label {{ display:flex; gap:6px; align-items:center; font-size:.84rem; font-weight:600; }}
form.dates input {{ width:auto; margin:0; }}
.topbar {{ display:flex; justify-content:space-between; align-items:flex-start; gap:12px; flex-wrap:wrap; }}
.date-menu {{ position:relative; display:inline-block; max-width:100%; margin-bottom:16px; }}
.date-menu.corner {{ margin-left:auto; margin-bottom:12px; }}
.date-toggle {{ display:block; min-width:280px; max-width:100%; background:var(--card); color:var(--ink); border:1px solid var(--line); text-align:left; }}
.date-toggle .label {{ display:block; }}
.date-toggle strong {{ display:block; font-size:1rem; margin-top:2px; }}
.date-panel {{ display:none; position:absolute; z-index:20; top:calc(100% + 6px); left:0; width:min(320px, 86vw); max-height:70vh; overflow:auto; background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px; box-shadow:0 12px 28px rgba(44,40,37,.14); }}
.date-menu.open .date-panel {{ display:block; }}
.date-menu.corner .date-panel {{ left:auto; right:0; }}
.date-menu.end {{ margin-top:18px; margin-bottom:0; }}
.date-menu.end .date-panel {{ top:auto; bottom:calc(100% + 6px); }}
.suggest {{ position:relative; max-width:560px; }}
form.hkex-search .suggest {{ flex:1 1 420px; min-width:min(420px, 100%); }}
form.hkex-search input[type=number] {{ width:7.5rem; }}
.suggest input {{ width:100%; font:inherit; padding:8px 10px; border:1px solid var(--line); border-radius:8px; margin-top:6px; }}
.suggest-list {{ position:absolute; z-index:30; left:0; right:0; top:calc(100% + 4px); background:#fff; border:1px solid var(--line); border-radius:12px; box-shadow:0 12px 28px rgba(44,40,37,.14); max-height:320px; overflow:auto; }}
.suggest-item {{ display:block; width:100%; text-align:left; background:#fff; color:var(--ink); border:0; border-bottom:1px solid var(--line); border-radius:0; padding:8px 12px; font-weight:600; }}
.suggest-item small {{ display:block; color:var(--muted); font-weight:400; }}
.date-panel label {{ display:flex; gap:8px; align-items:center; padding:5px 0; font-weight:600; }}
.date-panel input {{ width:auto; margin:0; }}
.date-panel .hint {{ color:var(--muted); font-size:.82rem; }}
.date-actions {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; }}
.date-panel button.ghost {{ background:#F7F4F0; color:var(--ink); border:1px solid var(--line); }}
.trend-chart, #trend-svg {{ width:100%; height:auto; display:block; }}
.legend {{ display:flex; flex-wrap:wrap; gap:10px 16px; margin-top:8px; font-size:.84rem; }}
.legend i {{ display:inline-block; width:10px; height:10px; border-radius:99px; margin-right:6px; }}
.scroll {{ overflow-x:auto; }}
body.news-lock {{ height:100vh; overflow:hidden; }}
body.news-lock .shell {{ height:100vh; min-height:0; }}
body.news-lock main {{ height:100vh; overflow:hidden; display:flex; flex-direction:column; padding-bottom:16px; }}
.news-screen {{ display:flex; flex-direction:column; min-height:0; }}
body.news-lock .news-screen {{ flex:1; }}
.news-screen .lead {{ max-width:none; margin:0 0 10px; }}
.news-boards {{ min-height:0; display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
body.news-lock .news-boards {{ flex:1; grid-template-rows:minmax(0, 1fr); }}
.news-board {{ min-height:0; display:flex; flex-direction:column; background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px 14px; }}
.news-board h2 {{ margin:0 0 4px; font-size:1.15rem; }}
.news-board .news-tools {{ margin:8px 0; }}
.news-board .news-filters, .mail-tools .news-filters {{ margin-left:0; }}
.news-scroll {{ min-height:0; overflow-y:scroll; border:1px solid var(--line); border-radius:10px; background:#fff; }}
body.news-lock .news-scroll {{ flex:1; }}
.news-scroll thead th {{ position:sticky; top:0; background:#fff; z-index:1; }}
tr[hidden], .sent-mail[hidden] {{ display:none !important; }}
@media (max-width:900px) {{
  .news-boards {{ grid-template-columns:1fr; grid-template-rows:minmax(0, 1fr) minmax(0, 1fr); }}
}}
table.trend th, table.trend td {{ white-space:nowrap; }}
table.trend th {{ font-size:.78rem; letter-spacing:0; text-transform:none; }}
@media (max-width:900px) {{
  .shell {{ display:block; }}
  nav {{
    position:fixed; z-index:30; left:0; top:0; bottom:0; width:min(280px,86vw); height:auto;
    box-shadow:8px 0 24px rgba(0,0,0,.25);
  }}
  .shell.collapsed nav {{ transform:translateX(-105%); padding:22px 16px; width:min(280px,86vw); overflow:auto; }}
  .backdrop {{ position:fixed; inset:0; background:rgba(44,40,37,.35); z-index:25; }}
  .shell:not(.collapsed) .backdrop {{ display:block; }}
  .metrics, .grid, .grid3, .news-read dl, .mail-row {{ grid-template-columns:1fr; }}
  .mail-send input {{ flex:1; width:auto; min-width:0; }}
  main {{ padding:16px 16px 72px; }}
}}
</style>
</head>
<body{" class=\"news-lock\"" if active == "news" else ""}>
<div class="shell" id="shell">
  <nav id="rail">
    <div class="mark">BEA -<br><span>Risk Intelligence</span></div>
    <p>Portfolio numbers follow the last checked month. Other pages keep the date choice in a menu.</p>
    {''.join(links)}
    <a class="logout" href="/logout">Sign out</a>
  </nav>
  <div class="backdrop" id="backdrop"></div>
  <main>
    <div class="topbar">
      <button type="button" class="nav-toggle" id="nav-toggle" aria-controls="rail">Hide menu</button>
      {chart_month_menu() if active == "dashboard" else ""}
    </div>
    <div class="banner">{escape(BOOK["banner"])}</div>
    {"" if active in {"dashboard", "news", "reports-external"} else date_bar()}
    {body}
  </main>
</div>
<script>
(function () {{
  var shell = document.getElementById("shell");
  var toggle = document.getElementById("nav-toggle");
  var narrow = window.matchMedia("(max-width: 900px)").matches;
  function apply(collapsed) {{
    shell.classList.toggle("collapsed", collapsed);
    toggle.textContent = collapsed ? "Menu" : "Hide menu";
    toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
  }}
  apply(narrow ? true : localStorage.getItem("rip-nav") === "1");
  toggle.addEventListener("click", function () {{
    var collapsed = !shell.classList.contains("collapsed");
    apply(collapsed);
    if (!narrow) localStorage.setItem("rip-nav", collapsed ? "1" : "0");
  }});
  document.getElementById("backdrop").addEventListener("click", function () {{ apply(true); }});
  var reportMenu = document.querySelector(".nav-sub");
  if (reportMenu) {{
    var reportButton = reportMenu.querySelector(".nav-parent");
    reportButton.addEventListener("click", function () {{
      var open = reportMenu.classList.toggle("open");
      reportButton.setAttribute("aria-expanded", open ? "true" : "false");
    }});
  }}
  var menu = document.querySelector(".date-menu");
  if (menu) {{
    var dateToggle = menu.querySelector(".date-toggle");
    dateToggle.addEventListener("click", function () {{
      var open = menu.classList.toggle("open");
      dateToggle.setAttribute("aria-expanded", open ? "true" : "false");
    }});
    document.addEventListener("click", function (event) {{
      if (!menu.contains(event.target)) {{
        menu.classList.remove("open");
        dateToggle.setAttribute("aria-expanded", "false");
      }}
    }});
  }}
}})();
</script>
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
            f'<div style="display:grid;grid-template-columns:minmax(168px,240px) 1fr 176px;gap:8px;align-items:center;margin:8px 0">'
            f'<div>{escape(label)}</div><div class="bar {"hot" if hot else ""}"><span style="width:{width}%"></span></div>'
            f'<div style="text-align:right;color:var(--muted);white-space:nowrap">{money(value)}</div></div>'
        )
    return "".join(lines)


def dashboard() -> str:
    iso = view().focus
    port = portfolio_at(iso)
    position = view().label(iso)
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
    industry_rows = [(row["industry"], row["drawn_hkd"]) for row in port["industries"][:6]]
    present = [row for row in (customer_at(item["customer_id"], iso) for item in BOOK["customers"]) if row]
    top = sorted(present, key=lambda row: row["drawn_hkd"], reverse=True)[:8]
    table = "".join(
        f'<tr class="click"><td><a href="/customer?id={escape(row["customer_id"])}">{escape(row["legal_name"])}</a><div style="color:var(--muted);font-size:.8rem">{escape(row["rm"])}</div></td>'
        f'<td>{escape(row["industry"])}</td><td>Stage {row["stage"]}</td>'
        f'<td>{row["prior_rating"]} → {row["rating"]}</td><td>{money(row["drawn_hkd"])}</td>'
        f'<td>{row["dpd"]}</td></tr>'
        for row in top
    )
    body = f"""
    <div class="label">Portfolio</div><h1>Management dashboard</h1>
    <p class="lead">The number panels are {escape(position)}, the last checked month. The chart draws every checked month, and its legend is that same month. Financial statements, covenants and the news headlines are still demonstration figures.</p>
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
      <div class="card"><div class="label">Largest industries</div>{bars(industry_rows, hot=True)}<p><a href="/industry?name={escape(default_industry())}">Open the {escape(default_industry())} review</a></p></div>
      <div class="card"><div class="label">ECL and LTV</div>
        <p>ECL coverage of drawn exposure is {port["ecl_coverage"]:.2%}. ECL movement versus the previous month-end is {money(port["ecl_hkd"] - port["prior_ecl_hkd"])}.</p>
        <p>Portfolio LTV is exposure divided by recorded collateral. Open a customer to see the ratio used in news materiality.</p>
      </div>
    </div>
    <div class="card" style="margin-top:12px">
      <div class="label">Largest names</div>
      <table><thead><tr><th>Customer</th><th>Industry</th><th>Stage</th><th>Rating</th><th>Drawn</th><th>DPD</th></tr></thead><tbody>{table}</tbody></table>
    </div>
    {trend_chart()}"""
    return body


def news_stamp(text: str) -> int:
    for fmt in ("%d %b %Y", "%b %Y"):
        try:
            return int(datetime.strptime(text, fmt).timestamp())
        except ValueError:
            continue
    return 0


def news_fields(body: str) -> tuple[str, dict[str, str]]:
    marker = " News type: "
    if marker not in body:
        return body, {}
    article, rest = body.split(marker, 1)
    found = re.match(
        r"(?P<news_type>.*?)\. Signal: (?P<signal>.*?)\. Severity: (?P<severity>.*?)\. Entities: (?P<entities>.*)\.\s*$",
        rest,
        re.S,
    )
    if not found:
        return body, {}
    return article.strip(), found.groupdict()


def news_facts(pairs: list[tuple[str, str]]) -> str:
    wide = {"Entities", "Signal", "Financial strength", "Collateral"}
    rows = "".join(
        f'<div{ " class=\"wide\"" if label in wide else ""}><dt>{escape(label)}</dt><dd>{value}</dd></div>'
        for label, value in pairs
    )
    return f"<dl>{rows}</dl>"


def news_detail(item: dict) -> str:
    article, fields = news_fields(item["body"])
    factors = item["factors"]
    file_rows = [
        ("News type", escape(fields.get("news_type", ""))),
        ("Signal", escape(fields.get("signal", ""))),
        ("Severity", f'<span class="sev-live">{escape(item["severity"])}</span>'),
        ("Entities", escape(fields.get("entities", ""))),
    ]
    book_rows = [
        ("Exposure", money(factors["exposure_hkd"])),
        ("Coverage", escape(str(factors["security_coverage"]))),
        ("Guarantor", escape(str(factors["guarantor_support"]))),
        ("Financial strength", escape(str(factors["financial_strength"]))),
        ("Warnings", escape(str(factors["warning_signals"]))),
    ]
    if item["customer_id"]:
        person = customer(item["customer_id"])
        book_rows = [
            ("Borrower", escape(person["legal_name"])),
            ("Rating", escape(f"{person['prior_rating']} to {person['rating']}")),
            ("Collateral", f"{escape(person['collateral_type'])} {money(person['collateral_hkd'])}"),
            ("Relationship manager", escape(person["rm"])),
            ("Drawn", money(person["drawn_hkd"])),
            ("ECL", money(person["ecl_hkd"])),
            ("Stage", escape(str(person["stage"]))),
            ("Days past due", escape(str(person["dpd"]))),
            *book_rows,
        ]
        mail_link = f'<a href="/drafts#sent-{escape(item["id"])}">Open the message sent to the relationship manager</a>' if item["severity"] == "CRITICAL" else ""
        links = (
            f'{mail_link}'
            f'<a href="/industry?name={escape(person["industry"])}">Continue to the {escape(person["industry"])} industry review</a>'
        )
    else:
        links = (
            f'<a href="/industry?name={escape(item["industry"])}">Continue to the {escape(item["industry"])} review</a>'
            f'<a href="/email?id=MAIL-IND-WHOLESALE">Open the industry email draft</a>'
        )
    file_block = f'<div><div class="label">From the file</div>{news_facts(file_rows)}</div>' if fields else ""
    return (
        f'<div class="news-read"><p class="news-copy">{escape(article)}</p>{file_block}'
        f'<div><div class="label">On the book</div>{news_facts(book_rows)}</div>'
        f'<p class="news-links">{links}</p></div>'
    )


ACTION_NOTES = {
    "ready": "Actions for the selected headlines are below. Edit the wording, then confirm to add them to the borrower report.",
    "saved": "Edits are saved on this page. They stay out of the report until you confirm.",
    "added": "A summary of the selected news is now in section 7, and a summary of the actions is under section 9, of the borrower monitoring report.",
    "choose": "Choose a borrower and keep the wording for each action before adding it to a report. The edits were saved.",
    "pick": "Select at least one headline, then generate actions.",
}


def obligor_name(cid: str) -> str:
    found = next((item for item in OBLIGORS if item["id"] == cid), None)
    if found:
        return found["name"]
    raw = next((row for row in BOOK["customers"] if row["customer_id"] == cid), None)
    return raw["legal_name"] if raw else ""


def borrower_options(selected: str) -> str:
    options = ['<option value="">Choose a borrower</option>']
    for item in OBLIGORS:
        mark = " selected" if item["id"] == selected else ""
        options.append(f'<option value="{escape(item["id"])}"{mark}>{escape(item["name"])}</option>')
    return "".join(options)


def action_desk(note: str) -> str:
    state = news_desk.load_state()
    known = {item["id"]: item for item in BOOK["news"]}
    order = {item["id"]: index for index, item in enumerate(BOOK["news"])}
    records = [(news_id, record) for news_id, record in state["actions"].items() if news_id in known and isinstance(record, dict)]
    records.sort(key=lambda pair: order[pair[0]])
    message = ACTION_NOTES.get(note, "")
    message_html = f"<p><strong>{escape(message)}</strong></p>" if message else ""
    confirmed: list[str] = []
    for _, record in records:
        cid = record.get("confirmed_customer_id") or ""
        if record.get("confirmed_text") and cid and cid not in confirmed:
            confirmed.append(cid)
    links = " ".join(
        f'<a href="/report-file?id={escape(cid)}">Download the {escape(obligor_name(cid))} report</a>'
        for cid in confirmed
    )
    link_html = f'<p class="news-links">{links}</p>' if links else ""
    intro = (
        "Select one or more headlines, then generate actions. Edit the wording here. "
        "Confirm summarises the selected news into section 7, Other Market News, and summarises the actions under section 9, Suggested Action Plan. "
        "The rest of that report stays in place. The annual-review proposal is left unchanged."
    )
    if not records:
        return f"""
        <div class="card" id="action-desk" style="margin-top:12px">
          <div class="label">Actions</div>
          <p>{intro}</p>
          {message_html}
        </div>"""
    blocks = []
    for news_id, record in records:
        item = known[news_id]
        customer_id = record.get("customer_id") or ""
        confirmed_customer = record.get("confirmed_customer_id") or ""
        confirmed_text = record.get("confirmed_text") or ""
        text = record.get("text") or ""
        if confirmed_text and confirmed_text == text and confirmed_customer == customer_id:
            status = f"In the {obligor_name(confirmed_customer)} report."
        elif confirmed_text:
            status = f"The {obligor_name(confirmed_customer)} report still has the previous wording until you confirm this edit."
        else:
            status = "Draft. Not in a report yet."
        blocks.append(
            "<div class=\"action-block\">"
            f'<input type="hidden" name="news_id" value="{escape(news_id)}">'
            f"<p><strong>{escape(item['headline'])}</strong><br>"
            f'<span style="color:var(--muted)">{escape(item["date"])} · {escape(item["source"])} · {escape(item["severity"])}</span></p>'
            f'<label>Borrower<br><select name="customer_{escape(news_id)}">{borrower_options(customer_id)}</select></label>'
            f'<label>Action<br><textarea class="action" name="text_{escape(news_id)}">{escape(text)}</textarea></label>'
            f'<p class="lead">{escape(status)}</p></div>'
        )
    return f"""
    <div class="card" id="action-desk" style="margin-top:12px">
      <div class="label">Actions</div>
      <p>{intro}</p>
      {message_html}{link_html}
      <form method="post" action="/news-actions">
        {''.join(blocks)}
        <p class="date-actions">
          <button type="submit" class="ghost" name="intent" value="save">Save edits</button>
          <button type="submit" name="intent" value="confirm">Confirm and add to the report</button>
        </p>
      </form>
    </div>"""


def confirmed_report_actions(state: dict, customer_id: str) -> list[dict]:
    rows = []
    for item in BOOK["news"]:
        record = state["actions"].get(item["id"]) or {}
        if not isinstance(record, dict) or record.get("confirmed_customer_id") != customer_id:
            continue
        text = (record.get("confirmed_text") or "").strip()
        if not text:
            continue
        rows.append({
            "headline": item["headline"],
            "severity": record.get("confirmed_severity") or item["severity"],
            "source": item["source"],
            "date": item["date"],
            "text": text,
        })
    return rows


def rebuild_reports(customer_ids: set[str]) -> None:
    state = news_desk.load_state()
    for customer_id in sorted(customer_ids):
        raw = next((row for row in BOOK["customers"] if row["customer_id"] == customer_id), None)
        folder = REPORT_FILES / "obligors" / customer_id
        if raw is None or not folder.is_dir():
            continue
        build_obligor_reports.save_report(raw, raw["history"][-1], confirmed_report_actions(state, customer_id), folder / "report.docx")


def handle_news_form(form: dict[str, list[str]]) -> str:
    intent = (form.get("intent") or ["generate"])[0]
    known = {item["id"]: item for item in BOOK["news"]}
    obligor_ids = {item["id"] for item in OBLIGORS}
    borrowers = {row["customer_id"]: row for row in BOOK["customers"]}
    if intent == "generate":
        chosen = [known[item] for item in form.get("ids", []) if item in known]
        if not chosen:
            return "pick"

        def generate(state: dict) -> None:
            for item in chosen:
                record = state["actions"].get(item["id"])
                if not isinstance(record, dict):
                    record = {}
                customer_id = record.get("customer_id") or news_desk.suggest_customer(item, BOOK["customers"])
                if customer_id not in obligor_ids:
                    customer_id = ""
                record["customer_id"] = customer_id
                record["text"] = news_desk.draft_action(item, borrowers.get(customer_id))
                state["actions"][item["id"]] = record

        news_desk.update_state(generate)
        return "ready"
    posted = []
    for news_id in form.get("news_id", []):
        if news_id not in known:
            continue
        customer_id = (form.get(f"customer_{news_id}") or [""])[0]
        if customer_id not in obligor_ids:
            customer_id = ""
        text = news_desk.clean_text((form.get(f"text_{news_id}") or [""])[0])
        posted.append((news_id, customer_id, text))
    if not posted:
        return "pick"

    def store_drafts(state: dict) -> None:
        for news_id, customer_id, text in posted:
            record = state["actions"].get(news_id)
            if not isinstance(record, dict):
                record = {}
            record["customer_id"] = customer_id
            record["text"] = text
            state["actions"][news_id] = record

    if intent != "confirm":
        news_desk.update_state(store_drafts)
        return "saved"
    if any(not customer_id or not text for _, customer_id, text in posted):
        news_desk.update_state(store_drafts)
        return "choose"
    touched: set[str] = set()

    def confirm(state: dict) -> None:
        for news_id, customer_id, text in posted:
            record = state["actions"].get(news_id)
            if not isinstance(record, dict):
                record = {}
            previous = record.get("confirmed_customer_id") or ""
            if previous:
                touched.add(previous)
            record["customer_id"] = customer_id
            record["text"] = text
            record["confirmed_text"] = text
            record["confirmed_customer_id"] = customer_id
            record["confirmed_severity"] = known[news_id]["severity"]
            state["actions"][news_id] = record
            touched.add(customer_id)

    news_desk.update_state(confirm)
    rebuild_reports(touched)
    return "added"


def news_action_form(item: dict) -> str:
    state = news_desk.load_state()
    record = state["actions"].get(item["id"]) if isinstance(state["actions"].get(item["id"]), dict) else {}
    customer_id = (record or {}).get("customer_id") or item.get("customer_id") or ""
    raw = next((row for row in BOOK["customers"] if row["customer_id"] == customer_id), None)
    text = (record or {}).get("text") or news_desk.draft_action(item, raw)
    confirmed = (record or {}).get("confirmed_text") or ""
    confirmed_customer = (record or {}).get("confirmed_customer_id") or ""
    if confirmed and confirmed == text and confirmed_customer == customer_id:
        status = f"In the {obligor_name(confirmed_customer)} report."
    elif confirmed:
        status = "Saved here. The report still has the previous wording until you confirm."
    else:
        status = "Draft. Not in a report yet."
    return (
        '<div class="action-block">'
        f'<div class="label">Action</div>'
        f'<form method="post" action="/news-actions">'
        f'<input type="hidden" name="news_id" value="{escape(item["id"])}">'
        f'<label>Borrower<br><select name="customer_{escape(item["id"])}">{borrower_options(customer_id)}</select></label>'
        f'<label>Action<br><textarea class="action" name="text_{escape(item["id"])}">{escape(text)}</textarea></label>'
        f'<p class="lead">{escape(status)}</p>'
        '<p class="date-actions"><button type="submit" class="ghost" name="intent" value="save">Save edits</button>'
        '<button type="submit" name="intent" value="confirm">Confirm and add to the report</button></p>'
        '</form></div>'
    )


INDUSTRY_NEWS = {"Sector Related News", "General News"}


def news_group(item: dict) -> str:
    return "industry" if item.get("news_type") in INDUSTRY_NEWS else "obligor"


def news_borrower_name(item: dict) -> str:
    person = customer(item.get("customer_id") or "")
    if person:
        return person["legal_name"]
    entities = [part.strip() for part in str(item.get("entities") or "").split(",") if part.strip()]
    return entities[0] if entities else "Not named"


def news_industry_name(item: dict) -> str:
    if item.get("customer_id"):
        label = item.get("industry") or ""
        if label and label != "Not linked on the book":
            return label
    text = item.get("headline") or ""
    if "水" in text:
        return "Public Utilities"
    if "基建" in text:
        return "Transportation & Infrastructure"
    if "公用" in text:
        return "Public Utilities"
    return "Unclassified"


def news_page(note: str = "") -> str:
    grouped = {"obligor": [], "industry": []}
    for order, item in enumerate(BOOK["news"]):
        grouped[news_group(item)].append((order, item))

    def rows_for(kind: str) -> str:
        rows = []
        for order, item in grouped[kind]:
            factors = item["factors"]
            flag = '<span class="tag tag-red">Material</span>' if factors["material"] else '<span class="tag tag-grey">Below threshold</span>'
            levels = "".join(
                f'<option{" selected" if item["severity"] == level else ""}>{level}</option>'
                for level in news_desk.SEVERITIES
            )
            borrower = news_borrower_name(item)
            industry = news_industry_name(item)
            label = borrower if kind == "obligor" else industry
            rows.append(
                f'<tr class="news-item click" data-order="{order}" data-severity="{escape(item["severity"])}" data-time="{news_stamp(item["date"])}" data-borrower="{escape(borrower)}" data-industry="{escape(industry)}">'
                f'<td>{escape(item["headline"])}'
                f'<div style="color:var(--muted);font-size:.8rem">{escape(item["date"])} · {escape(item["source"])}</div></td>'
                f'<td>{escape(label)}</td>'
                f'<td><select class="sev" data-id="{escape(item["id"])}" data-saved="{escape(item["severity"])}" aria-label="Severity">{levels}</select> <span class="sev-note" hidden>Saved</span></td>'
                f'<td>{flag}</td></tr>'
                f'<tr class="news-detail" hidden><td colspan="4">{news_detail(item)}{news_action_form(item)}</td></tr>'
            )
        return "".join(rows)

    def choices(kind: str, field: str) -> str:
        names = sorted({(news_borrower_name(item) if field == "borrower" else news_industry_name(item)) for _, item in grouped[kind]})
        return "".join(f"<option>{escape(name)}</option>" for name in names)

    def board(kind: str, title: str, column: str, field: str) -> str:
        return f"""
        <section class="news-board" data-filter="{field}">
          <h2>{title}</h2>
          <div class="news-tools">
            <div class="news-filters">
              <label><span class="label">{column}</span><br>
                <select class="board-filter"><option value="">All</option>{choices(kind, field)}</select>
              </label>
              <label><span class="label">Severity</span><br>
                <select class="severity-filter">
                  <option value="">All</option>
                  <option>CRITICAL</option>
                  <option>HIGH</option>
                  <option>MEDIUM</option>
                  <option>LOW</option>
                </select>
              </label>
              <label><span class="label">Sort</span><br>
                <select class="news-sort">
                  <option value="listed">As listed</option>
                  <option value="severity-desc">Severity, high to low</option>
                  <option value="severity-asc">Severity, low to high</option>
                  <option value="date-desc">Date, newest</option>
                  <option value="date-asc">Date, oldest</option>
                </select>
              </label>
            </div>
          </div>
          <div class="news-scroll"><table><thead><tr><th>Item</th><th>{column}</th><th>Severity</th><th></th></tr></thead>
            <tbody>{rows_for(kind)}<tr class="news-empty" hidden><td colspan="4">No news matches this filter.</td></tr></tbody>
          </table></div>
        </section>"""
    message = ACTION_NOTES.get(note, "")
    message_html = f"<p><strong>{escape(message)}</strong></p>" if message else ""
    return f"""
    <div class="news-screen">
    <div class="label">Adverse news</div><h1>Adverse news</h1>
    <p class="lead">Adverse news is a daily update. Obligor related news is filtered by borrower. Industry news is filtered by industry. Click a headline to open the article and its action. Severity changes save immediately.</p>
    {message_html}
    <div class="news-boards">
      {board("obligor", "Obligor related news", "Borrower", "borrower")}
      {board("industry", "Industry news", "Industry", "industry")}
    </div>
    </div>
    <script>
    (function () {{
      var rank = {{"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}};
      document.querySelectorAll(".news-board").forEach(function (board) {{
        var key = board.dataset.filter;
        var filter = board.querySelector(".board-filter");
        var severity = board.querySelector(".severity-filter");
        var sort = board.querySelector(".news-sort");
        var body = board.querySelector("tbody");
        var empty = board.querySelector(".news-empty");
        function pairs() {{
          return [...body.querySelectorAll("tr.news-item")].map(function (row) {{
            return {{row: row, detail: row.nextElementSibling}};
          }});
        }}
        function apply() {{
          var want = severity.value;
          var named = filter.value;
          var mode = sort.value;
          var items = pairs();
          items.sort(function (a, b) {{
            if (mode === "severity-desc") return (rank[b.row.dataset.severity] - rank[a.row.dataset.severity]) || (Number(a.row.dataset.order) - Number(b.row.dataset.order));
            if (mode === "severity-asc") return (rank[a.row.dataset.severity] - rank[b.row.dataset.severity]) || (Number(a.row.dataset.order) - Number(b.row.dataset.order));
            if (mode === "date-desc") return Number(b.row.dataset.time) - Number(a.row.dataset.time);
            if (mode === "date-asc") return Number(a.row.dataset.time) - Number(b.row.dataset.time);
            return Number(a.row.dataset.order) - Number(b.row.dataset.order);
          }});
          var shown = 0;
          items.forEach(function (item) {{
            var visible = (!want || item.row.dataset.severity === want) && (!named || item.row.dataset[key] === named);
            item.row.hidden = !visible;
            item.detail.hidden = !visible || item.row.dataset.open !== "1";
            if (visible) shown += 1;
            body.appendChild(item.row);
            body.appendChild(item.detail);
          }});
          empty.hidden = shown > 0;
          body.appendChild(empty);
        }}
        board.addEventListener("news-refresh", apply);
        body.addEventListener("click", function (event) {{
          if (event.target.closest("select, input, button, a, textarea, label")) return;
          var row = event.target.closest("tr.news-item");
          if (!row) return;
          var detail = row.nextElementSibling;
          var open = row.dataset.open !== "1";
          row.dataset.open = open ? "1" : "";
          detail.hidden = !open;
          if (open) detail.scrollIntoView({{block: "nearest"}});
        }});
        filter.addEventListener("change", apply);
        severity.addEventListener("change", apply);
        sort.addEventListener("change", apply);
      }});
      document.addEventListener("change", function (event) {{
        var select = event.target.closest("select.sev");
        if (!select) return;
        var row = select.closest("tr.news-item");
        var board = select.closest(".news-board");
        var previous = select.dataset.saved || row.dataset.severity;
        var chosen = select.value;
        var note = select.parentElement.querySelector(".sev-note");
        fetch("/news-severity", {{
          method: "POST",
          headers: {{"Content-Type": "application/x-www-form-urlencoded"}},
          credentials: "same-origin",
          body: "id=" + encodeURIComponent(select.dataset.id) + "&severity=" + encodeURIComponent(chosen)
        }}).then(function (response) {{
          if (!response.ok) throw new Error("save");
          return response.json();
        }}).then(function () {{
          row.dataset.severity = chosen;
          select.dataset.saved = chosen;
          var live = row.nextElementSibling.querySelector(".sev-live");
          if (live) live.textContent = chosen;
          note.hidden = false;
          note.textContent = "Saved";
          setTimeout(function () {{ note.hidden = true; }}, 1200);
          board.dispatchEvent(new Event("news-refresh"));
        }}).catch(function () {{
          select.value = previous;
          note.hidden = false;
          note.textContent = "Not saved";
        }});
      }});
    }})();
    </script>"""


def industry_on(iso: str, name: str) -> dict:
    point = next(item for item in view().portfolio_series() if item["date"] == iso)
    found = next((item for item in point["industries"] if item["industry"] == name), None)
    if found:
        return found
    return {
        "industry": name,
        "drawn_hkd": 0,
        "ecl_hkd": 0,
        "stage2": 0,
        "migrations": 0,
        "dpd_accounts": 0,
        "collateral_hkd": 0,
    }


def industry_page(name: str) -> str:
    port = view().portfolio()
    row = next((item for item in port["industries"] if item["industry"] == name), port["industries"][0])
    members = [
        person for person in (customer(item["customer_id"]) for item in BOOK["customers"] if item["industry"] == row["industry"])
        if person and person.get("on_position", True)
    ]
    members.sort(key=lambda item: item["drawn_hkd"], reverse=True)
    open_warnings = sum(len(item["warnings"]) for item in members)
    body_rows = "".join(
        f'<tr><td><a href="/customer?id={escape(item["customer_id"])}">{escape(item["legal_name"])}</a></td>'
        f'<td>{item["prior_rating"]} → {item["rating"]}</td><td>Stage {item["stage"]}</td>'
        f'<td>{money(item["drawn_hkd"])}</td><td>{item["coverage_ratio"]}</td><td>{len(item["warnings"])}</td>'
        f'<td>{item["dpd"]}</td></tr>'
        for item in members
    )
    options = "".join(
        f'<option {"selected" if item["industry"]==row["industry"] else ""}>{escape(item["industry"])}</option>'
        for item in port["industries"]
    )
    return f"""
    <div class="label">Industry</div><h1>{escape(row["industry"])}</h1>
    <p class="lead">Position {escape(view().label())}. Signals use this industry's drawn exposure, ECL and days past due at that date. The trend follows the checked dates.</p>
    <form class="inline" method="get" action="/industry"><label>Industry<br><select name="name" onchange="this.form.submit()">{options}</select></label></form>
    {metrics([
        ("Drawn", money(row["drawn_hkd"]), False),
        ("Stage 2 names", str(row["stage2"]), True),
        ("Migrations", str(row["migrations"]), row["migrations"] > 0),
        ("Open warnings", str(open_warnings), open_warnings > 0),
    ])}
    <div class="card">
      <table><thead><tr><th>Customer</th><th>Rating</th><th>Stage</th><th>Drawn</th><th>Coverage</th><th>Warnings</th><th>DPD</th></tr></thead>
      <tbody>{body_rows}</tbody></table>
    </div>
    <div class="card" style="margin-top:12px"><div class="label">Trend across the checked dates</div>
      {trend_table([
        ("Drawn", lambda iso, industry=row["industry"]: money(industry_on(iso, industry)["drawn_hkd"])),
        ("ECL", lambda iso, industry=row["industry"]: money(industry_on(iso, industry)["ecl_hkd"])),
        ("Stage 2 names", lambda iso, industry=row["industry"]: str(industry_on(iso, industry)["stage2"])),
        ("Names past due", lambda iso, industry=row["industry"]: str(industry_on(iso, industry)["dpd_accounts"])),
        ("Collateral", lambda iso, industry=row["industry"]: money(industry_on(iso, industry)["collateral_hkd"])),
      ])}
    </div>
    <p><a class="btn" href="/email?id=MAIL-IND-WHOLESALE">Open the industry email draft</a></p>
    """


def repayment_threshold(raw: str | None) -> int:
    text = str(raw or "").replace(",", "").strip()
    if not text:
        return THRESHOLD
    try:
        value = int(float(text))
    except ValueError:
        return THRESHOLD
    if value < 0:
        return THRESHOLD
    return min(value, 100_000_000_000)


def repayment_page(window: int, threshold: int = THRESHOLD) -> str:
    people = [person for person in (customer(item["customer_id"]) for item in BOOK["customers"]) if person and person.get("on_position", True)]
    rows = []
    for item in people:
        if item["next_due_hkd"] < threshold or item["next_due_days"] > window:
            continue
        rows.append(item)
    rows.sort(key=lambda item: item["next_due_days"])
    lines = []
    for item in rows:
        draft = (
            f'<a href="/email?id={escape(item["repay_draft_id"])}">Draft</a>'
            if item.get("repay_draft_id")
            else "—"
        )
        kind = "Refinancing" if item["refinancing"] else "Instalment"
        lines.append(
            f'<tr><td><a href="/customer?id={escape(item["customer_id"])}">{escape(item["legal_name"])}</a>'
            f'<div style="color:var(--muted);font-size:.8rem">{escape(item["rm"])} · {escape(item["group_name"])}</div></td>'
            f'<td>{money(item["next_due_hkd"])}</td><td>{item["next_due_days"]} days</td>'
            f'<td>{escape(item["next_due_source"])}</td><td>{kind}</td><td>{draft}</td></tr>'
        )
    body = "".join(lines) or f'<tr><td colspan="6">No obligation above {escape(money(threshold))} falls in this window.</td></tr>'
    ageing = "".join(
        f'<tr><td><a href="/customer?id={escape(item["customer_id"])}">{escape(item["legal_name"])}</a></td><td>{item["dpd"]}</td><td>{escape(item["dpd_component"])}</td><td>{money(item["drawn_hkd"])}</td></tr>'
        for item in sorted(people, key=lambda row: row["dpd"], reverse=True)
        if item["dpd"] > 0
    )
    return f"""
    <div class="label">Repayment</div><h1>Obligations above {escape(money(threshold))}</h1>
    <p class="lead">Position {escape(view().label())}. Due dates and amounts are the next principal on that date's cash flow schedule. The threshold starts at HKD 5,000,000 and can be changed. The window is {window} days. Days past due follow the same position, and the trend shows how both move across the checked dates.</p>
    <form class="inline" method="get" action="/repayment">
      <label>Threshold (HKD)<br><input type="number" name="threshold" min="0" step="1000000" value="{threshold}"></label>
      <label>Window (days)<br><input type="number" name="window" min="7" max="365" value="{window}"></label>
      <button type="submit">Apply</button>
      <a class="btn ghost" href="/repayment?window=31&threshold={threshold}">One month</a>
      <a class="btn ghost" href="/repayment?window=92&threshold={threshold}">One quarter</a>
    </form>
    <div class="card" style="margin-top:12px"><table><thead><tr><th>Customer</th><th>Amount</th><th>Due</th><th>Source</th><th>Type</th><th></th></tr></thead><tbody>{body}</tbody></table></div>
    <div class="card" style="margin-top:12px"><div class="label">Approaching 30, 60, 90 and 180 days</div>
      <table><thead><tr><th>Customer</th><th>DPD</th><th>Component</th><th>Drawn</th></tr></thead><tbody>{ageing}</tbody></table>
      <p><a href="/email?id=MAIL-DPD-LANTERN">Open the days-past-due draft</a></p>
    </div>
    <div class="card" style="margin-top:12px"><div class="label">Days past due across the checked dates</div>
      {trend_table([(item["legal_name"], lambda iso, cid=item["customer_id"]: str(customer(cid)["series"][view().dates.index(iso)]["dpd"])) for item in people if any(point["dpd"] > 0 for point in item["series"])])}
    </div>
    <div class="card" style="margin-top:12px"><div class="label">Next principal across the checked dates</div>
      {trend_table([(item["legal_name"], lambda iso, cid=item["customer_id"]: money(customer(cid)["series"][view().dates.index(iso)]["next_due_hkd"]) + " on " + customer(cid)["series"][view().dates.index(iso)]["next_due_date"]) for item in people])}
    </div>"""


def financial_page(cid: str, scenario: str) -> str:
    row = customer(cid) or customer(default_customer_id())
    projected = project(row, scenario)
    latest = row["interest_coverage"][-1]
    threshold = row["coverage_threshold"]
    if latest is None or threshold is None:
        status = "Not on file"
        scenario_status = "Not on file"
    else:
        status = "Inside covenant" if latest >= threshold else "Outside covenant"
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
            ("Margin", [measure(v, "{:.1f}%") for v in row["margin_pct"]]),
            ("Liquidity ratio", [measure(v, "{:.2f}") for v in row["liquidity_ratio"]]),
            ("Leverage", [measure(v, "{:.1f}x") for v in row["leverage"]]),
            ("Interest coverage", [measure(v, "{:.1f}x") for v in row["interest_coverage"]]),
        )
    )
    return f"""
    <div class="label">Financial analysis</div><h1>{escape(row["legal_name"])}</h1>
    <p class="lead">Revenue, margin, liquidity, leverage and interest cover are demonstration figures, so the covenant tests can be run before statements arrive. Drawn balance, collateral, ECL and days past due below follow the checked reporting dates.</p>
    <form class="inline" method="get" action="/financial">
      <label>Customer<br><select name="customer">{options}</select></label>
      <label>Scenario<br><select name="scenario">{shocks}</select></label>
      <button type="submit">Run</button>
    </form>
    {metrics([
        ("Latest coverage", measure(latest, "{:.1f}x"), False),
        ("Covenant", measure(threshold, "{:.1f}x"), False),
        ("Today", status, False),
        ("Scenario", measure(projected, "{:.1f}x"), False),
    ])}
    <div class="card"><table><thead><tr><th>Measure</th>{"".join(f"<th>{year}</th>" for year in years)}</tr></thead><tbody>{fin_rows}</tbody></table>
      <p>Credit assumption at approval: {measure(row["coverage_assumption"], "{:.1f}x")}. Scenario: {escape(SCENARIOS[scenario])}. Result: {scenario_status}.</p>
      <p>Statement extract: {escape(row["documents"]["financials"]["passage"])}</p>
      <p><a href="/email?id=MAIL-COV-APEX">Open the covenant email draft</a></p>
    </div>
    <div class="card" style="margin-top:12px"><div class="label">Portfolio extract across the checked dates</div>
      {trend_table([
        ("Drawn", lambda iso, cid=row["customer_id"]: money(customer(cid)["series"][view().dates.index(iso)]["drawn_hkd"])),
        ("ECL", lambda iso, cid=row["customer_id"]: money(customer(cid)["series"][view().dates.index(iso)]["ecl_hkd"])),
        ("EAD", lambda iso, cid=row["customer_id"]: money(customer(cid)["series"][view().dates.index(iso)]["ead_hkd"])),
        ("Stage", lambda iso, cid=row["customer_id"]: str(customer(cid)["series"][view().dates.index(iso)]["stage"])),
        ("Days past due", lambda iso, cid=row["customer_id"]: str(customer(cid)["series"][view().dates.index(iso)]["dpd"])),
        ("LTV", lambda iso, cid=row["customer_id"]: str(customer(cid)["series"][view().dates.index(iso)]["ltv"])),
        ("Next principal", lambda iso, cid=row["customer_id"]: money(customer(cid)["series"][view().dates.index(iso)]["next_due_hkd"])),
      ])}
    </div>"""


def proposal_records() -> list[dict]:
    rows = list(SEEDED_PROPOSALS)
    if UPLOAD_INDEX.exists():
        rows.extend(json.loads(UPLOAD_INDEX.read_text(encoding="utf-8")))
    return rows


def proposal_by_id(proposal_id: str) -> dict | None:
    return next((item for item in proposal_records() if item["id"] == proposal_id), None)


def proposal_path(item: dict) -> Path:
    base = UPLOADS if item.get("uploaded") else REPORT_FILES
    return base / item["file"]


def save_proposal(rm: str, filename: str, payload: bytes) -> str:
    UPLOADS.mkdir(parents=True, exist_ok=True)
    stored = json.loads(UPLOAD_INDEX.read_text(encoding="utf-8")) if UPLOAD_INDEX.exists() else []
    stamp = datetime.now(HK).strftime("%Y%m%d%H%M%S")
    item_id = f"upload-{stamp}-{len(stored) + 1}"
    display = Path(filename).name.replace('"', "").replace("/", "").replace("\\", "") or "proposal.docx"
    if not display.lower().endswith(".docx"):
        display += ".docx"
    target_name = f"{item_id}.docx"
    (UPLOADS / target_name).write_bytes(payload)
    stored.append({
        "id": item_id,
        "title": Path(display).stem,
        "rm": rm.strip() or "Relationship manager",
        "stored": datetime.now(HK).strftime("%-d %b %Y %H:%M HKT"),
        "filename": display,
        "file": target_name,
        "uploaded": True,
    })
    UPLOAD_INDEX.write_text(json.dumps(stored, indent=2), encoding="utf-8")
    return item_id


def parse_multipart(content_type: str, body: bytes) -> dict[str, dict]:
    marker = "boundary="
    if marker not in content_type:
        return {}
    boundary = content_type.split(marker, 1)[1].split(";", 1)[0].strip().strip('"')
    fields: dict[str, dict] = {}
    for part in body.split(b"--" + boundary.encode()):
        if b"Content-Disposition" not in part:
            continue
        header, _, data = part.partition(b"\r\n\r\n")
        if data.endswith(b"\r\n"):
            data = data[:-2]
        header_text = header.decode("utf-8", "replace")
        disposition = next((line for line in header_text.splitlines() if "Content-Disposition" in line), "")
        name_match = re.search(r'name="([^"]*)"', disposition)
        file_match = re.search(r'filename="([^"]*)"', disposition)
        name = name_match.group(1) if name_match else ""
        filename = file_match.group(1) if file_match else ""
        if name:
            fields[name] = {"filename": filename, "data": data}
    return fields


def hkex_hits(borrower: str, year: str) -> list[dict]:
    query = " ".join(borrower.split()).lower()
    if len(query) < 2 or not str(year).strip().isdigit():
        return []
    wanted = int(year)
    hits = []
    for item in HKEX_FILINGS:
        if item["year"] != wanted:
            continue
        names = [item["issuer"], *item["names"]]
        if any(query in name.lower() for name in names):
            hits.append(item)
    return hits


def external_reports_page(borrower: str, year: str) -> str:
    borrower = " ".join(borrower.split())
    year = year.strip()
    ready = len(borrower) >= 2 and year.isdigit()
    hits = hkex_hits(borrower, year) if ready else []
    if not borrower and not year:
        result = "<p>Enter a borrower and a year.</p>"
    elif not ready:
        result = "<p>Enter a borrower and a four-digit year.</p>"
    elif not hits:
        result = f"<p>No HKEX report is on file for {escape(borrower)} in {escape(year)}. The Gemini agent has not retrieved one yet.</p>"
    else:
        cards = []
        for item in hits:
            cards.append(
                f'<article class="sent-mail"><div class="label">HKEX</div>'
                f'<h2>{escape(item["issuer"])}</h2>'
                f'<p>{escape(item["document"])} · {item["year"]}</p>'
                f'<p>Retrieved for the search {escape(borrower)}, {escape(year)}. '
                f'The Gemini agent collects this filing from HKEX. The document is not stored here yet. '
                f'When it arrives, it is an input to the internal report.</p></article>'
            )
        result = "".join(cards)
    catalog = json.dumps([item["name"] for item in OBLIGORS] + ["Apex Water Solutions Ltd. (3768.HK)"])
    return f"""
    <div class="label">Report</div><h1>External report</h1>
    <p class="lead">Search by borrower and year for a financial report collected from HKEX.</p>
    <form class="inline hkex-search" method="get" action="/reports">
      <input type="hidden" name="source" value="external">
      <div class="suggest">
        <label>Borrower<br><input id="hkex-borrower" name="borrower" value="{escape(borrower)}" placeholder="Borrower or stock code" autocomplete="off"></label>
        <div class="suggest-list" id="hkex-list" hidden></div>
      </div>
      <label>Year<br><input name="year" type="number" min="1990" max="2100" value="{escape(year)}" placeholder="2025"></label>
      <button type="submit">Search</button>
    </form>
    <div class="card" style="margin-top:12px">{result}</div>
    <script>
    (function () {{
      var names = {catalog};
      var input = document.getElementById("hkex-borrower");
      var list = document.getElementById("hkex-list");
      function render() {{
        var query = input.value.trim().toLowerCase();
        if (!query) {{ list.hidden = true; list.innerHTML = ""; return; }}
        var hits = names.filter(function (name) {{ return name.toLowerCase().indexOf(query) >= 0; }}).slice(0, 8);
        list.hidden = false;
        list.innerHTML = hits.length ? hits.map(function (name) {{
          return '<button type="button" class="suggest-item" data-name="' + name.replace(/"/g, "&quot;") + '">' + name + "</button>";
        }}).join("") : '<p style="margin:8px 12px;color:#6F6862">No borrower matches.</p>';
      }}
      input.addEventListener("input", render);
      list.addEventListener("mousedown", function (event) {{
        var button = event.target.closest("button");
        if (!button) return;
        event.preventDefault();
        input.value = button.getAttribute("data-name");
        list.hidden = true;
      }});
      document.addEventListener("click", function (event) {{
        if (!input.parentElement.parentElement.contains(event.target)) list.hidden = true;
      }});
    }})();
    </script>"""


def reports_page(kind: str, detail: str, cid: str, generated: str = "", source: str = "", borrower: str = "", year: str = "") -> str:
    if source == "external":
        return external_reports_page(borrower, year)
    row = customer(cid) or customer(default_customer_id())
    port = view().portfolio()
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
            f"<p>{escape(port['industries'][0]['industry'])} is the largest industry at {escape(view().label())}, with drawn exposure {money(port['industries'][0]['drawn_hkd'])}.</p>"
        )
        extra = "<h2>Stage and DPD</h2>" + bars(
            [(f"Stage {key}", port["stages"][str(key)]["drawn_hkd"]) for key in (1, 2, 3)],
            hot=True,
        ) if detail == "full" else ""
    customers = "".join(
        f'<option value="{escape(item["customer_id"])}" {"selected" if item["customer_id"]==row["customer_id"] else ""}>{escape(item["legal_name"])}</option>'
        for item in BOOK["customers"] if item["full_file"]
    )
    catalog = json.dumps([
        {
            "id": item["id"],
            "name": item["name"],
            "aliases": item.get("aliases") or [],
            "industry": item["industry"],
            "rm": item["rm"],
            "asof": item["asof"],
            "drawn": item["drawn"],
            "ecl": item["ecl"],
            "stage": item["stage"],
            "dpd": item["dpd"],
            "rating": item["rating"],
        }
        for item in OBLIGORS
    ])
    return f"""
    <div class="label">Report</div><h1>Internal report</h1>
    <p class="lead">Search for a borrower. The closest names appear as you type. Choose one, generate the paper, then download the proposal or the monitoring report.</p>
    <div class="card">
      <div class="label">Borrower</div>
      <div class="suggest">
        <label>Search<br><input id="borrower-q" placeholder="Name, industry or borrower id" autocomplete="off"></label>
        <div class="suggest-list" id="borrower-list" hidden></div>
      </div>
      <div id="borrower-actions" hidden style="margin-top:12px">
        <p id="sel-line"></p>
        <button type="button" id="generate-btn">Generate</button>
      </div>
      <div id="borrower-result" hidden style="margin-top:12px">
        <h2 id="res-name"></h2>
        <p id="res-line"></p>
        <p><a class="btn" id="res-proposal">Download proposal</a> <a class="btn ghost" id="res-report">Download report</a></p>
      </div>
    </div>
    <script>
    (function () {{
      var borrowers = {catalog};
      var input = document.getElementById("borrower-q");
      var list = document.getElementById("borrower-list");
      var actions = document.getElementById("borrower-actions");
      var result = document.getElementById("borrower-result");
      var current = null;
      function esc(value) {{
        return String(value).replace(/[&<>\"']/g, function (ch) {{
          return {{"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}}[ch];
        }});
      }}
      function score(item, query) {{
        var name = item.name.toLowerCase();
        var industry = item.industry.toLowerCase();
        var id = item.id.toLowerCase();
        var aliases = (item.aliases || []).join(" ").toLowerCase();
        if (name === query) return 100;
        if (name.indexOf(query) === 0) return 80;
        if (name.split(/\\s+/).some(function (word) {{ return word.indexOf(query) === 0; }})) return 70;
        if (aliases.indexOf(query) >= 0) return 65;
        if (name.indexOf(query) >= 0) return 50;
        if (industry.indexOf(query) >= 0) return 30;
        if (id.indexOf(query) >= 0) return 20;
        return 0;
      }}
      function render() {{
        var query = input.value.trim().toLowerCase();
        if (!query) {{ list.hidden = true; list.innerHTML = ""; return; }}
        var hits = borrowers.map(function (item) {{ return {{ item: item, rank: score(item, query) }}; }})
          .filter(function (row) {{ return row.rank > 0; }})
          .sort(function (a, b) {{ return b.rank - a.rank || a.item.name.localeCompare(b.item.name); }})
          .slice(0, 8);
        list.hidden = false;
        list.innerHTML = hits.length ? hits.map(function (row) {{
          return '<button type="button" class="suggest-item" data-id="' + esc(row.item.id) + '">' + esc(row.item.name) + '<small>' + esc(row.item.industry) + " · " + esc(row.item.id) + "</small></button>";
        }}).join("") : '<p style="margin:8px 12px;color:#6F6862">No borrower matches.</p>';
      }}
      function select(id) {{
        current = borrowers.filter(function (item) {{ return item.id === id; }})[0];
        if (!current) return;
        input.value = current.name;
        list.hidden = true;
        actions.hidden = false;
        result.hidden = true;
        document.getElementById("sel-line").textContent = current.industry + " · " + current.asof + " · RM " + current.rm;
      }}
      input.addEventListener("input", render);
      list.addEventListener("mousedown", function (event) {{
        var button = event.target.closest("button");
        if (!button) return;
        event.preventDefault();
        select(button.getAttribute("data-id"));
      }});
      document.getElementById("generate-btn").addEventListener("click", function () {{
        if (!current) return;
        result.hidden = false;
        document.getElementById("res-name").textContent = current.name;
        document.getElementById("res-line").textContent = "Position " + current.asof + ". Drawn " + current.drawn + ". ECL " + current.ecl + ". Stage " + current.stage + ", PD grade " + current.rating + ", " + current.dpd + " days past due. The proposal is the input and the monitoring report is the output.";
        document.getElementById("res-proposal").href = "/proposal-file?id=" + encodeURIComponent(current.id);
        document.getElementById("res-report").href = "/report-file?id=" + encodeURIComponent(current.id);
      }});
      document.addEventListener("click", function (event) {{
        if (!input.parentElement.parentElement.contains(event.target)) list.hidden = true;
      }});
    }})();
    </script>
    <div class="label" style="margin-top:18px">Portfolio extract</div><h2>{escape(title)}</h2>
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
    <div class="card" style="margin-top:12px">{summary}{extra}
      <h2>Trend across the checked dates</h2>
      {trend_table([
        ("Drawn", lambda iso: money(view().portfolio_series()[view().dates.index(iso)]["drawn_hkd"]) if kind != "customer" else money(customer(row["customer_id"])["series"][view().dates.index(iso)]["drawn_hkd"])),
        ("ECL", lambda iso: money(view().portfolio_series()[view().dates.index(iso)]["ecl_hkd"]) if kind != "customer" else money(customer(row["customer_id"])["series"][view().dates.index(iso)]["ecl_hkd"])),
        ("Days past due" if kind == "customer" else "Names past due", lambda iso: str(customer(row["customer_id"])["series"][view().dates.index(iso)]["dpd"]) if kind == "customer" else str(view().portfolio_series()[view().dates.index(iso)]["dpd_names"])),
        ("Stage" if kind == "customer" else "Stage 2 names", lambda iso: str(customer(row["customer_id"])["series"][view().dates.index(iso)]["stage"]) if kind == "customer" else str(view().portfolio_series()[view().dates.index(iso)]["stage2_names"])),
      ])}
    </div>"""


def assistant_page(question: str, cid: str) -> str:
    row = customer(cid) or customer(default_customer_id())
    external = agent_slot.ask(row, question, view().dates, view().label())
    if external is None:
        answer, cites = answer_for(row, question)
        answer_label = "Local demonstration"
    else:
        answer, cites = external
        answer_label = "Gemini agent"
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
    <p class="lead">This first version answers four questions from the local file. News, approval minutes and internal mail are not searched yet.</p>
    <div class="card"><div class="label">Agent slot</div><p>{escape(agent_slot.status())} The later connection is the Gemini agent built in Google Enterprise, reached through Antigravity. Set RIP_AGENT_URL on this server when that endpoint exists. RIP_AGENT_KEY stays in the server environment.</p></div>
    <form class="inline" method="get" action="/assistant">
      <label>Customer<br><select name="customer">{options}</select></label>
      <label>Question<br><input name="q" value="{escape(question)}" style="width:420px"></label>
      <button type="submit">Ask</button>
    </form>
    <p>{chips}</p>
    <div class="card"><div class="label">{escape(answer_label)}</div><p>{escape(answer)}</p>{cite_html}</div>"""


def answer_for(row: dict, question: str) -> tuple[str, list[dict]]:
    text = question.lower()
    docs = row["documents"]
    if any(word in text for word in ("rating", "downgrade", "notch", "why")):
        grades = ", ".join(f"{view().label(point['date'])} grade {point['rating']}" for point in row["series"])
        stages = ", ".join(f"{view().label(point['date'])} stage {point['stage']}" for point in row["series"])
        return (
            f"At {view().label()} the current PD grade is {row['rating']}. The original grade on the portfolio file is {row['prior_rating']}. "
            f"Across the checked dates: {grades}. Stages: {stages}.",
            [docs["review"], docs["credit_paper"]],
        )
    if any(word in text for word in ("repay", "due", "maturity", "instal")):
        schedule = ", ".join(
            f"{view().label(point['date'])} {money(point['next_due_hkd'])} due {point['next_due_date']} ({point['next_due_days']} days)"
            for point in row["series"]
        )
        return (
            f"At {view().label()} the next obligation is {money(row['next_due_hkd'])} in {row['next_due_days']} days, from the cash flow schedule. "
            f"Days past due are {row['dpd']}. The monitoring threshold is HKD 5,000,000. Checked dates: {schedule}.",
            [docs["repayment"]],
        )
    if any(word in text for word in ("since", "develop", "change", "latest", "review")):
        first = row["series"][0]
        return (
            f"From {view().label(first['date'])} to {view().label()}, drawn exposure is {money(row['drawn_hkd'])}. "
            f"ECL moved from {money(first['ecl_hkd'])} to {money(row['ecl_hkd'])}. "
            f"Days past due moved from {first['dpd']} to {row['dpd']}. Stage moved from {first['stage']} to {row['stage']}. "
            f"Interest cover on the demonstration statements is {measure(row['interest_coverage'][-1], '{:.1f} times')} "
            f"and the demonstration covenant is {measure(row['coverage_threshold'], '{:.1f} times')}. "
            f"Demonstration revenue in the latest year is {money(row['revenue_hkd'][-1])}.",
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


def recipient_address(raw: str | None) -> str:
    """One address for the draft. Newlines cannot open another header."""
    return "".join(str(raw or "").split())[:254]


def script_json(value) -> str:
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def mail_row(entry_id: str, subject: str, meta: str) -> str:
    return (
        f'<div class="mail-row" data-id="{escape(entry_id)}">'
        f'<div class="mail-subject"><strong>{escape(subject)}</strong><span>{escape(meta)}</span></div>'
        f'<div class="mail-send">'
        f'<input type="email" inputmode="email" autocomplete="email" maxlength="254" placeholder="name@example.com" aria-label="Recipient for {escape(subject)}">'
        f'<button type="button">Send</button>'
        f'</div>'
        f'<p class="mail-note" hidden></p>'
        f'</div>'
    )


def mail_script(payload: dict) -> str:
    return f"""
    <script>
    (function () {{
      var letters = {script_json(payload)};
      var memory = {{}};
      try {{ memory = JSON.parse(sessionStorage.getItem("rip-draft-to") || "{{}}"); }} catch (error) {{ memory = {{}}; }}
      function clean(value) {{ return String(value || "").replace(/\\s+/g, "").slice(0, 254); }}
      function usable(address) {{ return address.indexOf("@") > 0 && address.indexOf("@") < address.length - 1; }}
      document.querySelectorAll(".mail-row").forEach(function (row) {{
        var input = row.querySelector("input");
        if (memory[row.dataset.id]) input.value = memory[row.dataset.id];
        input.addEventListener("input", function () {{
          memory[row.dataset.id] = clean(input.value);
          sessionStorage.setItem("rip-draft-to", JSON.stringify(memory));
        }});
      }});
      document.addEventListener("click", function (event) {{
        var button = event.target.closest(".mail-send button");
        if (!button) return;
        var row = button.closest(".mail-row");
        var input = row.querySelector("input");
        var note = row.querySelector(".mail-note");
        var address = clean(input.value);
        var letter = letters[row.dataset.id];
        if (!usable(address)) {{
          note.hidden = false;
          note.textContent = "Enter a recipient for this subject.";
          input.focus();
          return;
        }}
        note.hidden = true;
        memory[row.dataset.id] = address;
        sessionStorage.setItem("rip-draft-to", JSON.stringify(memory));
        var url = "mailto:" + address
          + "?subject=" + encodeURIComponent(letter.subject)
          + "&body=" + encodeURIComponent(letter.body);
        if (window.ripOpenMail) window.ripOpenMail(url);
        else window.location.href = url;
      }});
    }})();
    </script>"""


def news_mail(item: dict) -> dict:
    linked = ""
    person = customer(item.get("customer_id") or "")
    if person:
        linked = (
            f"\n\nLinked borrower {person['legal_name']}: drawn {money(person['drawn_hkd'])}, "
            f"stage {person['stage']}, {person['dpd']} days past due."
        )
    text = " ".join(str(item.get("body") or "").split())
    if len(text) > 700:
        text = text[:697].rstrip() + "..."
    subject = item["headline"]
    body = (
        f"{BOOK['banner']}\n\n"
        f"{item['date']}. {subject}\n"
        f"Source: {item['source']}. Severity: {item['severity']}.\n\n"
        f"{text}{linked}\n\n"
        "This draft is not a credit decision."
    )
    return {"subject": subject, "body": body}


def draft_mail(draft: dict) -> dict:
    text = live_letter(draft, "")
    if text.startswith("To:"):
        text = text.split("\n", 1)[1]
    if text.startswith("Subject:"):
        text = text.split("\n", 1)[1].lstrip("\n")
    return {"subject": draft["subject"], "body": text}


def relationship_mailbox(item: dict) -> tuple[str, str]:
    person = next((row for row in BOOK["customers"] if row["customer_id"] == item.get("customer_id")), None)
    name = ((person or {}).get("rm") or "").strip()
    if not name or "facilit" in name.lower():
        return "Credit desk", "credit.desk@hkbea.example"
    local = ".".join(part.lower() for part in name.split())
    return name, f"{local}@hkbea.example"


def sent_letter(item: dict) -> str:
    name, address = relationship_mailbox(item)
    article, _fields = news_fields(item["body"])
    borrower = next((row for row in BOOK["customers"] if row["customer_id"] == item.get("customer_id")), None)
    linked = f"\nLinked borrower: {borrower['legal_name']}." if borrower else "\nNo borrower on the book is named in this item."
    return (
        f"To: {name} <{address}>\n"
        f"Sent: {item['date']}, 08:20 HKT\n"
        f"Subject: {item['headline']}\n\n"
        f"This message was sent automatically because the severity is CRITICAL.\n\n"
        f"{article.strip()}\n"
        f"{linked}\n"
        f"Relationship manager: {name}."
    )


def drafts_page() -> str:
    critical = [item for item in BOOK["news"] if item["severity"] == "CRITICAL"]
    held = [item for item in BOOK["news"] if item["severity"] != "CRITICAL"]
    cards = []
    rms: list[str] = []
    borrowers: list[str] = []
    for item in critical:
        name, address = relationship_mailbox(item)
        person = next((row for row in BOOK["customers"] if row["customer_id"] == item.get("customer_id")), None)
        borrower = person["legal_name"] if person else "Not linked"
        if name not in rms:
            rms.append(name)
        if borrower not in borrowers:
            borrowers.append(borrower)
        cards.append(
            f'<article class="sent-mail" id="sent-{escape(item["id"])}" data-rm="{escape(name)}" data-borrower="{escape(borrower)}">'
            f'<div class="label">Sent automatically</div>'
            f'<h2>{escape(item["headline"])}</h2>'
            f'<p>RM: {escape(name)}</p>'
            f'<p>Borrower: {escape(borrower)}</p>'
            f'<p>To: {escape(name)} &lt;{escape(address)}&gt;</p>'
            f'<p>Sent: {escape(item["date"])}, 08:20 HKT</p>'
            f'<div class="letter">{escape(sent_letter(item))}</div></article>'
        )
    counts = {}
    for item in held:
        counts[item["severity"]] = counts.get(item["severity"], 0) + 1
    held_line = ", ".join(f"{counts[level]} {level.lower()}" for level in ("HIGH", "MEDIUM", "LOW") if counts.get(level))
    rm_options = "".join(f"<option>{escape(name)}</option>" for name in sorted(rms))
    borrower_options = "".join(f"<option>{escape(name)}</option>" for name in sorted(borrowers))
    return f"""
    <div class="label">Outbox</div><h1>Email portal</h1>
    <p class="lead">Critical news is sent automatically to the relationship manager. Filter the sent messages by RM or borrower. The record is the message, the time it went, and the address it went to. Addresses are demonstration mailboxes. High, medium and low items are not sent.</p>
    <div class="news-tools mail-tools">
      <div class="news-filters">
        <label><span class="label">RM</span><br>
          <select id="mail-rm"><option value="">All</option>{rm_options}</select>
        </label>
        <label><span class="label">Borrower</span><br>
          <select id="mail-borrower"><option value="">All</option>{borrower_options}</select>
        </label>
      </div>
    </div>
    <div class="card" id="mail-list">{''.join(cards) or '<p>No critical item is on the file.</p>'}
      <p id="mail-empty" hidden>No sent message matches this RM and borrower.</p>
    </div>
    <p class="lead">{escape(held_line)} were kept on the adverse-news page and were not sent.</p>
    <script>
    (function () {{
      var rm = document.getElementById("mail-rm");
      var borrower = document.getElementById("mail-borrower");
      var cards = [...document.querySelectorAll("#mail-list .sent-mail")];
      var empty = document.getElementById("mail-empty");
      function apply() {{
        var shown = 0;
        cards.forEach(function (card) {{
          var ok = (!rm.value || card.dataset.rm === rm.value) && (!borrower.value || card.dataset.borrower === borrower.value);
          card.hidden = !ok;
          if (ok) shown += 1;
        }});
        empty.hidden = shown > 0 || !cards.length;
      }}
      rm.addEventListener("change", apply);
      borrower.addEventListener("change", apply);
    }})();
    </script>"""


def live_letter(draft: dict, recipient: str = "") -> str:
    port = view().portfolio()
    people = [person for person in (customer(item["customer_id"]) for item in BOOK["customers"]) if person and person.get("on_position", True)]
    checked = ", ".join(view().label(date) for date in view().dates)
    late = [item for item in people if item["dpd"] > 0]
    late_line = "; ".join(
        f"{item['legal_name']} at {item['dpd']} days, ECL {money(item['ecl_hkd'])}, drawn {money(item['drawn_hkd'])}"
        for item in late
    ) or "none"
    banner = BOOK["banner"]
    intro = (
        f"To: {recipient_address(recipient)}\nSubject: {draft['subject']}\n\n{banner}\n\nDear colleague,\n\n"
        f"Position {view().label()}. Checked dates: {checked}. "
        f"Drawn {money(port['drawn_hkd'])}. ECL {money(port['ecl_hkd'])}. "
        "This draft follows the checked dates. It is not a credit decision.\n\n"
    )
    if draft["id"] == "MAIL-DPD-LANTERN":
        body = f"Days past due at the position date: {late_line}.\n\nThe cash-flow dates above HKD 5,000,000 are future principal dates. This draft does not treat those future dates as past due.\n"
    elif draft["id"] == "MAIL-REPAY-LANTERN":
        due = [item for item in people if item["next_due_hkd"] >= THRESHOLD and item["next_due_days"] <= 90]
        due.sort(key=lambda item: item["next_due_hkd"], reverse=True)
        focus = due[0] if due else people[0]
        body = (
            f"{focus['legal_name']} has principal of {money(focus['next_due_hkd'])} due on {focus['next_due_date']}, "
            f"{focus['next_due_days']} days after {view().label()}.\n\n"
            f"The amount is on {focus['next_contract']}, method {focus['next_method'].replace('_', ' ').title()}. "
            f"Group drawn is {money(focus['drawn_hkd'])}. LTV is {focus['ltv']}.\n"
        )
    elif draft["id"] == "MAIL-IND-WHOLESALE":
        lines = [f"{item['industry']}: drawn {money(item['drawn_hkd'])}, ECL {money(item['ecl_hkd'])}, stage 2 names {item['stage2']}, names past due {item['dpd_accounts']}." for item in port["industries"]]
        body = "\n".join(lines) + f"\n\nPortfolio LTV at the position date is {port['ltv']}.\n"
    elif draft["id"] == "MAIL-COV-APEX":
        apex = customer("BOR-AGHL")
        body = (
            f"Financial statements were not in the uploaded files. The covenant test still uses the demonstration statements.\n\n"
            f"What follows the checked dates for {apex['legal_name']}: drawn {money(apex['drawn_hkd'])}, "
            f"ECL {money(apex['ecl_hkd'])}, stage {apex['stage']}, {apex['dpd']} days past due, LTV {apex['ltv']}.\n"
        )
    else:
        apex = customer("BOR-AGHL")
        linked = [item for item in BOOK["news"] if item["customer_id"] == apex["customer_id"]]
        lines = "\n".join(f"{item['date']}. {item['headline']}" for item in linked)
        body = (
            f"Adverse news on file for {apex['legal_name']}:\n{lines}\n\n"
            f"At {view().label()}, {apex['legal_name']} is drawn {money(apex['drawn_hkd'])}, "
            f"ECL {money(apex['ecl_hkd'])}, stage {apex['stage']}, {apex['dpd']} days past due.\n"
        )
    return intro + body + "\nPlease send this from your own mailbox if you want it delivered.\n"


def email_page(draft_id: str) -> str:
    draft = next((item for item in BOOK["drafts"] if item["id"] == draft_id), BOOK["drafts"][0])
    if draft["id"] == "MAIL-NEWS-APEX":
        rows = []
        payload = {}
        for item in BOOK["news"]:
            payload[item["id"]] = news_mail(item)
            rows.append(mail_row(item["id"], item["headline"], f'{item["date"]} · {item["source"]} · {item["severity"]}'))
        return f"""
        <div class="label">Adverse news</div><h1>News drafts</h1>
        <p class="lead">Each headline is its own subject. Type a recipient beside that subject and send it on its own. Send opens your mail program. This site does not deliver the message.</p>
        <div class="card"><div class="mail-list">{''.join(rows)}</div></div>
        {mail_script(payload)}"""
    letter = live_letter(draft)
    payload = {draft["id"]: draft_mail(draft)}
    return f"""
    <div class="label">{escape(draft["kind"])}</div><h1>{escape(draft["subject"])}</h1>
    <p class="lead">This subject keeps its own recipient. Send opens your mail program. This site does not deliver the message.</p>
    <div class="mail-list">{mail_row(draft["id"], draft["subject"], draft["kind"])}</div>
    <p><a class="btn ghost" id="draft-download" href="/email.eml?id={escape(draft["id"])}">Download .eml</a></p>
    <textarea id="draft-letter" readonly>{escape(letter)}</textarea>
    {mail_script(payload)}
    <script>
    (function () {{
      var row = document.querySelector(".mail-row");
      var input = row.querySelector("input");
      var letter = document.getElementById("draft-letter");
      var link = document.getElementById("draft-download");
      function paint() {{
        var address = input.value.replace(/\\s+/g, "").slice(0, 254);
        var lines = letter.value.split("\\n");
        lines[0] = "To: " + address;
        letter.value = lines.join("\\n");
        link.href = "/email.eml?id=" + encodeURIComponent(row.dataset.id) + (address ? "&to=" + encodeURIComponent(address) : "");
      }}
      input.addEventListener("input", paint);
    }})();
    </script>"""


def customer_page(cid: str) -> str:
    row = customer(cid)
    if not row:
        return "<h1>Customer not in the book</h1>"
    docs = "".join(
        f'<p class="cite"><strong>{escape(doc["title"])}</strong> · {escape(doc["locator"])}<br>{escape(doc["passage"])}</p>'
        for doc in row["documents"].values()
    )
    def facility_metric(field: str, contract: str, money_field: bool = False):
        def getter(iso: str, contract: str = contract) -> str:
            point = customer(row["customer_id"])["series"][view().dates.index(iso)]
            found = next((item for item in point["facilities"] if item["contract"] == contract), None)
            if found is None:
                return "—"
            return money(found[field]) if money_field else str(found[field])
        return getter

    moving = [item for item in row["facilities"] if item["instrument"] != "Off-Bal"]
    facility_rows = "".join(
        "<tr>"
        f"<td>{escape(item['contract'])}</td><td>{escape(item['instrument'])}</td><td>{escape(item['status'])}</td>"
        f"<td>{money(item['balance_hkd'])}</td><td>{money(item['limit_hkd'])}</td><td>{money(item['available_hkd'])}</td>"
        f"<td>{money(item['ead_hkd'])}</td><td>{item['pd']}</td><td>{item['lgd']}</td><td>{money(item['ecl_hkd'])}</td>"
        f"<td>{item['stage']}</td><td>{item['dpd']}</td><td>{item['original_grade']} → {item['grade']}</td>"
        f"<td>{escape(item['maturity'])}</td><td>{item['ltv']}</td><td>{item['ltv_nrv']}</td>"
        f"<td>{escape(item['collateral_id'])}</td><td>{escape(item['collateral_type'])}</td>"
        f"<td>{money(item['market_hkd'])}</td><td>{money(item['nrv_hkd'])}</td>"
        f"<td>{escape(item['address'])}</td>"
        "</tr>"
        for item in row["facilities"]
    )
    return f"""
    <div class="label">Customer</div><h1>{escape(row["legal_name"])}</h1>
    <p class="lead">Position {escape(view().label(row.get("observed") or view().focus))}. {escape(row["legal_name"])} has drawn {money(row["drawn_hkd"])}, ECL {money(row["ecl_hkd"])}, stage {row["stage"]} and {row["dpd"]} days past due. Original grade {row["prior_rating"]}, current grade {row["rating"]}. Next principal {money(row["next_due_hkd"])} on {escape(row["next_due_date"])}.</p>
    {metrics([
        ("Drawn", money(row["drawn_hkd"]), False),
        ("ECL", money(row["ecl_hkd"]), True),
        ("Rating", f'{row["prior_rating"]} → {row["rating"]}', row["rating"] > row["prior_rating"]),
        ("DPD", str(row["dpd"]), row["dpd"] >= 30),
    ])}
    <div class="card"><div class="label">Trend across the checked dates</div>
      {trend_table([
        ("Drawn", lambda iso, cid=row["customer_id"]: money(customer(cid)["series"][view().dates.index(iso)]["drawn_hkd"])),
        ("Committed limit", lambda iso, cid=row["customer_id"]: money(customer(cid)["series"][view().dates.index(iso)]["committed_hkd"])),
        ("EAD", lambda iso, cid=row["customer_id"]: money(customer(cid)["series"][view().dates.index(iso)]["ead_hkd"])),
        ("ECL", lambda iso, cid=row["customer_id"]: money(customer(cid)["series"][view().dates.index(iso)]["ecl_hkd"])),
        ("Stage", lambda iso, cid=row["customer_id"]: str(customer(cid)["series"][view().dates.index(iso)]["stage"])),
        ("Days past due", lambda iso, cid=row["customer_id"]: str(customer(cid)["series"][view().dates.index(iso)]["dpd"])),
        ("Grade", lambda iso, cid=row["customer_id"]: str(customer(cid)["series"][view().dates.index(iso)]["rating"])),
        ("LTV", lambda iso, cid=row["customer_id"]: str(customer(cid)["series"][view().dates.index(iso)]["ltv"])),
        ("Collateral", lambda iso, cid=row["customer_id"]: money(customer(cid)["series"][view().dates.index(iso)]["collateral_hkd"])),
        ("Next principal", lambda iso, cid=row["customer_id"]: money(customer(cid)["series"][view().dates.index(iso)]["next_due_hkd"])),
        ("Next principal date", lambda iso, cid=row["customer_id"]: customer(cid)["series"][view().dates.index(iso)]["next_due_date"]),
      ])}
    </div>
    <div class="card" style="margin-top:12px"><div class="label">Facility ECL across the checked dates</div>
      {trend_table([(item["contract"], facility_metric("ecl_hkd", item["contract"], True)) for item in moving])}
    </div>
    <div class="card" style="margin-top:12px"><div class="label">Facility EAD across the checked dates</div>
      {trend_table([(item["contract"], facility_metric("ead_hkd", item["contract"], True)) for item in moving])}
    </div>
    <div class="card" style="margin-top:12px"><div class="label">Facility days past due across the checked dates</div>
      {trend_table([(item["contract"], facility_metric("dpd", item["contract"])) for item in moving])}
    </div>
    <div class="card" style="margin-top:12px"><div class="label">Facility maturity across the checked dates</div>
      {trend_table([(item["contract"], facility_metric("maturity", item["contract"])) for item in moving])}
    </div>
    <div class="card" style="margin-top:12px"><div class="label">Every facility at {escape(view().label())}</div>
      <div class="scroll"><table><thead><tr>
        <th>Contract</th><th>Instrument</th><th>Status</th><th>Balance</th><th>Limit</th><th>Available</th>
        <th>EAD</th><th>PD</th><th>LGD</th><th>ECL</th><th>Stage</th><th>DPD</th><th>Grade</th>
        <th>Maturity</th><th>LTV</th><th>LTV on NRV</th><th>Collateral</th><th>Type</th><th>Market</th><th>NRV</th><th>Address</th>
      </tr></thead><tbody>{facility_rows}</tbody></table></div>
      <p>Industry {escape(row["industry"])}. Collateral coverage {row["coverage_ratio"]}. RM {escape(row["rm"])} is a demonstration name.</p>
      {docs}
      <p><a href="/assistant?customer={escape(row["customer_id"])}&q=What+are+the+key+risks+for+this+customer%3F">Ask about this customer</a></p>
    </div>"""


def login_page(message: str = "") -> bytes:
    note = f'<p class="banner">{escape(message)}</p>' if message else ""
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sign in · BEA - Risk Intelligence</title>
<link href="https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600;700&family=Source+Serif+4:opsz,wght@8..60,560&display=swap" rel="stylesheet">
<style>
body {{ margin:0; min-height:100vh; display:grid; place-items:center; background:#F3EFEA; font-family:"Source Sans 3",sans-serif; color:#2C2825; }}
form {{ width:min(420px, calc(100% - 32px)); background:#FFFCF9; border:1px solid #E4DDD6; border-radius:16px; padding:28px; }}
h1 {{ font-family:"Source Serif 4",serif; color:#8C3E16; font-weight:560; margin:8px 0; }}
p {{ color:#6F6862; line-height:1.45; }}
label {{ display:block; font-size:.78rem; font-weight:700; letter-spacing:.04em; text-transform:uppercase; color:#6F6862; margin:12px 0; }}
input {{ width:100%; font:inherit; padding:10px 12px; border:1px solid #E4DDD6; border-radius:8px; margin-top:6px; }}
button {{ font:inherit; background:#E36F1E; color:#fff; border:0; border-radius:8px; padding:10px 14px; font-weight:700; margin-top:8px; }}
.banner {{ background:#F8E8E4; color:#B42318; border-radius:10px; padding:10px 12px; }}
code {{ color:#2C2825; }}
</style>
</head>
<body>
<form method="post" action="/login">
  <div style="font-family:'Source Serif 4',serif;font-size:1.45rem;line-height:1.2">BEA -<br><span style="color:#E36F1E">Risk Intelligence</span></div>
  <h1>Sign in</h1>
  <p>Property portfolio from 31 Dec 2025 to 30 Nov 2026. After sign-in, check the reporting dates. Demonstration account <code>cro.shum</code>, password <code>Harbour-Demo-2026</code>.</p>
  {note}
  <label>User<input name="user" autocomplete="username" required></label>
  <label>Password<input name="password" type="password" autocomplete="current-password" required></label>
  <button type="submit">Sign in</button>
</form>
</body>
</html>"""
    return html.encode("utf-8")


def session_ok(header: str | None) -> bool:
    jar = SimpleCookie()
    jar.load(header or "")
    morsel = jar.get("rip")
    if morsel is None:
        return False
    return hmac.compare_digest(morsel.value, SESSION)


ROUTES = {
    "dashboard": lambda q: dashboard(),
    "news": lambda q: news_page((q.get("note") or [""])[0]),
    "industry": lambda q: industry_page((q.get("name") or [default_industry()])[0]),
    "repayment": lambda q: repayment_page(int((q.get("window") or ["92"])[0] or 92), repayment_threshold((q.get("threshold") or [""])[0])),
    "financial": lambda q: financial_page((q.get("customer") or [default_customer_id()])[0], (q.get("scenario") or ["revenue_decline"])[0]),
    "reports": lambda q: reports_page((q.get("kind") or ["mir"])[0], (q.get("detail") or ["summary"])[0], (q.get("customer") or [default_customer_id()])[0], (q.get("generated") or [""])[0], (q.get("source") or [""])[0], (q.get("borrower") or [""])[0], (q.get("year") or [""])[0]),
    "assistant": lambda q: assistant_page((q.get("q") or ["What are the key risks for this customer?"])[0], (q.get("customer") or [default_customer_id()])[0]),
    "drafts": lambda q: drafts_page(),
    "email": lambda q: email_page((q.get("id") or ["MAIL-NEWS-APEX"])[0]),
    "customer": lambda q: customer_page((q.get("id") or [""])[0]),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        key = parsed.path.strip("/") or "dashboard"
        query = parse_qs(parsed.query)
        signed_in = session_ok(self.headers.get("Cookie"))
        if key == "logout":
            self._redirect("/login", "rip=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0")
            return
        if key == "login":
            if signed_in:
                self._redirect("/dashboard")
                return
            self._html(login_page())
            return
        if not signed_in:
            self._redirect("/login")
            return
        requested = query.get("d") or dates_from_cookie(self.headers.get("Cookie"))
        bind_view(requested, parsed.path + (("?" + parsed.query) if parsed.query else ""))
        if key in {"proposal-file", "report-file"}:
            requested_id = (query.get("id") or [""])[0]
            obligor = next((row for row in OBLIGORS if row["id"] == requested_id), None)
            if obligor is not None:
                kind = "proposal" if key == "proposal-file" else "report"
                path = REPORT_FILES / "obligors" / obligor["id"] / f"{kind}.docx"
                download_name = f"{obligor['name']} {'Proposal' if kind == 'proposal' else 'Report'}.docx".replace('"', "")
            else:
                item = proposal_by_id(requested_id)
                if item is None:
                    self.send_error(404)
                    return
                if key == "report-file":
                    if not item.get("output_file"):
                        self.send_error(404)
                        return
                    path = REPORT_FILES / item["output_file"]
                    download_name = item["output_name"]
                else:
                    path = proposal_path(item)
                    download_name = item["filename"]
            if not path.is_file():
                self.send_error(404)
                return
            payload = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if key == "email.eml":
            draft = next((item for item in BOOK["drafts"] if item["id"] == (query.get("id") or [""])[0]), BOOK["drafts"][0])
            payload = live_letter(draft, (query.get("to") or [""])[0]).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "message/rfc822")
            self.send_header("Content-Disposition", f'attachment; filename="{draft["id"]}.eml"')
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if key not in ROUTES:
            key = "dashboard"
        section = "drafts" if key == "email" else key
        if key == "reports" and (query.get("source") or [""])[0] == "external":
            section = "reports-external"
        body = page(key, section, ROUTES[key](query))
        self._html(body)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        action = parsed.path.strip("/")
        length = int(self.headers.get("Content-Length") or 0)
        if action == "proposals":
            if not session_ok(self.headers.get("Cookie")):
                self._redirect("/login")
                return
            if length > 8_000_000:
                self.send_error(413)
                return
            fields = parse_multipart(self.headers.get("Content-Type", ""), self.rfile.read(length))
            upload = fields.get("proposal") or {}
            filename = upload.get("filename") or ""
            payload = upload.get("data") or b""
            rm = (fields.get("rm") or {}).get("data", b"").decode("utf-8", "replace")
            if not filename.lower().endswith(".docx") or not payload.startswith(b"PK"):
                self._redirect("/reports")
                return
            save_proposal(rm, filename, payload)
            self._redirect("/reports")
            return
        if action in {"news-severity", "news-actions"}:
            if not session_ok(self.headers.get("Cookie")):
                if action == "news-severity":
                    self._json({"ok": False}, 401)
                else:
                    self._redirect("/login")
                return
            if length > (2_000 if action == "news-severity" else 400_000):
                self.send_error(413)
                return
            form = parse_qs(self.rfile.read(length).decode("utf-8"))
            if action == "news-severity":
                severity = (form.get("severity") or [""])[0]
                ok = news_desk.set_severity(BOOK["news"], (form.get("id") or [""])[0], severity)
                self._json({"ok": ok, "severity": severity if ok else ""}, 200 if ok else 400)
                return
            note = handle_news_form(form)
            self._redirect(f"/news?note={note}#action-desk")
            return
        if length > 20000:
            self.send_error(413)
            return
        form = parse_qs(self.rfile.read(length).decode("utf-8"))
        if action == "dates":
            if not session_ok(self.headers.get("Cookie")):
                self._redirect("/login")
                return
            preset = (form.get("preset") or ["apply"])[0]
            if preset == "all":
                chosen = list(BOOK["dates"])
            elif preset == "latest":
                chosen = [BOOK["dates"][-1]]
            else:
                chosen = [item for item in BOOK["dates"] if item in form.get("d", [])]
                if not chosen:
                    chosen = [BOOK["dates"][-1]]
            nxt = (form.get("next") or ["/dashboard"])[0]
            if not nxt.startswith("/") or nxt.startswith("//"):
                nxt = "/dashboard"
            self._redirect(nxt, date_cookie(chosen))
            return
        if action != "login":
            self.send_error(404)
            return
        user = (form.get("user") or [""])[0]
        password = (form.get("password") or [""])[0]
        user_ok = hmac.compare_digest(hashlib.sha256(user.encode()).hexdigest(), hashlib.sha256(DEMO_USER.encode()).hexdigest())
        password_ok = hmac.compare_digest(
            hashlib.sha256(password.encode()).hexdigest(),
            hashlib.sha256(DEMO_PASSWORD.encode()).hexdigest(),
        )
        if user_ok and password_ok:
            self._redirect("/dashboard", f"rip={SESSION}; HttpOnly; SameSite=Lax; Path=/")
            return
        self._html(login_page("The user name or password does not match the demonstration account."), 401)

    def _redirect(self, location: str, cookie: str | None = None) -> None:
        self.send_response(303)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Location", location)
        self.end_headers()

    def _json(self, payload: dict, status: int = 200) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _html(self, payload: bytes, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", 8766), Handler)
    print("http://127.0.0.1:8766")
    server.serve_forever()


if __name__ == "__main__":
    main()
