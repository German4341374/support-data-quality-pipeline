from __future__ import annotations

import csv
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from support_data_quality.models import InputFormat
from support_data_quality.readers import batched, detect_format, file_sha256, iter_rows


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("input.csv", InputFormat.CSV),
        ("input.jsonl", InputFormat.JSONL),
        ("input.parquet", InputFormat.PARQUET),
    ],
)
def test_detects_supported_formats(name: str, expected: InputFormat) -> None:
    assert detect_format(Path(name)) == expected


def test_unknown_extension_fails() -> None:
    with pytest.raises(ValueError, match="Cannot detect"):
        detect_format(Path("input.txt"))


def test_reads_csv_stream(tmp_path: Path) -> None:
    path = tmp_path / "tickets.csv"
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=["ticket_id"])
        writer.writeheader()
        writer.writerows([{"ticket_id": "1"}, {"ticket_id": "2"}])
    assert [row.data for row in iter_rows(path, InputFormat.CSV, batch_size=2)] == [
        {"ticket_id": "1"},
        {"ticket_id": "2"},
    ]


def test_jsonl_keeps_corrupt_line_as_rejected_record(tmp_path: Path) -> None:
    path = tmp_path / "tickets.jsonl"
    path.write_text('{"ticket_id":"1"}\nnot-json\n', encoding="utf-8")
    rows = list(iter_rows(path, InputFormat.JSONL, batch_size=2))
    assert rows[0].data == {"ticket_id": "1"}
    assert rows[1].read_error is not None


def test_reads_parquet_in_batches(tmp_path: Path) -> None:
    path = tmp_path / "tickets.parquet"
    pq.write_table(pa.Table.from_pylist([{"ticket_id": "1"}, {"ticket_id": "2"}]), path)
    assert len(list(iter_rows(path, InputFormat.PARQUET, batch_size=1))) == 2


def test_resume_offset_skips_committed_rows(tmp_path: Path) -> None:
    path = tmp_path / "tickets.jsonl"
    path.write_text("\n".join(json.dumps({"id": i}) for i in range(5)), encoding="utf-8")
    rows = list(iter_rows(path, InputFormat.JSONL, batch_size=2, start_offset=3))
    assert [row.row_number for row in rows] == [4, 5]


def test_batched_preserves_partial_final_batch(tmp_path: Path) -> None:
    path = tmp_path / "tickets.jsonl"
    path.write_text("\n".join(json.dumps({"id": i}) for i in range(5)), encoding="utf-8")
    groups = list(batched(iter_rows(path, InputFormat.JSONL, batch_size=2), 2))
    assert [len(group) for group in groups] == [2, 2, 1]


def test_file_hash_is_stable(tmp_path: Path) -> None:
    path = tmp_path / "input.csv"
    path.write_bytes(b"stable\n")
    assert file_sha256(path) == file_sha256(path)
