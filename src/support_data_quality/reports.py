"""Machine-readable and reviewer-friendly pipeline reports."""

from __future__ import annotations

import json
from pathlib import Path

from support_data_quality.models import RunSummary


def write_reports(summary: RunSummary, output_dir: Path) -> tuple[Path, Path]:
    run_dir = output_dir / summary.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    json_path = run_dir / "summary.json"
    markdown_path = run_dir / "summary.md"
    json_path.write_text(
        json.dumps(summary.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    dimensions = "\n".join(
        f"| {name.title()} | {score:.2%} |" for name, score in summary.quality_dimensions.items()
    )
    markdown_path.write_text(
        f"""# Data quality run `{summary.run_id}`

- Status: **{summary.status}**
- Input SHA-256: `{summary.input_hash}`
- Format: `{summary.input_format.value}`
- Dry run: `{str(summary.dry_run).lower()}`
- Incremental: `{str(summary.incremental).lower()}`
- Records: {summary.total_records:,}
- Accepted: {summary.accepted_records:,}
- Quarantined: {summary.quarantined_records:,}
- Duplicates: {summary.duplicate_records:,}
- Loaded: {summary.loaded_records:,}
- Unchanged: {summary.unchanged_records:,}
- Duration: {summary.duration_seconds:.3f} seconds
- Throughput: {summary.records_per_second:,.2f} records/second
- Quality gate: **{"PASS" if summary.quality_gate_passed else "FAIL"}**

## Quality dimensions

| Dimension | Score |
| --- | ---: |
{dimensions}

Overall score: **{summary.quality_score:.2%}** (threshold: {summary.quality_threshold:.2%}).
""",
        encoding="utf-8",
    )
    return json_path, markdown_path
