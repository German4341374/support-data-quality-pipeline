# Five-minute demonstration

1. Explain the architecture diagram in `README.md` (30 seconds).
2. Start the local database and apply migrations: `make up` (45 seconds).
3. Generate 10,000 safe records: `make demo` (30 seconds).
4. Run the incremental pipeline: `make run` (60 seconds).
5. Open the generated JSON/Markdown report and show five quality dimensions (45 seconds).
6. Run the same command again and show the same run ID and unchanged counters (30 seconds).
7. Demonstrate recovery with `--fail-after-batches 2`, then repeat without that option (45 seconds).
8. Show lineage, quarantine, the transaction boundary, and the successful GitHub Actions checks (60 seconds).

Reset with `make clean`. This removes the local PostgreSQL volume and generated data.
