# Regulatory reference register

These references are contextual design inputs only.

**Formal legal, compliance and regulatory review remains required. Nothing in this prototype is a statement of compliance with any law, ordinance, regulatory module, circular, guideline or supervisory expectation.**

The machine-readable copy is `config/regulatory_references.json`. It is loaded into `regulatory_references` when the database is seeded. Do not embed regulatory conclusions in application logic.

| Reference | Authority | Version or issue date | Domain | Status |
| --- | --- | --- | --- | --- |
| Supervisory Policy Manual IC-1 Risk Management Framework | Hong Kong Monetary Authority | 06 Oct 2017 (BRDR listing observed as current; confirm the in-force revision before any reliance) | Enterprise risk management | Design input only — not implemented as a compliance control |
| Supervisory Policy Manual SA-1 Risk-based Supervisory Approach | Hong Kong Monetary Authority | 23 Dec 2022 (BRDR listing observed as current; confirm the in-force revision before any reliance) | Supervisory context | Design input only — not implemented as a compliance control |
| Supervisory Policy Manual CR-G-1 General Principles of Credit Risk Management | Hong Kong Monetary Authority | 19 Jan 2001 (BRDR listing observed as current; confirm the in-force revision before any reliance) | Credit risk | Design input only — not implemented as a compliance control |
| Supervisory Policy Manual CR-G-13 Counterparty Credit Risk Management | Hong Kong Monetary Authority | 03 Jul 2018 (BRDR listing observed as current; confirm the in-force revision before any reliance) | Counterparty credit risk | Design input only — not implemented as a compliance control |
| Supervisory Policy Manual LM-2 Sound Systems and Controls for Liquidity Risk Management | Hong Kong Monetary Authority | V.2 dated 25 Nov 2016 in secondary summaries; confirm the in-force revision on the HKMA BRDR before any reliance | Liquidity risk | Design input only — not implemented as a compliance control |
| Supervisory Policy Manual OR-1 Operational Risk Management | Hong Kong Monetary Authority | 25 Jul 2022 (BRDR listing observed as current; confirm the in-force revision before any reliance) | Operational risk | Design input only — not implemented as a compliance control |
| Supervisory Policy Manual TM-G-1 General Principles for Technology Risk Management | Hong Kong Monetary Authority | 24 Jun 2003 (BRDR cross-reference observed as current; confirm the in-force revision before any reliance) | Technology risk | Design input only — not implemented as a compliance control |
| High-level Principles on Artificial Intelligence | Hong Kong Monetary Authority | 01 Nov 2019 (HKMA document identifier 20191101; confirm before any reliance) | Model risk | Design input only — not implemented as a compliance control |
| Consumer Protection in respect of Use of Generative Artificial Intelligence | Hong Kong Monetary Authority | 07 Nov 2024, with a related document dated 25 Nov 2024 (confirm before any reliance) | Conduct risk | Design input only — not implemented as a compliance control |
| Guideline on Anti-Money Laundering and Counter-Financing of Terrorism (For Authorized Institutions) | Hong Kong Monetary Authority | Current HKMA guideline; exact revision to be confirmed on the HKMA BRDR before any reliance | AML risk | Design input only — not implemented as a compliance control |
| Banking Ordinance (Cap. 155) | Hong Kong SAR | Cap. 155, as amended from time to time; confirm the in-force text before any reliance | Institutional context | Design input only — not implemented as a compliance control |
| Anti-Money Laundering and Counter-Terrorist Financing Ordinance (Cap. 615) | Hong Kong SAR | Cap. 615, as amended from time to time; confirm the in-force text before any reliance | AML risk | Design input only — not implemented as a compliance control |
| Personal Data (Privacy) Ordinance (Cap. 486) | Hong Kong SAR | Cap. 486, as amended from time to time; confirm the in-force text before any reliance | Data risk | Design input only — not implemented as a compliance control |
| Guidance on the Ethical Development and Use of Artificial Intelligence | Office of the Privacy Commissioner for Personal Data, Hong Kong | 18 Aug 2021 (confirm before any reliance) | Data risk | Design input only — not implemented as a compliance control |
| Artificial Intelligence: Model Personal Data Protection Framework | Office of the Privacy Commissioner for Personal Data, Hong Kong | 11 Jun 2024 (confirm before any reliance) | Data risk | Design input only — not implemented as a compliance control |
| Supervisory Policy Manual GS-1 Climate Risk Management | Hong Kong Monetary Authority | 30 Dec 2021 (BRDR listing observed as current; confirm the in-force revision before any reliance) | Climate risk | Design input only — not implemented as a compliance control |
| Basel Committee principles for credit, liquidity, operational and related risk management | Basel Committee on Banking Supervision | Specific papers and revision dates to be confirmed at formal review | Cross-risk | Design input only — not implemented as a compliance control |

## Design consideration and validation

### HKMA-SPM-IC-1
- Application owner: Synthetic platform administrator, Harbour Meridian Bank Limited (fictional)
- Design consideration: Informs the prototype's three-lines-of-defence roles, risk taxonomy and the separation between evidence and management reporting. It is a design input only.
- Validation requirement: Formal legal, compliance and regulatory review required

### HKMA-SPM-SA-1
- Application owner: Synthetic chief risk officer role (fictional user cro.shum)
- Design consideration: Informs why the prototype organises information by risk and materiality for a management reader. It does not implement a supervisory process.
- Validation requirement: Formal legal, compliance and regulatory review required

### HKMA-SPM-CR-G-1
- Application owner: Synthetic credit-risk function (fictional)
- Design consideration: Informs customer, facility, limit, collateral, review and early-warning displays. Demonstration calculations are not credit decisions.
- Validation requirement: Formal legal, compliance and regulatory review required

### HKMA-SPM-CR-G-13
- Application owner: Synthetic market-risk function (fictional)
- Design consideration: Informs the separate display of demonstration counterparty credit exposure. The prototype does not calculate regulatory capital.
- Validation requirement: Formal legal, compliance and regulatory review required

### HKMA-SPM-LM-2
- Application owner: Synthetic liquidity-risk function (fictional)
- Design consideration: Informs separate liquidity metrics, early-warning indicators and the instruction not to treat liquidity stress as credit default.
- Validation requirement: Formal legal, compliance and regulatory review required

### HKMA-SPM-OR-1
- Application owner: Synthetic operational-risk function (fictional)
- Design consideration: Informs operational and cyber incident records and the distinction between an incident summary and a risk acceptance.
- Validation requirement: Formal legal, compliance and regulatory review required

### HKMA-SPM-TM-G-1
- Application owner: Synthetic platform administrator (fictional)
- Design consideration: Informs upload validation, access control, logging and the documented production-control gap. The prototype is not a technology-risk-compliant system.
- Validation requirement: Formal legal, compliance, cybersecurity and regulatory review required

### HKMA-AI-PRINCIPLES-2019
- Application owner: Synthetic model administrator (fictional)
- Design consideration: Informs governance, accountability, data-quality labelling, transparency and the prohibition on presenting model text as a decision.
- Validation requirement: Formal model-risk, legal, compliance and regulatory review required

### HKMA-GENAI-CP-2024
- Application owner: Synthetic model administrator (fictional)
- Design consideration: Informs disclosure that commentary is model-generated, human oversight, and the default refusal to send data to an external model.
- Validation requirement: Formal legal, compliance and regulatory review required

### HKMA-AML-GUIDELINE
- Application owner: Synthetic financial-crime compliance role (fictional)
- Design consideration: Informs restricted access to synthetic financial-crime indicators and the ban on suspicious-transaction-reporting or exit decisions.
- Validation requirement: Formal legal, compliance and regulatory review required

### BO-CAP-155
- Application owner: Synthetic senior management role (fictional)
- Design consideration: Explains why the fictional bank is not described as an authorised institution and why the prototype cannot be used for banking business.
- Validation requirement: Formal legal, compliance and regulatory review required

### AMLO-CAP-615
- Application owner: Synthetic financial-crime compliance role (fictional)
- Design consideration: Informs the boundary that the prototype retrieves synthetic indicators and does not file, simulate or decide a suspicious transaction report.
- Validation requirement: Formal legal, compliance and regulatory review required

### PDPO-CAP-486
- Application owner: Synthetic data-governance reviewer (fictional)
- Design consideration: Informs purpose limitation, access control, retention labels and the synthetic-data-only constraint. No real personal data is processed.
- Validation requirement: Formal legal, privacy and compliance review required

### PCPD-AI-2021
- Application owner: Synthetic data-governance reviewer (fictional)
- Design consideration: Informs accountability, human oversight, transparency and data-minimisation language in the AI governance record.
- Validation requirement: Formal privacy, legal and compliance review required

### PCPD-AI-FRAMEWORK-2024
- Application owner: Synthetic data-governance reviewer (fictional)
- Design consideration: Informs the privacy-impact and AI-impact templates. The dataset is synthetic and the templates are not completed assessments.
- Validation requirement: Formal privacy, legal and compliance review required

### HKMA-SPM-GS-1
- Application owner: Synthetic enterprise-risk role (fictional)
- Design consideration: Informs the separate climate-risk indicator. The prototype does not perform climate-risk capital or scenario analysis.
- Validation requirement: Formal legal, compliance and regulatory review required

### BCBS-RISK-PRINCIPLES
- Application owner: Synthetic chief risk officer role (fictional user cro.shum)
- Design consideration: Informs vocabulary for exposure, limits, operational incidents and governance. No Basel ratio or capital figure is presented as a regulatory measure.
- Validation requirement: Formal legal, compliance and regulatory review required
