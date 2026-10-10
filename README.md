# Harbour Meridian Risk Intelligence

Hackathon proof of concept for the fictional **Harbour Meridian Bank Limited**. The bank is not an HKMA-authorised institution and does not conduct banking business.

**SYNTHETIC HACKATHON DATA - NOT FOR CUSTOMER, CREDIT, COMPLIANCE, RISK, REGULATORY OR BUSINESS DECISION-MAKING**

The local profile does not call a hosted model. Answers and reports are assembled from authorised database records and trusted synthetic documents. Numeric risk figures are calculated in Python.

## What you can do

- Search customers and groups inside a portfolio entitlement.
- Open a Customer 360 and a Group 360 view.
- Ask a question and receive claim-level citations.
- Generate a draft customer risk summary as HTML, PDF and JSON.
- Review facilities, limits, covenants, collateral, early-warning indicators and data quality.
- Open a source document on the cited page, sheet or section.
- See why a relationship manager cannot read another portfolio, and why AML indicators are restricted.

## Demonstration accounts

Every synthetic user uses the password `Harbour-Demo-2026`.

| Username | Role | Portfolio |
| --- | --- | --- |
| `cro.shum` | Chief risk officer | All |
| `cra.ho` | Credit-risk analyst | All |
| `fcc.lam` | Financial-crime compliance analyst | All, including AML |
| `rm.chan` | Relationship manager | Corporate banking only |
| `rm.wong` | Relationship manager | Commercial and SME |
| `ia.fung` | Internal auditor (read-only) | All |
| `admin.platform` | Platform administrator | No customer portfolio |
| `admin.model` | Model administrator | No customer portfolio |

`rm.chan` cannot retrieve Sai Kung Aquaculture Limited (`CUS-SKAL-0008`), which sits in the cross-border portfolio.

## Setup

Python 3.12 is required.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Or `make setup`.

## Synthetic data, documents and the database

```bash
PYTHONPATH=. .venv/bin/python scripts/seed_database.py
```

This regenerates the book with seed `20261010`, writes `data/ground_truth.json`, stores watermarked documents in `data/object_store`, and ingests them. The full book has 42 customers, 14 groups, 18 month-ends and 104 documents.

Schema creation for a fresh database is also available through Alembic:

```bash
PYTHONPATH=. .venv/bin/alembic upgrade head
```

The seed command creates the schema itself, then loads data. Use Alembic when you want the migration path without loading the book.

## Search index

Keyword and vector indexes are built at question time from the documents the caller is allowed to see. They are not a global unrestricted index. After seeding, the configured index directory is `data/indexes`.

## Start the application

API (OpenAPI at `http://127.0.0.1:8000/docs`):

```bash
PYTHONPATH=. .venv/bin/python -m uvicorn app.api.app:app --host 0.0.0.0 --port 8000
```

Web UI:

```bash
PYTHONPATH=. .venv/bin/python -m streamlit run app/ui/streamlit_app.py --server.address 0.0.0.0 --port 8501
```

Health: `GET /health`. Readiness: `GET /ready`.

## Tests and evaluation

```bash
PYTHONPATH=. .venv/bin/python -m pytest
PYTHONPATH=. .venv/bin/python -m ruff check app scripts synthetic_data tests
PYTHONPATH=. .venv/bin/python scripts/run_evaluation.py
```

Evaluation prints measured rates. Do not replace those figures with an assumed score. The cases live in `app/evaluation/cases.json`.

## Reports

Sign in through the UI as `cro.shum` and open **Customer Risk Report Generator**, or call:

```bash
curl -s -X POST http://127.0.0.1:8000/auth/login \
  -H 'content-type: application/json' \
  -d '{"username":"cro.shum","password":"Harbour-Demo-2026"}'
```

Use the returned bearer token with `POST /reports` and body `{"customer_id":"CUS-AHTL-0001"}`. Download `GET /reports/{report_id}/html` or `GET /reports/{report_id}/pdf`.

## Docker

```bash
docker compose up --build
```

The UI is on port 8501 and the API on port 8000. The container seeds the database on first start. This remains a hackathon profile, not a production deployment.

## Five-minute demonstration

1. Sign in as `cro.shum`.
2. Open Apex Harbour Trading Limited and note the overdue review, rising utilisation and two early-warning indicators.
3. Ask: `What is the facility utilisation for Kowloon Meridian Textiles Limited?` The answer cites both 62% and 71% and does not pick one.
4. Ask the same exposure question about Sai Kung Aquaculture Limited after signing in as `rm.chan`. Retrieval is denied.
5. Sign back in as `fcc.lam` and open the AML page for Golden Bauhinia Remittance Limited. The page summarises alerts and does not recommend a suspicious transaction report.
6. Generate the Apex draft report and download the PDF. It is labelled as requiring human review.

## Further reading

- [Architecture](docs/architecture.md)
- [Walkthrough and measured results](walkthrough.md)
- [User guide](docs/user-guide.md)
- [Limitations](docs/limitations.md)
- [Production roadmap](docs/production-roadmap.md)
