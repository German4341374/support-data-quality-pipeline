# Security Policy

Report vulnerabilities privately through GitHub's security advisory feature. Do not open public issues containing Service Desk exports, database URLs, quarantine samples, or credentials.

The pipeline masks common email addresses and phone numbers before persistence, but masking is not anonymization. Restrict access to source files, artifacts, PostgreSQL, and logs; use an external secret manager in production; rotate database credentials; and review custom fields before extending the schema.

Supported security fixes target the latest release on `main`.
