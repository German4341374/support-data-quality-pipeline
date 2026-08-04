"""Deterministic, privacy-safe Service Desk export generator."""

from __future__ import annotations

import csv
import json
import random
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from support_data_quality.models import InputFormat

FIELDS = [
    "ticket_id",
    "title",
    "description",
    "status",
    "priority",
    "requester_email",
    "assignee",
    "created_at",
    "updated_at",
    "resolved_at",
    "source_system",
]


def synthetic_rows(
    records: int,
    *,
    seed: int = 20260804,
    duplicate_rate: float = 0.01,
    invalid_rate: float = 0.02,
) -> Iterator[dict[str, Any]]:
    rng = random.Random(seed)  # noqa: S311 -- deterministic test data, not security.
    base = datetime(2025, 11, 1, tzinfo=UTC)
    statuses = ["Open", "In Progress", "Pending", "Resolved", "Closed"]
    priorities = ["Low", "Medium", "High", "Critical"]
    for index in range(records):
        duplicate = index > 0 and rng.random() < duplicate_rate
        ticket_number = max(0, index - 1) if duplicate else index
        status = statuses[index % len(statuses)]
        created = base + timedelta(minutes=index % 80_000)
        updated = created + timedelta(minutes=5 + index % 240)
        resolved = updated if status in {"Resolved", "Closed"} else None
        row: dict[str, Any] = {
            "ticket_id": f"SD-{ticket_number:09d}",
            "title": f"Synthetic support issue {index % 500}",
            "description": f"Demonstration record {index}; contact +1-202-555-{index % 10_000:04d}",
            "status": status,
            "priority": priorities[index % len(priorities)],
            "requester_email": f"requester{index % 10_000}@example.invalid",
            "assignee": f"engineer-{index % 100}",
            "created_at": created.isoformat(),
            "updated_at": updated.isoformat(),
            "resolved_at": resolved.isoformat() if resolved else "",
            "source_system": "synthetic-service-desk",
        }
        if rng.random() < invalid_rate:
            failure = index % 4
            if failure == 0:
                row["title"] = ""
            elif failure == 1:
                row["status"] = "Mystery"
            elif failure == 2:
                row["updated_at"] = "not-a-date"
            else:
                row["resolved_at"] = (created - timedelta(hours=1)).isoformat()
        yield row


def generate_dataset(
    output: Path,
    *,
    input_format: InputFormat,
    records: int,
    seed: int = 20260804,
    duplicate_rate: float = 0.01,
    invalid_rate: float = 0.02,
    parquet_batch_size: int = 10_000,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = synthetic_rows(
        records,
        seed=seed,
        duplicate_rate=duplicate_rate,
        invalid_rate=invalid_rate,
    )
    if input_format == InputFormat.CSV:
        with output.open("w", encoding="utf-8", newline="") as target:
            csv_writer = csv.DictWriter(target, fieldnames=FIELDS)
            csv_writer.writeheader()
            csv_writer.writerows(rows)
        return
    if input_format == InputFormat.JSONL:
        with output.open("w", encoding="utf-8") as target:
            for row in rows:
                target.write(json.dumps(row, separators=(",", ":")) + "\n")
        return
    parquet_writer: pq.ParquetWriter | None = None
    buffer: list[dict[str, Any]] = []
    try:
        for row in rows:
            buffer.append(row)
            if len(buffer) >= parquet_batch_size:
                table = pa.Table.from_pylist(buffer)
                parquet_writer = parquet_writer or pq.ParquetWriter(
                    output, table.schema, compression="zstd"
                )
                parquet_writer.write_table(table)
                buffer.clear()
        if buffer:
            table = pa.Table.from_pylist(buffer)
            parquet_writer = parquet_writer or pq.ParquetWriter(
                output, table.schema, compression="zstd"
            )
            parquet_writer.write_table(table)
    finally:
        if parquet_writer is not None:
            parquet_writer.close()
