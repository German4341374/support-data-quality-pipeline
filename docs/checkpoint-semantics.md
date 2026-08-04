# Checkpoints, idempotency, and retries

## Identity

A run key is derived from the SHA-256 input hash, canonical configuration hash, dry-run flag, and incremental flag. Two byte-identical inputs using the same semantics resolve to one run. Concurrent starters serialize through a PostgreSQL advisory transaction lock and the unique run key.

## Checkpoint semantics

The checkpoint is the count of source rows durably handled plus the committed batch index. It advances only in the same transaction as target, quarantine, deduplication, and metric changes. Resume reopens the input and skips the committed row count. This is intentionally simple and portable; for very large compressed or remote objects, a seekable source offset or object-store cursor would be more efficient.

`--fail-after-batches N` throws an intentional error after batch `N` commits. Repeating the exact `run` command locates the failed run and resumes from its checkpoint.

## Exactly-once limitations

The database effects are effectively-once for one immutable local input and one configuration because each batch and its checkpoint share a transaction. End-to-end exactly-once is not guaranteed: the filesystem and PostgreSQL do not share a distributed transaction; a file may be replaced between hashing and reading; report files are written after database completion; and downstream consumers can create independent effects.

Production mitigations include immutable object versions, verifying source metadata before every resume, transactional outbox events for downstream delivery, retention of run keys, and consumers that enforce their own idempotency keys.

## Incremental mode

The natural target key is `(source_system, ticket_id)`. Incremental loads update an existing ticket only when the incoming `updated_at` is later. Older or equal records are counted as unchanged. Standard mode uses insert-on-conflict-do-nothing.
