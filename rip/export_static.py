"""Write the business-case screens as static pages for hosting."""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import serve

ROOT = Path(__file__).resolve().parent.parent / "site"
QUESTIONS = [
    "What are the key risks for this customer?",
    "Why did the rating change?",
    "What has changed since the last review?",
    "What repayments are coming due?",
]


def slug(text: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in text)
    parts = [part for part in cleaned.split("-") if part]
    return "-".join(parts)[:80] or "page"


def filename_for(url: str) -> str:
    parsed = urlparse(unescape(url))
    path = parsed.path.strip("/") or "dashboard"
    query = parse_qs(parsed.query)
    if path in ("", "dashboard"):
        return "index.html"
    if path == "news":
        return "news.html"
    if path == "industry":
        name = (query.get("name") or [serve.default_industry()])[0]
        return f"industry-{slug(name)}.html"
    if path == "repayment":
        window = (query.get("window") or ["92"])[0]
        return f"repayment-{window}.html"
    if path == "financial":
        customer = (query.get("customer") or [serve.default_customer_id()])[0]
        scenario = (query.get("scenario") or ["revenue_decline"])[0]
        return f"financial-{slug(customer)}-{slug(scenario)}.html"
    if path == "reports":
        kind = (query.get("kind") or ["mir"])[0]
        detail = (query.get("detail") or ["summary"])[0]
        customer = (query.get("customer") or [serve.default_customer_id()])[0]
        return f"reports-{slug(kind)}-{slug(detail)}-{slug(customer)}.html"
    if path == "assistant":
        customer = (query.get("customer") or [serve.default_customer_id()])[0]
        question = (query.get("q") or [QUESTIONS[0]])[0]
        return f"assistant-{slug(customer)}-{slug(question)}.html"
    if path == "drafts":
        return "drafts.html"
    if path == "email":
        return f"email-{(query.get('id') or ['draft'])[0]}.html"
    if path == "email.eml":
        return f"{(query.get('id') or ['draft'])[0]}.eml"
    if path == "customer":
        return f"customer-{(query.get('id') or ['missing'])[0]}.html"
    return "index.html"


def urls() -> list[str]:
    found = [
        "/dashboard",
        "/news",
        "/industry",
        "/repayment",
        "/financial",
        "/reports",
        "/assistant",
        "/drafts",
    ]
    for industry in serve.BOOK["industries"]:
        found.append("/industry?name=" + industry["industry"])
    for window in ("31", "92", "180", "365"):
        found.append(f"/repayment?window={window}")
    customers = [row["customer_id"] for row in serve.BOOK["customers"] if row["full_file"]]
    for customer in customers:
        found.append(f"/customer?id={customer}")
        for scenario in serve.SCENARIOS:
            found.append(f"/financial?customer={customer}&scenario={scenario}")
        for kind in ("mir", "customer"):
            for detail in ("summary", "full"):
                found.append(f"/reports?kind={kind}&detail={detail}&customer={customer}")
        for question in QUESTIONS:
            found.append(f"/assistant?customer={customer}&q={question}")
    for draft in serve.BOOK["drafts"]:
        found.append(f"/email?id={draft['id']}")
        found.append(f"/email.eml?id={draft['id']}")
    return found


def render(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.strip("/") or "dashboard"
    query = parse_qs(parsed.query)
    if path == "email.eml":
        draft = next(
            item for item in serve.BOOK["drafts"] if item["id"] == (query.get("id") or [""])[0]
        )
        return draft["body"]
    key = path if path in serve.ROUTES else "dashboard"
    active = "drafts" if key == "email" else key
    html = serve.page(active, active, serve.ROUTES[key](query)).decode("utf-8")
    return html


def rewrite(html: str, mapping: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        attribute, target = match.group(1), match.group(2)
        if not target.startswith("/"):
            return match.group(0)
        filename = mapping.get(target) or mapping.get(unescape(target)) or filename_for(target)
        return f'{attribute}="{filename}"'

    return re.sub(r'(href|action)="([^"]+)"', replace, html)


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}
    pages: dict[str, str] = {}
    for url in urls():
        filename = filename_for(url)
        mapping[url] = filename
        encoded = url.split("?", 1)
        if len(encoded) == 2:
            path, query = encoded
            pairs = parse_qs(query)
            flat = [(key, value) for key, values in pairs.items() for value in values]
            mapping[path + "?" + urlencode(flat)] = filename
        if filename not in pages:
            pages[filename] = render(url)
    script = (
        "<script>"
        f"const FILEMAP={json_map(mapping)};"
        "document.addEventListener('submit',function(event){"
        "var form=event.target; if(!form||!form.getAttribute) return;"
        "event.preventDefault();"
        "var action=form.getAttribute('action')||'/dashboard';"
        "var params=new URLSearchParams(new FormData(form)).toString();"
        "var key=action+(params?'?'+params:'');"
        "var dest=FILEMAP[key]||FILEMAP[key.replace(/\\+/g,'%20')];"
        "if(dest) location.href=dest;"
        "});"
        "</script>"
    )
    for filename, content in pages.items():
        if filename.endswith(".eml"):
            (ROOT / filename).write_text(content, encoding="utf-8")
            continue
        html = rewrite(content, mapping)
        html = html.replace("</body>", script + "</body>")
        (ROOT / filename).write_text(html, encoding="utf-8")
    print(f"wrote {len(pages)} files to {ROOT}")


def json_map(mapping: dict[str, str]) -> str:
    import json

    return json.dumps(mapping, ensure_ascii=False)


if __name__ == "__main__":
    main()
