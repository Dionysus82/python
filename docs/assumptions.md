# Assumptions

- The demonstration clock is 10 Oct 2026 (`DEMO_TODAY`). Month-end history runs for 18 months through 30 Sep 2026.
- Foreign-exchange rates are a flat synthetic mid-rate card, not a market feed. HKD per 1 unit of foreign currency is stored on each snapshot.
- Internal ratings use a fictional 1-to-10 scale where 1 is strongest. They are not an external rating agency scale.
- Probability of default, loss given default, expected loss and the concern score are teaching calculations. They are not regulatory capital.
- "Total exposure" in the composer adds drawn, contingent and demonstration counterparty-credit amounts after conversion. Notional is excluded.
- The latest facility snapshot date in the book is 30 Sep 2026. Freshness thresholds live in `config/freshness.json`.
- Generic customers beyond the named scenarios are stable illustrations so the book reaches 42 legal entities and 14 groups.
- Users are fictional. Names are synthetic staff labels, not real employees.
- The local profile is the supported path. PostgreSQL and external models are configuration seams only.
