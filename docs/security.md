# Security notes

Controls implemented for the hackathon profile:

- Role permissions are loaded from `config/rbac.json`, not from document text.
- Portfolio entitlements are applied before content queries.
- Uploads are checked for extension, signature, size, executables, macros and a synthetic-data declaration.
- Duplicate checksums are rejected.
- Instruction-like text is detected and stored only as content.
- Audit records are appended. The SQLite profile installs abort triggers on update and delete.
- The default configuration does not enable an external model or send prompts off the machine.
- Secrets are read from the environment. The production profile name refuses the default hackathon secret at startup, and even then this build is not a production system.

The denial message is the same whether a customer is outside the portfolio or not visible to the caller: "The requested customer is outside your authorised portfolio or does not exist."

AML views write `aml_access` on the audit event.

These controls have not been independently assured.
