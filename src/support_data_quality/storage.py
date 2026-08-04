"""PostgreSQL persistence, checkpointing, and idempotent loading."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg import Connection, sql
from psycopg.rows import dict_row

from support_data_quality.models import PipelineRules, ProcessedRow, QualityAccumulator, Violation
from support_data_quality.transform import quality_scores


@dataclass(frozen=True)
class RunState:
    run_id: str
    status: str
    row_offset: int
    batch_index: int
    resumed: bool


@dataclass(frozen=True)
class BatchResult:
    total: int
    accepted: int
    quarantined: int
    duplicates: int
    loaded: int
    unchanged: int


class PipelineStore:
    """Owns all database effects and keeps each batch transactionally atomic."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def connect(self) -> Connection[dict[str, Any]]:
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def migrate(self, migrations_dir: Path) -> list[str]:
        applied: list[str] = []
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (72_604_921,))
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                    version text PRIMARY KEY,
                    checksum text NOT NULL,
                    applied_at timestamptz NOT NULL DEFAULT now()
                )"""
            )
            for migration in sorted(migrations_dir.glob("*.sql")):
                body = migration.read_text(encoding="utf-8")
                checksum = hashlib.sha256(body.encode()).hexdigest()
                cursor.execute(
                    "SELECT checksum FROM schema_migrations WHERE version = %s",
                    (migration.name,),
                )
                existing = cursor.fetchone()
                if existing:
                    if existing["checksum"] != checksum:
                        raise RuntimeError(f"Applied migration changed: {migration.name}")
                    continue
                cursor.execute(sql.SQL(body))
                cursor.execute(
                    "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                    (migration.name, checksum),
                )
                applied.append(migration.name)
        return applied

    def prepare_run(
        self,
        *,
        input_path: Path,
        input_hash: str,
        input_format: str,
        input_size: int,
        config_hash: str,
        rules: PipelineRules,
        dry_run: bool,
        incremental: bool,
    ) -> RunState:
        identity = f"{input_hash}:{config_hash}:{int(dry_run)}:{int(incremental)}"
        run_key = hashlib.sha256(identity.encode()).hexdigest()
        run_id = str(uuid.uuid4())
        config_json = json.dumps(rules.model_dump(mode="json"), sort_keys=True)
        lock_key = int(run_key[:15], 16)
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))
            cursor.execute(
                """INSERT INTO pipeline_runs (
                    id, run_key, input_path, input_hash, input_format, config_hash,
                    config_json, dry_run, incremental, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, 'PENDING')
                ON CONFLICT (run_key) DO NOTHING""",
                (
                    run_id,
                    run_key,
                    str(input_path.resolve()),
                    input_hash,
                    input_format,
                    config_hash,
                    config_json,
                    dry_run,
                    incremental,
                ),
            )
            cursor.execute(
                "SELECT id::text, status FROM pipeline_runs WHERE run_key = %s FOR UPDATE",
                (run_key,),
            )
            run = cursor.fetchone()
            if run is None:
                raise RuntimeError("Failed to create or locate pipeline run")
            actual_id = str(run["id"])
            cursor.execute(
                """INSERT INTO pipeline_checkpoints (run_id) VALUES (%s)
                ON CONFLICT (run_id) DO NOTHING""",
                (actual_id,),
            )
            cursor.execute(
                """INSERT INTO lineage_metadata (
                    run_id, source_system, original_path, input_size_bytes, input_hash,
                    input_format, config_hash, schema_version
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO NOTHING""",
                (
                    actual_id,
                    rules.source_system,
                    str(input_path.resolve()),
                    input_size,
                    input_hash,
                    input_format,
                    config_hash,
                    rules.schema_version,
                ),
            )
            cursor.execute(
                "SELECT row_offset, batch_index FROM pipeline_checkpoints WHERE run_id = %s",
                (actual_id,),
            )
            checkpoint = cursor.fetchone()
            if checkpoint is None:
                raise RuntimeError("Run checkpoint is missing")
            was_resumed = run["status"] == "FAILED" or int(checkpoint["row_offset"]) > 0
            if run["status"] != "COMPLETED":
                cursor.execute(
                    """UPDATE pipeline_runs
                    SET status = 'RUNNING', error_message = NULL
                    WHERE id = %s""",
                    (actual_id,),
                )
            return RunState(
                run_id=actual_id,
                status=str(run["status"]),
                row_offset=int(checkpoint["row_offset"]),
                batch_index=int(checkpoint["batch_index"]),
                resumed=was_resumed,
            )

    def process_batch(
        self,
        *,
        run_id: str,
        input_hash: str,
        rows: list[ProcessedRow],
        new_offset: int,
        batch_index: int,
        rules: PipelineRules,
        dry_run: bool,
        incremental: bool,
    ) -> BatchResult:
        counts = {"accepted": 0, "quarantined": 0, "duplicates": 0, "loaded": 0, "unchanged": 0}
        accumulator = QualityAccumulator()
        with self.connect() as connection, connection.cursor() as cursor:
            for row in rows:
                if row.ticket is not None:
                    ticket_key = hashlib.sha256(
                        f"{row.ticket.source_system}:{row.ticket.ticket_id}".encode()
                    ).hexdigest()
                    cursor.execute(
                        """INSERT INTO processed_ticket_keys (run_id, ticket_key, first_row_number)
                        VALUES (%s, %s, %s) ON CONFLICT DO NOTHING RETURNING ticket_key""",
                        (run_id, ticket_key, row.row_number),
                    )
                    if cursor.fetchone() is None:
                        row.duplicate = True
                        row.violations.append(
                            Violation(
                                code="duplicate_ticket_id",
                                dimension="uniqueness",
                                message="Duplicate ticket identifier in this input",
                            )
                        )
                        counts["duplicates"] += 1

                accumulator.add(quality_scores(row, len(rules.required_fields)))
                if row.accepted:
                    counts["accepted"] += 1
                    if not dry_run and row.ticket is not None:
                        loaded = self._load_ticket(
                            cursor,
                            run_id=run_id,
                            input_hash=input_hash,
                            row=row,
                            incremental=incremental,
                        )
                        counts["loaded" if loaded else "unchanged"] += 1
                else:
                    counts["quarantined"] += 1
                    if not dry_run:
                        cursor.execute(
                            """INSERT INTO quarantine_records
                            (run_id, row_number, masked_raw, violations)
                            VALUES (%s, %s, %s::jsonb, %s::jsonb)
                            ON CONFLICT (run_id, row_number) DO NOTHING""",
                            (
                                run_id,
                                row.row_number,
                                json.dumps(row.masked_raw, default=str),
                                json.dumps(
                                    [violation.model_dump() for violation in row.violations]
                                ),
                            ),
                        )

            cursor.execute(
                """UPDATE pipeline_runs SET
                    total_records = total_records + %s,
                    accepted_records = accepted_records + %s,
                    quarantined_records = quarantined_records + %s,
                    duplicate_records = duplicate_records + %s,
                    loaded_records = loaded_records + %s,
                    unchanged_records = unchanged_records + %s,
                    batches_committed = batches_committed + 1,
                    quality_records = quality_records + %s,
                    quality_totals = jsonb_build_object(
                        'completeness', (quality_totals->>'completeness')::float8 + %s,
                        'uniqueness', (quality_totals->>'uniqueness')::float8 + %s,
                        'validity', (quality_totals->>'validity')::float8 + %s,
                        'consistency', (quality_totals->>'consistency')::float8 + %s,
                        'timeliness', (quality_totals->>'timeliness')::float8 + %s
                    )
                WHERE id = %s""",
                (
                    len(rows),
                    counts["accepted"],
                    counts["quarantined"],
                    counts["duplicates"],
                    counts["loaded"],
                    counts["unchanged"],
                    accumulator.records,
                    accumulator.dimension_totals["completeness"],
                    accumulator.dimension_totals["uniqueness"],
                    accumulator.dimension_totals["validity"],
                    accumulator.dimension_totals["consistency"],
                    accumulator.dimension_totals["timeliness"],
                    run_id,
                ),
            )
            cursor.execute(
                """UPDATE pipeline_checkpoints
                SET row_offset = %s, batch_index = %s, updated_at = now()
                WHERE run_id = %s""",
                (new_offset, batch_index, run_id),
            )
        return BatchResult(total=len(rows), **counts)

    @staticmethod
    def _load_ticket(
        cursor: psycopg.Cursor[dict[str, Any]],
        *,
        run_id: str,
        input_hash: str,
        row: ProcessedRow,
        incremental: bool,
    ) -> bool:
        ticket = row.ticket
        if ticket is None:
            return False
        values: tuple[Any, ...] = (
            ticket.source_system,
            ticket.ticket_id,
            ticket.title,
            ticket.description,
            ticket.status.value,
            ticket.priority.value,
            ticket.requester_email,
            ticket.assignee,
            ticket.created_at,
            ticket.updated_at,
            ticket.resolved_at,
            input_hash,
            run_id,
        )
        update_clause = (
            """DO UPDATE SET
            title = EXCLUDED.title,
            description = EXCLUDED.description,
            status = EXCLUDED.status,
            priority = EXCLUDED.priority,
            requester_email = EXCLUDED.requester_email,
            assignee = EXCLUDED.assignee,
            created_at = EXCLUDED.created_at,
            updated_at = EXCLUDED.updated_at,
            resolved_at = EXCLUDED.resolved_at,
            source_input_hash = EXCLUDED.source_input_hash,
            source_run_id = EXCLUDED.source_run_id,
            loaded_at = now()
            WHERE EXCLUDED.updated_at > tickets.updated_at"""
            if incremental
            else "DO NOTHING"
        )
        cursor.execute(
            f"""INSERT INTO tickets (
                source_system, ticket_id, title, description, status, priority,
                requester_email, assignee, created_at, updated_at, resolved_at,
                source_input_hash, source_run_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_system, ticket_id) {update_clause}
            RETURNING ticket_id""",  # noqa: S608 -- clause is selected from constants above.
            values,
        )
        return cursor.fetchone() is not None

    def mark_failed(self, run_id: str, error: Exception) -> None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE pipeline_runs SET status = 'FAILED', error_message = %s WHERE id = %s",
                (str(error)[:2000], run_id),
            )

    def complete(self, run_id: str, duration_seconds: float) -> None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE pipeline_runs
                SET status = 'COMPLETED', completed_at = now(), duration_seconds = %s,
                    error_message = NULL
                WHERE id = %s""",
                (duration_seconds, run_id),
            )
            cursor.execute(
                "DELETE FROM quality_metrics WHERE run_id = %s",
                (run_id,),
            )
            cursor.execute(
                """INSERT INTO quality_metrics (run_id, dimension, score)
                SELECT id, metric.key,
                    CASE WHEN quality_records = 0 THEN 0
                         ELSE metric.value::float8 / quality_records END
                FROM pipeline_runs, jsonb_each_text(quality_totals) AS metric
                WHERE id = %s""",
                (run_id,),
            )

    def set_report_paths(self, run_id: str, json_path: Path, markdown_path: Path) -> None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE pipeline_runs SET report_json = %s, report_markdown = %s WHERE id = %s",
                (str(json_path), str(markdown_path), run_id),
            )

    def summary(self, run_id: str, *, quality_threshold: float) -> dict[str, Any]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT r.*, c.row_offset, c.batch_index
                FROM pipeline_runs r JOIN pipeline_checkpoints c ON c.run_id = r.id
                WHERE r.id = %s""",
                (run_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise KeyError(f"Pipeline run not found: {run_id}")
        records = int(row["quality_records"])
        totals = row["quality_totals"]
        dimensions = {
            key: round(float(value) / records, 6) if records else 0.0
            for key, value in totals.items()
        }
        overall = round(sum(dimensions.values()) / len(dimensions), 6) if dimensions else 0.0
        duration = float(row["duration_seconds"] or 0.0)
        return {
            "run_id": str(row["id"]),
            "status": row["status"],
            "input_path": row["input_path"],
            "input_hash": row["input_hash"],
            "input_format": row["input_format"],
            "config_hash": row["config_hash"],
            "dry_run": row["dry_run"],
            "incremental": row["incremental"],
            "total_records": int(row["total_records"]),
            "accepted_records": int(row["accepted_records"]),
            "quarantined_records": int(row["quarantined_records"]),
            "duplicate_records": int(row["duplicate_records"]),
            "loaded_records": int(row["loaded_records"]),
            "unchanged_records": int(row["unchanged_records"]),
            "resumed_from_offset": int(row["row_offset"]),
            "batches_committed": int(row["batch_index"]),
            "duration_seconds": round(duration, 6),
            "records_per_second": round(int(row["total_records"]) / duration, 2)
            if duration > 0
            else 0.0,
            "quality_dimensions": dimensions,
            "quality_score": overall,
            "quality_threshold": quality_threshold,
            "quality_gate_passed": overall >= quality_threshold,
            "report_json": row["report_json"],
            "report_markdown": row["report_markdown"],
        }

    def quarantine(self, run_id: str, limit: int = 100) -> Iterable[dict[str, Any]]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT row_number, masked_raw, violations, quarantined_at
                FROM quarantine_records WHERE run_id = %s
                ORDER BY row_number LIMIT %s""",
                (run_id, limit),
            )
            return list(cursor.fetchall())
