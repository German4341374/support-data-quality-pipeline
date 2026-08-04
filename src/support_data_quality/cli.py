"""Typer command-line interface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from support_data_quality.config import database_url, load_rules
from support_data_quality.generator import generate_dataset
from support_data_quality.models import InputFormat, RunSummary
from support_data_quality.pipeline import execute_pipeline
from support_data_quality.storage import PipelineStore

app = typer.Typer(no_args_is_help=True, help="Validate and load Service Desk data safely.")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "rules.example.yaml"
DEFAULT_MIGRATIONS = PROJECT_ROOT / "migrations"


def _store() -> PipelineStore:
    return PipelineStore(database_url())


def _print_summary(summary: RunSummary) -> None:
    typer.echo(json.dumps(summary.model_dump(mode="json"), indent=2, sort_keys=True))


@app.command()
def migrate(
    migrations: Annotated[Path, typer.Option(exists=True, file_okay=False)] = DEFAULT_MIGRATIONS,
) -> None:
    """Apply checksum-protected PostgreSQL migrations."""
    applied = _store().migrate(migrations)
    typer.echo(f"Applied migrations: {', '.join(applied) if applied else 'none'}")


@app.command("generate-demo")
def generate_demo(
    output: Annotated[Path, typer.Argument()],
    input_format: Annotated[InputFormat, typer.Option("--format")] = InputFormat.CSV,
    records: Annotated[int, typer.Option(min=1, max=10_000_000)] = 100_000,
    seed: int = 20260804,
    duplicate_rate: Annotated[float, typer.Option(min=0, max=1)] = 0.01,
    invalid_rate: Annotated[float, typer.Option(min=0, max=1)] = 0.02,
) -> None:
    """Create a deterministic large dataset without real personal data."""
    generate_dataset(
        output,
        input_format=input_format,
        records=records,
        seed=seed,
        duplicate_rate=duplicate_rate,
        invalid_rate=invalid_rate,
    )
    typer.echo(f"Generated {records} {input_format.value} records at {output}")


@app.command("run")
def run_pipeline(
    input_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    config: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = DEFAULT_CONFIG,
    input_format: Annotated[InputFormat | None, typer.Option("--format")] = None,
    output_dir: Path = Path("artifacts"),
    dry_run: bool = False,
    incremental: bool = False,
    fail_after_batches: Annotated[int | None, typer.Option(min=1)] = None,
) -> None:
    """Execute or transparently resume an input/config combination."""
    summary = execute_pipeline(
        input_path=input_path,
        rules=load_rules(config),
        store=_store(),
        migrations_dir=DEFAULT_MIGRATIONS,
        output_dir=output_dir,
        explicit_format=input_format,
        dry_run=dry_run,
        incremental=incremental,
        fail_after_batches=fail_after_batches,
    )
    _print_summary(summary)
    if not summary.quality_gate_passed:
        raise typer.Exit(code=2)


@app.command()
def report(
    run_id: Annotated[str, typer.Argument()],
    threshold: Annotated[float, typer.Option(min=0, max=1)] = 0.85,
) -> None:
    """Print a stored run summary."""
    summary = RunSummary.model_validate(_store().summary(run_id, quality_threshold=threshold))
    _print_summary(summary)


@app.command()
def quarantine(
    run_id: Annotated[str, typer.Argument()],
    limit: Annotated[int, typer.Option(min=1, max=10_000)] = 100,
) -> None:
    """Inspect masked rejected records for remediation."""
    rows = list(_store().quarantine(run_id, limit))
    typer.echo(json.dumps(rows, indent=2, default=str))
