# Handoff pack for a company-computer rebuild

This folder is the brief for regenerating the Risk Intelligence Platform with Google Antigravity or Gemini Argon. It follows the GCPE011 idea submission and the orange, red and grey workflow diagram in that document.

Give the model these files together, in this order:

1. `05-antigravity-prompt.md` — the instruction to paste first.
2. `01-workflow.md` — the operating workflow.
3. `02-agent-design.md` — the five agents, their inputs and the rules they must not break.
4. `03-ui-design-system.md` — colour, type and layout.
5. `04-screen-and-data-spec.md` — screens, roles and the mock data contract.
6. `sample-portfolio.json` — illustrative records, not live bank data.
7. `../preview/index.html` — the visual reference for the first business-style interface.
8. `workflow-diagram.png` — the colour and stage reference from the idea submission. Use the orange, red and warm grey. Do not redraw the globe mark.

The preview is a front-end sample. It does not call Gemini, and it does not read RDW, RDS, IS9, CWS, Bloomberg or Moody's. Those connections are for the rebuild on the company computer.

Keep the product name used in the submission: **BEA AI Risk Intelligence Platform**. Do not describe the result as regulator-approved or as a substitute for a credit decision.
