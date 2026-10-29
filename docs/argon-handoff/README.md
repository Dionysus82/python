# Handoff pack for a company-computer rebuild

This folder is the brief for regenerating the Risk Intelligence Platform with Google Antigravity or Gemini Argon. It follows the GCPE011 idea submission and the orange, red and grey workflow diagram in that document.

Give the model these files together, in this order:

1. `06-create-agent-prompts.md` — Name, Description, and Instructions to paste into Google Cloud → Create agent.
2. `05-antigravity-prompt.md` — the instruction to paste first if you are regenerating the platform as well.
3. `01-workflow.md` — the operating workflow.
4. `02-agent-design.md` — how the five backend agents are called. The paste-ready persona for each one is `../../.agents/agents/<name>/agent.md`.
5. `03-ui-design-system.md` — colour, type and layout for the platform a person sees.
6. `04-screen-and-data-spec.md` — screens, roles and the mock data contract.
7. `sample-portfolio.json` — illustrative records, not live bank data.
8. `../preview/index.html` — the visual reference for the platform. It does not contain a page for the agents.
9. `workflow-diagram.png` — the colour and stage reference from the idea submission. Use the orange, red and warm grey. Do not redraw the globe mark.

The five agents are Antigravity subagents. Copy `.agents/agents/` into the company workspace and confirm them with `/agents`. They do not become navigation items.

The preview is a front-end sample. It does not call Gemini, and it does not read RDW, RDS, IS9, CWS, Bloomberg or Moody's. Those connections are for the rebuild on the company computer.

Keep the product name used in the submission: **BEA AI Risk Intelligence Platform**. Do not describe the result as regulator-approved or as a substitute for a credit decision.
