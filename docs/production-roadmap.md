# Production roadmap

This prototype must not be deployed as a bank system. The following would be required before any production discussion, and completing them would still need independent assurance.

- Legal, compliance, financial-crime, model-risk, privacy and cybersecurity review, including the regulatory register.
- A decision that the use case is permitted, with named accountable executives.
- Replacement of synthetic authentication with the bank identity provider, joiner-mover-leaver, and step-up for sensitive views.
- PostgreSQL or the bank's approved database, with tested migrations, backups and restoration drills. SQLite triggers are not a substitute.
- An approved document repository behind `TrustedDocumentStore`, malware scanning, and a real retention and legal-hold process.
- Row-level entitlements enforced in the database, not only in the application.
- A reviewed embedding and, if ever used, a reviewed model host inside the permitted residency boundary. The default must remain able to run without an external model.
- Independent model validation, change control, and monitoring for groundedness, drift and incidents.
- Penetration testing, secret management, network controls, and immutable audit storage.
- Human processes for credit, AML and regulatory decisions that do not treat this draft as an input to a decision unless a separate policy says so.

Until that work is done, the only supported use is a supervised hackathon demonstration on synthetic data.
