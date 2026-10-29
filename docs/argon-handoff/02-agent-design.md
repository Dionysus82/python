# Five backend agents

These agents run inside Google Antigravity. They are not pages on the platform. The platform shows the pack they produce, the citations, and the audit trail.

Antigravity discovers each persona from `.agents/agents/<name>/agent.md`. On the company computer, copy that directory into the workspace root, then open `/agents` and confirm the five names. Each file has `subagent: true` and `mainAgent: false`, so the planner invokes them with `invoke_subagent` and a person does not pick them as the chat agent.

The `tools` list is deliberately empty. Antigravity can hang a subagent when a tool name is not a real tool. Connect Gemini Enterprise buckets, and the deterministic calculator, as MCP or governed tools later. Until those names are real, do not add them to the frontmatter.

`commandExecutionPolicy` is `off`. These agents read through the connections they are given. They do not shell out to compute a balance.

Each subagent starts with a clean context. The rules live in that agent's own file. They are not inherited from the parent chat.

## Call order

1. Invoke `quantitative-data`, `document-intelligence` and `market-surveillance` together. Pass the same group, position date, and entitlement list. Do not pass one agent's output into another.
2. Wait until all three have returned, including an abstention or a gap list.
3. Invoke `orchestration-synthesis` with those three JSON payloads and the audience (`cro`, `credit_committee`, or `rm`).
4. Invoke `compliance-audit` at the start, after each return, and when a person accepts or returns the monitoring plan. It appends. It does not rewrite earlier events.

A parent prompt that does only this coordination is enough. It should not read RDW or write the pack itself.

## What each one is for

| Persona | Proposal role | Reads | Returns |
| --- | --- | --- | --- |
| `quantitative-data` | Quantitative Data Agent | RDW, RDS, IS9, wealth extract | Monitoring baseline. Missing stays null. Conflicts stay side by side. Derived figures wait for the calculator. |
| `document-intelligence` | Document Intelligence Agent | Credit proposals, org charts, CWS | Customer overview, onshore and offshore map, UBO, guarantees, collateral, each with a page or record. |
| `market-surveillance` | Market Surveillance Agent | Bloomberg, Moody's, allow-listed web | Early-warning candidates on the names it was given, plus whether exposure changed. |
| `orchestration-synthesis` | Orchestration and Synthesis Agent | Only the three JSON payloads | The seven sections, each material sentence cited. |
| `compliance-audit` | Compliance and Audit Agent | Events from the other four and from the person | Append-only trail. A denial does not include the hidden record. |

## Platform

The screens stay the portfolio, the group pack, and the audit trail. Do not add a screen that introduces these five agents. The audit trail is a deliverable. The agents that write it stay in Antigravity.
