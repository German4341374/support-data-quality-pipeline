from __future__ import annotations

from pathlib import Path

import psycopg
import pytest

from support_data_quality.generator import generate_dataset
from support_data_quality.models import InputFormat, PipelineRules
from support_data_quality.pipeline import InjectedFailure, execute_pipeline
from support_data_quality.storage import PipelineStore

pytestmark = pytest.mark.integration


def clean_database(store: PipelineStore) -> None:
    with store.connect() as connection, connection.cursor() as cursor:
        cursor.execute("TRUNCATE pipeline_runs CASCADE")


def execute(path: Path, rules: PipelineRules, store: PipelineStore, tmp_path: Path, **kwargs):  # type: ignore[no-untyped-def]
    return execute_pipeline(
        input_path=path,
        rules=rules,
        store=store,
        migrations_dir=Path(__file__).parents[1] / "migrations",
        output_dir=tmp_path / "artifacts",
        **kwargs,
    )


def test_rerun_is_idempotent(tmp_path: Path, rules: PipelineRules, database_url_value: str) -> None:
    store = PipelineStore(database_url_value)
    store.migrate(Path(__file__).parents[1] / "migrations")
    clean_database(store)
    path = tmp_path / "input.jsonl"
    generate_dataset(path, input_format=InputFormat.JSONL, records=8, invalid_rate=0)
    first = execute(path, rules, store, tmp_path)
    second = execute(path, rules, store, tmp_path)
    assert first.run_id == second.run_id
    assert first.total_records == second.total_records == 8
    with store.connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT count(*) AS count FROM tickets")
        assert cursor.fetchone()["count"] == first.loaded_records


def test_resume_after_injected_failure(
    tmp_path: Path, rules: PipelineRules, database_url_value: str
) -> None:
    store = PipelineStore(database_url_value)
    store.migrate(Path(__file__).parents[1] / "migrations")
    clean_database(store)
    path = tmp_path / "input.csv"
    generate_dataset(path, input_format=InputFormat.CSV, records=7, invalid_rate=0)
    with pytest.raises(InjectedFailure):
        execute(path, rules, store, tmp_path, fail_after_batches=1)
    completed = execute(path, rules, store, tmp_path)
    assert completed.status == "COMPLETED"
    assert completed.total_records == 7
    assert completed.batches_committed == 4


def test_dry_run_does_not_load_business_tables(
    tmp_path: Path, rules: PipelineRules, database_url_value: str
) -> None:
    store = PipelineStore(database_url_value)
    store.migrate(Path(__file__).parents[1] / "migrations")
    clean_database(store)
    path = tmp_path / "input.parquet"
    generate_dataset(path, input_format=InputFormat.PARQUET, records=5, invalid_rate=0)
    summary = execute(path, rules, store, tmp_path, dry_run=True)
    assert summary.accepted_records == 5
    assert summary.loaded_records == 0
    with store.connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT count(*) AS count FROM tickets")
        assert cursor.fetchone()["count"] == 0
        cursor.execute("SELECT count(*) AS count FROM quarantine_records")
        assert cursor.fetchone()["count"] == 0


def test_incremental_mode_updates_only_newer_records(
    tmp_path: Path, rules: PipelineRules, database_url_value: str, valid_row: dict[str, str]
) -> None:
    store = PipelineStore(database_url_value)
    store.migrate(Path(__file__).parents[1] / "migrations")
    clean_database(store)
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    import json

    first.write_text(json.dumps(valid_row) + "\n", encoding="utf-8")
    newer = {**valid_row, "title": "Updated VPN issue", "updated_at": "2026-01-01T11:00:00Z"}
    second.write_text(json.dumps(newer) + "\n", encoding="utf-8")
    execute(first, rules, store, tmp_path, incremental=True)
    summary = execute(second, rules, store, tmp_path, incremental=True)
    assert summary.loaded_records == 1
    with psycopg.connect(database_url_value) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT title FROM tickets WHERE ticket_id = 'SD-1'")
        assert cursor.fetchone()[0] == "Updated VPN issue"
