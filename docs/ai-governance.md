# AI governance

The governance screen reads the database copies of `config/governance.json`.

- Intended purpose, system owner and risk owner are named as synthetic roles.
- The model inventory records the composer, hashing embedder, feature reranker and concern-score rules. Only the concern score creates a number, and it is Python, not a language model.
- Prompts are versioned in `prompt_registry`.
- Prohibited uses include credit decisions, onboarding or exit, suspicious transaction reports, sanctions clearance, regulatory filing, legal conclusions, real data, and disabling citations.
- Third parties are disabled by default. No document or prompt is sent to an external model unless `EXTERNAL_LLM_ENABLED` is set, which it is not in the local profile.
- Independent validation is a placeholder: "Not performed."
- The periodic review date stored for the demonstration is 10 Apr 2027.
- The kill switch and demonstration-upload mode are `control_states` rows. Changing them requires `model.admin` or `admin.demo_mode` and writes an audit event.
- There is no simulated model-change approval workflow beyond the human-review marker on reports. A production workflow is described in `docs/production-roadmap.md`.
- Senior management remains accountable. The model drafts. It does not decide.

The concern score shows weights, inputs, missing inputs, formula, timestamp and a hackathon label. Commentary must not hide a missing input or present the score as an approved internal rating.
