# Data model

The schema is `app/models/tables.py`. Amounts use numeric columns. Dates are stored as dates and displayed as DD MMM YYYY in Asia/Hong_Kong.

## Parties and access

- `portfolios`, `users`, `user_portfolios`, `role_permissions`
- `customer_groups`, `customers`, `beneficial_owners`, `products`, `customer_products`

A user sees a customer only when `customers.portfolio_id` is in that user's entitlements and the role has `customer.read`.

## Facilities and risk history

- `facilities`, `facility_snapshots` (original currency, rate, rate date, source, method, HKD equivalent, utilisation, data quality)
- `deposit_balances`, `fx_rates`, `risk_metrics`, `rating_history`
- `collateral_items`, `collateral_valuations`
- `covenants`, `covenant_observations`, `reported_figures`
- `alerts`, `risk_events`, `management_actions`, `reviews`, `early_warning_indicators`, `watchlist_entries`
- `transactions`, `legal_matters`, `qualitative_assessments`

`facility_snapshots.data_quality` is `conflict_unresolved` for Kowloon Meridian Textiles. Those rows have no adopted drawn amount. The application does not treat the missing amount as zero.

## Documents

- `documents`, `document_customers`, `document_chunks`, `evidence_statements`, `ingestion_events`

Each document stores a checksum, controlled reference, reporting date, version, superseded flag, sensitivity and ingestion status. The storage key is not shown to users.

## Governance and audit

- `audit_events` (SQLite triggers reject update and delete)
- `model_registry`, `prompt_registry`, `prohibited_uses`, `third_parties`, `control_states`, `ai_incidents`
- `generated_reports`, `report_reviews`
- `risk_taxonomy`, `regulatory_references`, `dataset_meta`, `data_quality_issues`, `jobs`

## Seed

`scripts/seed_database.py` rebuilds the book from seed `20261010`. Ground truth for scenarios A to J is written to `data/ground_truth.json`.
