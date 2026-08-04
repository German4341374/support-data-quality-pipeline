from pathlib import Path

from support_data_quality.models import InputFormat, RunSummary
from support_data_quality.reports import write_reports


def test_writes_json_and_markdown_reports(tmp_path: Path) -> None:
    summary = RunSummary(
        run_id="00000000-0000-0000-0000-000000000001",
        status="COMPLETED",
        input_path="input.csv",
        input_hash="a" * 64,
        input_format=InputFormat.CSV,
        config_hash="b" * 64,
        dry_run=True,
        incremental=False,
        total_records=10,
        accepted_records=9,
        quarantined_records=1,
        duplicate_records=0,
        loaded_records=0,
        unchanged_records=0,
        resumed_from_offset=10,
        batches_committed=1,
        duration_seconds=1.0,
        records_per_second=10.0,
        quality_dimensions={"validity": 0.9},
        quality_score=0.9,
        quality_threshold=0.85,
        quality_gate_passed=True,
    )
    json_path, markdown_path = write_reports(summary, tmp_path)
    assert json_path.is_file()
    assert "Quality dimensions" in markdown_path.read_text(encoding="utf-8")
