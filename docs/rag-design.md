# Retrieval and grounded answering

The pipeline in `app/rag/pipeline.py` does the following, in order:

1. Reject the question if the role lacks `ask.use`.
2. Resolve named customers from identifiers only, then refuse any name outside the portfolio before facts are loaded.
3. Detect instruction-like text and log it. It is not followed.
4. Abstain on unsupported allegations such as a conviction that no trusted statement supports.
5. For a group question, sum only authorised entities and show each original currency with its stored rate.
6. Build claims from structured records and trusted statements.
7. Fold conflicting values for the same metric and date into one contradiction claim. No figure is preferred.
8. Search BM25 and hashing vectors only inside the visible document set.
9. Validate that each claim's customer and documents are still inside scope.
10. Render sourced facts, calculations, rules, contradictions and missing evidence with different labels.

If no claim survives, the answer is: "Insufficient trusted evidence was found."

Stale evidence keeps its as-of date. A missing value is not zero. The absence of an alert is not the absence of risk.

The composer does not decide lending, onboarding, suspicious-transaction reporting, sanctions clearance or regulatory filing.
