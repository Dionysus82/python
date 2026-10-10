# Walkthrough

Harbour Meridian Risk Intelligence is a runnable hackathon proof of concept for the fictional Harbour Meridian Bank Limited. It is not an HKMA-authorised institution, not production-ready, and not a basis for a customer, credit, compliance, risk, regulatory or business decision.

**SYNTHETIC HACKATHON DATA - NOT FOR CUSTOMER, CREDIT, COMPLIANCE, RISK, REGULATORY OR BUSINESS DECISION-MAKING**

## What was built

A Python service and a management UI over a seeded synthetic book:

- 42 legal entities, 14 groups, 18 month-ends, facilities in HKD, USD, CNY, EUR and JPY
- 104 trusted documents (103 indexed, 1 quarantined corrupt file), watermarked
- Search, Customer 360, Group 360, portfolio screens, question answering with claim-level citations, and draft HTML, PDF and JSON reports
- Portfolio and role checks before retrieval, AML restrictions, immutable-style SQLite audit triggers, and an evaluation set for scenarios A to J

## Architecture

Streamlit and FastAPI call the same services. Those services ask the authorisation layer for the caller's customer set, then read SQLite and the trusted document directory. Numeric scores come from `app/domain/risk_calculation.py`. The answering pipeline labels sourced facts, calculations, rules, contradictions and missing evidence. See `docs/architecture.md`.

## Design choices

- The default path does not call an external model. A hashing embedder plus BM25 is enough for the seeded questions, and it keeps the demo offline.
- Conflicting figures for the same metric and date are shown together. Kowloon Meridian Textiles is the seeded case: 62% in the credit review and 71% in the workbook.
- HKD totals use the stored rate, rate date, source and method. Original currencies are not added to each other.
- A relationship manager's question about a customer outside the portfolio is rejected before the facts are loaded. The message does not describe the hidden book.
- Reports stay drafts. The author of a draft cannot record the human review of that draft.

## Commands that were run

```bash
PYTHONPATH=. .venv/bin/python scripts/seed_database.py
PYTHONPATH=. .venv/bin/python -m pytest
PYTHONPATH=. .venv/bin/python -m ruff check app scripts synthetic_data tests
PYTHONPATH=. .venv/bin/python -m mypy app scripts synthetic_data
PYTHONPATH=. .venv/bin/python scripts/run_evaluation.py
```

The API was exercised with the FastAPI test client: login, dashboard, Apex search, Kowloon contradiction, relationship-manager denial, PDF download, and PDF page 6 as PNG.

The Streamlit UI was exercised in a browser: sign-in as `cro.shum`, dashboard, the Kowloon contradiction with citations, sign-in as `rm.chan`, and the Sai Kung denial.

## Measured results

Seed: `{'indexed': 103, 'quarantined': 1, 'failed': 0}` with 42 customers, 14 groups, 104 documents and scenarios A–J in `data/ground_truth.json`.

Pytest: 14 passed.

Ruff: all checks passed.

Mypy: no issues found in 64 source files.

Evaluation on the seeded book:

| Measure | Result |
| --- | --- |
| Cases | 15 passed of 15 |
| Authorisation | 15 of 15 |
| Abstention correctness | 13 of 13 cases that declare it |
| Contradiction detection | 4 of 4 |
| Customer resolution | 10 of 10 |
| Citation correctness | 7 of 7 |
| Citation completeness | 7 of 7 |
| Retrieval recall of expected documents | 7 of 7 |

Dashboard aggregate exposure for the chief risk officer on this seed: HKD 633,971,593.00. That figure is a demonstration sum of stored HKD equivalents, not a management report.

The Apex draft PDF produced by the API started with a PDF header and the HTML copy contained the synthetic-data banner.

## Demonstration accounts

Password: `Harbour-Demo-2026`.

- `cro.shum` — chief risk officer, all portfolios
- `rm.chan` — corporate portfolio only; cannot open Sai Kung Aquaculture Limited
- `fcc.lam` — financial-crime analyst, including AML indicators
- `admin.model` — kill switch, no customer book

## Limitations and reviews still required

Local SQLite, a directory of files, HMAC sessions and a hashing embedder are hackathon controls. There is no malware scanner, no independent model validation, and no regulatory sign-off. Formal legal, compliance, financial-crime, model-risk, privacy and cybersecurity review remains required before any use beyond the demonstration. See `docs/limitations.md` and `docs/production-roadmap.md`.

Docker Compose is defined. It was not executed here because a Docker daemon was not available in the build environment.

## Five-minute script

Follow `docs/demo-script.md`.
