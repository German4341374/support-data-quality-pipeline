CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    checksum text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id uuid PRIMARY KEY,
    run_key text NOT NULL UNIQUE,
    input_path text NOT NULL,
    input_hash text NOT NULL,
    input_format text NOT NULL CHECK (input_format IN ('csv', 'jsonl', 'parquet')),
    config_hash text NOT NULL,
    config_json jsonb NOT NULL,
    dry_run boolean NOT NULL,
    incremental boolean NOT NULL,
    status text NOT NULL CHECK (status IN ('PENDING', 'RUNNING', 'FAILED', 'COMPLETED')),
    total_records bigint NOT NULL DEFAULT 0,
    accepted_records bigint NOT NULL DEFAULT 0,
    quarantined_records bigint NOT NULL DEFAULT 0,
    duplicate_records bigint NOT NULL DEFAULT 0,
    loaded_records bigint NOT NULL DEFAULT 0,
    unchanged_records bigint NOT NULL DEFAULT 0,
    batches_committed bigint NOT NULL DEFAULT 0,
    quality_records bigint NOT NULL DEFAULT 0,
    quality_totals jsonb NOT NULL DEFAULT '{"completeness":0,"uniqueness":0,"validity":0,"consistency":0,"timeliness":0}'::jsonb,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    duration_seconds double precision,
    error_message text,
    report_json text,
    report_markdown text
);

CREATE TABLE IF NOT EXISTS lineage_metadata (
    run_id uuid PRIMARY KEY REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    source_system text NOT NULL,
    original_path text NOT NULL,
    input_size_bytes bigint NOT NULL CHECK (input_size_bytes >= 0),
    input_hash text NOT NULL,
    input_format text NOT NULL,
    config_hash text NOT NULL,
    schema_version integer NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pipeline_checkpoints (
    run_id uuid PRIMARY KEY REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    row_offset bigint NOT NULL DEFAULT 0,
    batch_index bigint NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS processed_ticket_keys (
    run_id uuid NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    ticket_key text NOT NULL,
    first_row_number bigint NOT NULL,
    PRIMARY KEY (run_id, ticket_key)
);

CREATE TABLE IF NOT EXISTS tickets (
    source_system text NOT NULL,
    ticket_id text NOT NULL,
    title text NOT NULL,
    description text NOT NULL,
    status text NOT NULL,
    priority text NOT NULL,
    requester_email text NOT NULL,
    assignee text,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    resolved_at timestamptz,
    source_input_hash text NOT NULL,
    source_run_id uuid NOT NULL REFERENCES pipeline_runs(id),
    loaded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_system, ticket_id)
);

CREATE INDEX IF NOT EXISTS tickets_status_idx ON tickets (status);
CREATE INDEX IF NOT EXISTS tickets_priority_idx ON tickets (priority);
CREATE INDEX IF NOT EXISTS tickets_updated_at_idx ON tickets (updated_at DESC);

CREATE TABLE IF NOT EXISTS quarantine_records (
    id bigserial PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    row_number bigint NOT NULL,
    masked_raw jsonb NOT NULL,
    violations jsonb NOT NULL,
    quarantined_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, row_number)
);

CREATE INDEX IF NOT EXISTS quarantine_run_idx ON quarantine_records (run_id, row_number);

CREATE TABLE IF NOT EXISTS quality_metrics (
    run_id uuid NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    dimension text NOT NULL CHECK (dimension IN ('completeness', 'uniqueness', 'validity', 'consistency', 'timeliness')),
    score double precision NOT NULL CHECK (score BETWEEN 0 AND 1),
    measured_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, dimension)
);
