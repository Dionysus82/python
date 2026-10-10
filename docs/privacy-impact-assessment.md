# Privacy impact assessment template

This template is for the hackathon. It is not a completed assessment under the Personal Data (Privacy) Ordinance and it has not been reviewed by the Office of the Privacy Commissioner for Personal Data.

**Dataset:** synthetic only. The prototype is not designed to hold personal data. Do not load a real file.

| Topic | Hackathon position | Review still required |
| --- | --- | --- |
| Purpose | Research and drafting on synthetic customers | Confirm purpose limitation before any other use |
| Minimisation | AML fields are hidden without `aml.read`. Administrators have no customer book | Reassess every new field |
| Need to know | Portfolio entitlements | Joiners, movers and leavers are not a real identity process |
| Retention | Documents are labelled hackathon-ephemeral | No disposal job is executed |
| Correction | Not implemented as a case-management workflow | Required before any real record |
| Export | Downloads are permission-checked | No watermarking of the UI export beyond the banner |
| Residency | `DATA_RESIDENCY` defaults to a local Hong Kong hackathon label | No regional cloud control is enforced |
| External processing | External LLM disabled by default | A new assessment is required before enabling a provider |
| Audit | Access, denial and AML views are logged | Logs are not tamper-evident outside SQLite triggers |

Decision: the prototype may be demonstrated with synthetic data. It must not be connected to a real customer store on the strength of this template.
