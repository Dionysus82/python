# Evaluation

Cases are `app/evaluation/cases.json`. Run:

```bash
PYTHONPATH=. .venv/bin/python scripts/run_evaluation.py
```

Each case records the question, username, expected customer, expected abstention or denial, expected contradiction, expected citation documents and prohibited phrases.

The runner measures, from the actual answers:

- customer resolution
- citation correctness and completeness
- retrieval recall of the expected documents
- contradiction detection
- abstention correctness
- authorisation pass rate, including an audit event for the unauthorised portfolio case

Retrieval precision is not reduced to one ratio, because hybrid search may return additional authorised documents. Recall asks whether the expected document was retrieved or cited.

The measured summary from the seeded book is recorded in `walkthrough.md`. Re-run the script after any change. Do not copy an old rate forward.
