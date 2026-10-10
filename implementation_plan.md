# Implementation plan

The workspace started without an application. The plan below is what was built for the hackathon profile of the fictional Harbour Meridian Bank Limited.

## Decisions

- Python 3.12, FastAPI, SQLAlchemy, SQLite for the zero-configuration profile, Streamlit for the management UI.
- No hosted model. Answers are deterministic claims. Embeddings are a local hashing embedder. BM25 covers keywords.
- Risk numbers are Python functions in `app/domain/risk_calculation.py`. The composer cannot change them.
- Authorisation is applied before retrieval. An empty portfolio sees nothing.
- Documents sit behind `TrustedDocumentStore`. The local profile is a directory with object keys.
- Regulatory text stays in `config/regulatory_references.json`. Code does not state that a control meets a module.
- Reports are drafts. There is no simulated approval.

## Delivery order

1. Configuration, schema, security, audit triggers and authorisation.
2. Deterministic synthetic book: 42 customers, 14 groups, 18 month-ends, 104 watermarked documents, scenarios A to J.
3. Ingestion for PDF, DOCX, XLSX, CSV and TXT, with quarantine rules.
4. Claim builder, contradiction folding, hybrid search and the question pipeline.
5. Analytics services, source viewer, draft HTML/PDF/JSON reports.
6. FastAPI and the 19 Streamlit pages.
7. Evaluation cases, pytest, Ruff, mypy, Docker and the documentation set.

## Acceptance mapping

The README commands seed the database, start the API and UI, run tests and run evaluation. Measured results are in `walkthrough.md`.
