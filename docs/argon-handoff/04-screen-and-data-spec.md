# Screens and data contract

Build four destinations. Sample records live in `sample-portfolio.json`.

## 1. Portfolio

Audience: CRO.

Show entitled exposure, count of groups on enhanced monitoring, groups with a rating migration this quarter, and open early warnings. Then a short list of groups that need a meeting, each row opening the pack.

Include the five-stage strip so a visitor can see that the screen is the output of the workflow, not a static report.

## 2. Group pack

Audience: credit committee, and the CRO when they open one group.

Header: group name, onshore and offshore entities, UBO, stage, relationship manager.

Then the seven sections, in order. Each section has a short prose paragraph and the figures that support it. Each material sentence has a citation.

The monitoring plan ends with actions a person can accept or return. Accepting writes an audit event. It does not approve credit.

## 3. Agents

Show the five agents, whether they ran in parallel, the sources each one touched, and the output handed to Agent 4. This page explains the orchestration. It is not a second copy of the pack.

## 4. Audit trajectory

A timeline a reviewer can read: trigger, each tool call, formula, citation used, exception, and the human decision on the monitoring plan. Records are append-only.

## Mock contract

```json
{
  "group_id": "GRP-PLG",
  "legal_name": "Pacific Lantern Group",
  "entities": [{ "entity_id": "", "booking": "onshore|offshore", "currency": "HKD" }],
  "ubo": [{ "name": "", "ownership_pct": 0 }],
  "exposure": { "outstanding_hkd": 0, "limit_hkd": 0, "deposits_hkd": 0, "as_of": "2026-09-30" },
  "rating": { "current": 5, "prior": 4, "as_of": "2026-09-30" },
  "sections": [{ "id": "integrated_risk", "paragraphs": [{ "text": "", "citations": ["SRC-1"] }] }],
  "agents": [{ "id": "agent_1", "status": "complete", "sources": ["RDW"] }],
  "audit": [{ "at": "", "actor": "", "event": "", "detail": "" }]
}
```

Internal source names to use in the prototype, clearly marked illustrative: RDW, RDS, IS9, CWS, credit proposal PDF, Bloomberg, Moody's, web search.

## What the company-computer build must add

- Gemini Enterprise connections to the real buckets, behind the bank's identity.
- Antigravity orchestration of the five agents, with Agent 4 blocked until 1, 2 and 3 finish.
- NotebookLM-style citation clicks that open the source passage.
- Portfolio entitlements enforced before any agent retrieves a record.
- Deterministic tools for exposure, coverage, headroom and rating migration.
