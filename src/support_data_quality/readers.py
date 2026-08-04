"""Streaming input readers."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

import pyarrow.parquet as pq  # type: ignore[import-untyped]

from support_data_quality.models import InputFormat, InputRow


def detect_format(path: Path, explicit: InputFormat | None = None) -> InputFormat:
    if explicit is not None:
        return explicit
    suffix = path.suffix.casefold()
    if suffix == ".csv":
        return InputFormat.CSV
    if suffix in {".jsonl", ".ndjson"}:
        return InputFormat.JSONL
    if suffix == ".parquet":
        return InputFormat.PARQUET
    raise ValueError(f"Cannot detect format from extension: {path.name}")


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _csv_rows(path: Path) -> Iterator[InputRow]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames:
            raise ValueError("CSV input has no header")
        for row_number, row in enumerate(reader, start=1):
            yield InputRow(row_number=row_number, data=dict(row))


def _jsonl_rows(path: Path) -> Iterator[InputRow]:
    with path.open("r", encoding="utf-8") as source:
        for row_number, line in enumerate(source, start=1):
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("JSON Lines value must be an object")
                yield InputRow(row_number=row_number, data=value)
            except (json.JSONDecodeError, ValueError) as error:
                yield InputRow(
                    row_number=row_number, read_error=str(error), data={"raw": line[:1000]}
                )


def _parquet_rows(path: Path, batch_size: int) -> Iterator[InputRow]:
    parquet = pq.ParquetFile(path)
    row_number = 0
    for batch in parquet.iter_batches(batch_size=batch_size):
        for row in batch.to_pylist():
            row_number += 1
            yield InputRow(row_number=row_number, data=row)


def iter_rows(
    path: Path,
    input_format: InputFormat,
    *,
    batch_size: int,
    start_offset: int = 0,
) -> Iterator[InputRow]:
    readers = {
        InputFormat.CSV: lambda: _csv_rows(path),
        InputFormat.JSONL: lambda: _jsonl_rows(path),
        InputFormat.PARQUET: lambda: _parquet_rows(path, batch_size),
    }
    for offset, row in enumerate(readers[input_format](), start=1):
        if offset > start_offset:
            yield row


def batched(rows: Iterator[InputRow], size: int) -> Iterator[list[InputRow]]:
    batch: list[InputRow] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch
