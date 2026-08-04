# Repository Guidance

- Use English for code, documentation, configuration, and commits.
- Preserve streaming behavior; do not materialize complete input datasets.
- Keep checkpoint and business writes in the same PostgreSQL transaction.
- Never add real Service Desk data, secrets, or benchmark numbers that were not measured.
- Add migrations instead of editing an applied migration.
- Run formatting, linting, type checking, unit tests, integration tests, and package build before release.
