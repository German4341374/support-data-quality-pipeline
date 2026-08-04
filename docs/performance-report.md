# Performance report

The repository does not contain estimated throughput. The manual **Measured benchmark** workflow creates a deterministic Parquet input, starts a fresh PostgreSQL volume, executes the real pipeline, and uploads raw JSON output and database counts. Results are published here only after that workflow completes successfully on the referenced GitHub-hosted runner.

## Reproduce

Run `make benchmark` for 100,000 records, or dispatch the workflow with a value from 1,000 to 1,000,000. Preserve the raw artifact, runner type, commit SHA, record count, input size, batch size, quality distribution, elapsed duration, and records per second.

No benchmark has been recorded in this file yet.
