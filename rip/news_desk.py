"""Edits made on the adverse-news page.

Severity changes and action wording are stored beside the book, so the
generated book.json stays untouched. A confirmed action is copied into the
borrower's monitoring report by the server. Until then it is only a draft.
"""

from __future__ import annotations

import json
import threading
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "news_state.json"
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
GENERIC = {
    "limited", "ltd", "corp", "corporation", "holdings", "investment",
    "inc", "co", "company", "the",
}
PACE = {
    "CRITICAL": "Contact the borrower within five business days and bring the item to the next credit meeting.",
    "HIGH": "Verify the report against the facility file within ten business days.",
    "MEDIUM": "Record the item on the monitoring file and review it at the next scheduled review.",
    "LOW": "Keep the item as a watch point, and contact the borrower only if the same theme is reported again.",
}
LOCK = threading.RLock()


def _read() -> dict:
    if not STATE.exists():
        return {"severity": {}, "actions": {}}
    try:
        loaded = json.loads(STATE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"severity": {}, "actions": {}}
    if not isinstance(loaded, dict):
        return {"severity": {}, "actions": {}}
    severity = loaded.get("severity")
    actions = loaded.get("actions")
    return {
        "severity": severity if isinstance(severity, dict) else {},
        "actions": actions if isinstance(actions, dict) else {},
    }


def _write(state: dict) -> None:
    payload = json.dumps(state, ensure_ascii=False, indent=2)
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(STATE)


def load_state() -> dict:
    with LOCK:
        return _read()


def save_state(state: dict) -> None:
    with LOCK:
        _write(state)


def update_state(mutator):
    with LOCK:
        state = _read()
        result = mutator(state)
        _write(state)
        return result


def apply_severity(news: list[dict]) -> None:
    saved = load_state()["severity"]
    for item in news:
        severity = saved.get(item["id"])
        if severity in SEVERITIES:
            item["severity"] = severity


def set_severity(news: list[dict], news_id: str, severity: str) -> bool:
    if severity not in SEVERITIES:
        return False
    item = next((row for row in news if row["id"] == news_id), None)
    if item is None:
        return False

    def mutator(state: dict) -> None:
        state["severity"][news_id] = severity

    update_state(mutator)
    item["severity"] = severity
    return True


def clean_text(value: str, limit: int = 4000) -> str:
    kept = "".join(ch for ch in value if ch in "\n\t" or ord(ch) >= 32)
    return kept.strip()[:limit]


def match_keys(legal_name: str) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        cleaned = " ".join(value.split())
        if len(cleaned) < 10 or cleaned.lower() in seen:
            return
        seen.add(cleaned.lower())
        keys.append(cleaned)

    add(legal_name)
    trimmed = legal_name
    for suffix in (" Limited", " Ltd.", " Ltd", " Corp.", " Corp"):
        if trimmed.endswith(suffix):
            trimmed = trimmed[: -len(suffix)].strip()
            add(trimmed)
    words = [part.strip(".,") for part in legal_name.split()]
    core = [part for part in words if part.lower() not in GENERIC]
    if len(core) >= 2:
        add(" ".join(core[:2]))
    return keys


def suggest_customer(item: dict, customers: list[dict]) -> str:
    linked = item.get("customer_id") or ""
    if linked:
        return linked
    blob = f"{item.get('headline', '')} {item.get('body', '')}".lower()
    best_id = ""
    best_len = 0
    for customer in customers:
        for key in match_keys(customer.get("legal_name") or ""):
            if key.lower() in blob and len(key) > best_len:
                best_id = customer["customer_id"]
                best_len = len(key)
    return best_id


def news_signal(body: str) -> tuple[str, str]:
    marker = " News type: "
    if marker not in body:
        return "News", "Adverse development"
    _, rest = body.split(marker, 1)
    kind, _, after = rest.partition(". Signal: ")
    signal, _, _ = after.partition(". Severity: ")
    return (kind.strip() or "News"), (signal.strip() or "Adverse development")


def load_workbook_news(customers: list[dict], path: Path) -> list[dict]:
    """The adverse-news file is the only news source. Extra book rows are not kept."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as book:
        shared: list[str] = []
        root = ET.fromstring(book.read("xl/sharedStrings.xml"))
        for item in root.findall("m:si", ns):
            shared.append("".join(node.text or "" for node in item.iter(f"{{{ns['m']}}}t")))
        sheet = ET.fromstring(book.read("xl/worksheets/sheet1.xml"))
    rows: list[list[str]] = []
    for row in sheet.findall("m:sheetData/m:row", ns):
        values: list[str] = []
        for cell in row.findall("m:c", ns):
            node = cell.find("m:v", ns)
            if node is None or node.text is None:
                values.append("")
            elif cell.attrib.get("t") == "s":
                values.append(shared[int(node.text)])
            else:
                values.append(node.text)
        rows.append(values)
    header = rows[0]
    index = {name: position for position, name in enumerate(header)}
    news: list[dict] = []
    for values in rows[1:]:
        def cell(name: str) -> str:
            position = index[name]
            return values[position].strip() if position < len(values) else ""

        number = cell("news number")
        headline = cell("headline")
        source_field = cell("source")
        publisher, _, when = source_field.rpartition(" - ")
        if not when:
            publisher, when = source_field, ""
        try:
            dated = datetime.strptime(when, "%d %b %Y").strftime("%-d %b %Y")
        except ValueError:
            dated = when
        severity = cell("severity").upper()
        if severity not in SEVERITIES:
            severity = "MEDIUM"
        details = cell("details")
        kind = cell("news type") or "News"
        signal = cell("signal type") or "Adverse development"
        entities = cell("entity involved")
        body = f"{details} News type: {kind}. Signal: {signal}. Severity: {severity}. Entities: {entities}."
        item = {
            "id": f"NEWS-FILE-{int(number):02d}",
            "headline": headline,
            "source": publisher,
            "date": dated,
            "severity": severity,
            "customer_id": "",
            "industry": "Not linked on the book",
            "body": body,
            "entities": entities,
            "news_type": kind,
            "signal": signal,
        }
        item["customer_id"] = suggest_customer(item, customers)
        person = next((row for row in customers if row["customer_id"] == item["customer_id"]), None)
        point = (person or {}).get("history", [{}])[-1] if person else {}
        if person:
            item["industry"] = person.get("industry") or item["industry"]
        item["factors"] = {
            "exposure_hkd": point.get("drawn_hkd") or 0,
            "security_coverage": point.get("coverage_ratio") if person else "not on the book",
            "guarantor_support": (person or {}).get("guarantor") or "not on the book",
            "financial_strength": f"grade {point.get('rating')}" if person else "not on the book",
            "warning_signals": len((person or {}).get("warnings") or []) if person else "not on the book",
            "score": {"CRITICAL": 90, "HIGH": 70, "MEDIUM": 45, "LOW": 20}[severity],
            "material": severity in {"CRITICAL", "HIGH"},
        }
        news.append(item)
    return news


def draft_action(item: dict, borrower: dict | None) -> str:
    kind, signal = news_signal(item.get("body") or "")
    severity = item.get("severity") or "MEDIUM"
    pace = PACE.get(severity, PACE["MEDIUM"])
    if borrower:
        point = borrower["history"][-1]
        who = borrower["legal_name"]
        position = (
            f" On the current extract, {who} is PD grade {point['rating']}, stage {point['stage']}, "
            f"{point['dpd']} days past due, drawn HKD {point['drawn_hkd']:,.0f}."
        )
    else:
        who = "the borrower selected for this action"
        position = ""
    return (
        f"Follow up “{item['headline']}” ({item['source']}, {item['date']}). "
        f"The file classes it as {kind}, severity {severity}. Signal: {signal}. "
        f"For {who}: {pace}"
        f"{position} "
        f"Confirm whether the report changes repayment, collateral value, covenant headroom or the internal grade, "
        f"and attach the evidence to the monitoring file."
    )
