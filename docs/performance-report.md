# Performance report

## Recorded run

This result was measured by the repository's production container and PostgreSQL service on a GitHub-hosted `ubuntu-24.04` runner. It is not an estimate.

| Property | Measured value |
| --- | ---: |
| Commit | `ad0b1bfbb35edcd3fc6019422d14af8e07528950` |
| Workflow run | [30900571731](https://github.com/German4341374/support-data-quality-pipeline/actions/runs/30900571731) |
| Measurement time | 2026-08-04 10:25:42 UTC |
| Format | Parquet (Zstandard compression) |
| Requested / processed records | 100,000 / 100,000 |
| Batch size / committed batches | 1,000 / 100 |
| Pipeline duration | 58.579877 seconds |
| Pipeline throughput | 1,707.07 records/second |
| Accepted and loaded | 97,152 |
| Quarantined | 2,848 |
| Duplicate | 900 |
| Overall quality score | 99.4167% |
| Quality gate | Passed (85% threshold) |

The duration is measured inside pipeline orchestration after input hashing and migration/identity setup, and ends after the last batch plus database finalization. It excludes container build, image pull, deterministic dataset generation, and artifact upload. The result describes this runner and workload only; it is not a capacity guarantee.

The initial benchmark did not capture Parquet input size or peak memory, so neither is reported. The benchmark script now records input bytes for future comparisons. Memory behavior is bounded by the 1,000-row application batch plus PyArrow's Parquet batch and driver buffers, but that architecture statement is not a measured peak value.

## Quality dimensions

| Dimension | Measured score |
| --- | ---: |
| Completeness | 99.9317% |
| Uniqueness | 99.1000% |
| Validity | 98.0520% |
| Consistency | 100.0000% |
| Timeliness | 100.0000% |

Raw evidence is committed under [`docs/performance-results/20260804T102542Z`](performance-results/20260804T102542Z/summary.json) and remains available as the workflow artifact for 30 days. The database count of 97,152 matched the pipeline's `loaded_records` count.

## Reproduce

Run `make benchmark` for 100,000 records, or dispatch **Measured benchmark** with a value from 1,000 to 1,000,000. Compare only runs with the same commit, batch size, source profile, database settings, runner class, and reporting boundary.
