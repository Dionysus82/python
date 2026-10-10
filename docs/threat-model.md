# Threat model

This is a hackathon prototype. The notes below are design considerations, not a completed security assessment and not a claim that the controls are sufficient.

**SYNTHETIC HACKATHON DATA - NOT FOR CUSTOMER, CREDIT, COMPLIANCE, RISK, REGULATORY OR BUSINESS DECISION-MAKING**

## Assets

Synthetic customer records, synthetic documents, demonstration credentials, draft reports, and the audit trail.

## Actors

Authorised synthetic users in three lines of defence, a platform administrator, a model administrator, and anyone who can reach the local ports.

## Relevant abuse cases

| Case | Behaviour in this prototype |
| --- | --- |
| Cross-portfolio read | Denied before retrieval. The message does not confirm that hidden documents exist. An audit event is written. |
| AML curiosity | Roles without `aml.read` receive a restriction and no alert content. |
| Prompt injection in a question or a document | The text is logged as content. It does not change scope, citations or configuration. |
| Production-looking upload | Rejected unless demonstration mode was explicitly enabled by an administrator. |
| Tampering with the audit log | SQLite triggers abort update and delete. |
| Path disclosure | Downloads use object keys checked against the store root. Paths are not returned. |
| Treating a draft as an approval | Reports stay drafts. The author cannot record their own human review. |

## Gaps

There is no malware scanner, no hardware-backed secret store, no network segregation, no independent penetration test, and no production identity provider. HMAC session tokens and PBKDF2 passwords are demonstration controls. SQLite on a local disk is not an immutable ledger. See `docs/production-roadmap.md` and `docs/security.md`.

Formal cybersecurity review remains required before any use beyond the hackathon.
