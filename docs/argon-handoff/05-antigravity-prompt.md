# Prompt to paste into Antigravity or Gemini Argon

Use this as the first message. Attach `01` through `04`, `sample-portfolio.json`, and `preview/index.html`.

---

Build the BEA AI Risk Intelligence Platform described in the attached GCPE011 workflow.

Recreate the operating model, not a generic chatbot.

- A user triggers a group review or a portfolio scan.
- Read internal structured data (RDW, RDS, IS9), internal documents (credit proposals, CWS, early-warning signals) and external sources (Bloomberg, Moody's, web search).
- Install the five personas in `.agents/agents/` as Antigravity subagents. Quantitative Data, Document Intelligence and Market Surveillance run in parallel. Orchestration and Synthesis starts only when those three have finished. Compliance and Audit appends every step and cannot delete history. Do not put these agents on a platform page.
- Produce the seven sections in the submission: integrated risk summary, relationship summary, latest account developments, credit risk mitigants, credit deterioration indicators, portfolio analysis, and a proposed monitoring plan. Add the audit trajectory.
- All financial figures come from tools or cited records. The model explains them and does not calculate by prose.
- Every material claim has a clickable citation to the passage, record or formula.
- If sources disagree, show both figures.
- Map onshore and offshore entities and guarantees before stating group exposure.
- CRO, credit committee and relationship manager see the same facts with different emphasis. A relationship manager cannot see another officer's groups.
- The model must not approve credit, exit a customer, or file a suspicious transaction report.

Match the attached preview for layout and tone. Use the orange `#E36F1E`, deep orange `#C45112`, red `#B42318` and warm greys from the design system. Off-white ground, serif titles, sans-serif interface, thin borders, no purple and no decorative gradients.

Start from `sample-portfolio.json`. Label the figures as illustrative until a governed data connection is attached. When a bucket connection exists, keep the same screen contract and replace the mock records.

Acceptance for the first build:

1. Portfolio page for a CRO, with groups that open a pack.
2. Group pack with the seven sections and working citation panels.
3. Audit trail with an append-only record, including a human accept or return of the monitoring plan.
4. A relationship-manager session that cannot open a group outside entitlement.
5. The five personas available to `invoke_subagent`, and absent from the platform navigation.
