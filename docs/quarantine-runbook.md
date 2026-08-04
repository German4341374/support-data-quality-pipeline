# Quarantine runbook

Quarantine is a remediation queue, not a data-loss path. Stored payloads are masked before persistence and retain row number, run lineage, and machine-readable violations.

1. Identify the run from the JSON report.
2. Inspect a bounded sample: `support-data-quality quarantine RUN_ID --limit 50`.
3. Group by violation code in PostgreSQL; never export unbounded quarantine data to chat or tickets.
4. Correct the source export or versioned rule configuration.
5. Run in `--dry-run` first and compare dimension scores.
6. Submit a new immutable file. A corrected file has a new hash and therefore a new run.
7. Retain the old run for audit; purge according to the organization's approved retention policy.

If masking misses a custom PII field, stop processing, restrict artifact access, extend `mask_mapping`, test it, rotate exposed identifiers where applicable, and follow the incident process in `SECURITY.md`.
