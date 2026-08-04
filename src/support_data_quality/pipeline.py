"""Pipeline orchestration with resumable, transactional batches."""

from __future__ import annotations

import time
from pathlib import Path

from support_data_quality.config import rules_hash
from support_data_quality.models import InputFormat, PipelineRules, RunSummary
from support_data_quality.readers import batched, detect_format, file_sha256, iter_rows
from support_data_quality.reports import write_reports
from support_data_quality.storage import PipelineStore
from support_data_quality.transform import normalize_row


class InjectedFailure(RuntimeError):
    """Raised intentionally after a committed batch to demonstrate safe resume."""


def execute_pipeline(
    *,
    input_path: Path,
    rules: PipelineRules,
    store: PipelineStore,
    migrations_dir: Path,
    output_dir: Path,
    explicit_format: InputFormat | None = None,
    dry_run: bool = False,
    incremental: bool = False,
    fail_after_batches: int | None = None,
) -> RunSummary:
    if not input_path.is_file():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")
    store.migrate(migrations_dir)
    input_format = detect_format(input_path, explicit_format)
    input_hash = file_sha256(input_path)
    config_hash = rules_hash(rules)
    state = store.prepare_run(
        input_path=input_path,
        input_hash=input_hash,
        input_format=input_format.value,
        input_size=input_path.stat().st_size,
        config_hash=config_hash,
        rules=rules,
        dry_run=dry_run,
        incremental=incremental,
    )
    if state.status == "COMPLETED":
        completed = RunSummary.model_validate(
            store.summary(state.run_id, quality_threshold=rules.quality_threshold)
        )
        if not completed.report_json or not Path(completed.report_json).is_file():
            json_path, markdown_path = write_reports(completed, output_dir)
            store.set_report_paths(state.run_id, json_path, markdown_path)
            return completed.model_copy(
                update={"report_json": str(json_path), "report_markdown": str(markdown_path)}
            )
        return completed

    started = time.perf_counter()
    try:
        source = iter_rows(
            input_path,
            input_format,
            batch_size=rules.batch_size,
            start_offset=state.row_offset,
        )
        for relative_index, batch in enumerate(batched(source, rules.batch_size), start=1):
            processed = [normalize_row(row, rules) for row in batch]
            batch_index = state.batch_index + relative_index
            new_offset = state.row_offset + relative_index * rules.batch_size
            if len(batch) < rules.batch_size:
                new_offset = state.row_offset + (relative_index - 1) * rules.batch_size + len(batch)
            store.process_batch(
                run_id=state.run_id,
                input_hash=input_hash,
                rows=processed,
                new_offset=new_offset,
                batch_index=batch_index,
                rules=rules,
                dry_run=dry_run,
                incremental=incremental,
            )
            if fail_after_batches is not None and relative_index >= fail_after_batches:
                raise InjectedFailure(
                    f"Fault injected after {relative_index} batch(es); checkpoint is durable"
                )
        elapsed = time.perf_counter() - started
        store.complete(state.run_id, elapsed)
    except Exception as error:
        store.mark_failed(state.run_id, error)
        raise

    summary = RunSummary.model_validate(
        store.summary(state.run_id, quality_threshold=rules.quality_threshold)
    )
    json_path, markdown_path = write_reports(summary, output_dir)
    store.set_report_paths(state.run_id, json_path, markdown_path)
    return summary.model_copy(
        update={"report_json": str(json_path), "report_markdown": str(markdown_path)}
    )
