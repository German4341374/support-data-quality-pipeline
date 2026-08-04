from __future__ import annotations

from pathlib import Path

import pytest

from support_data_quality.generator import generate_dataset, synthetic_rows
from support_data_quality.models import InputFormat
from support_data_quality.readers import iter_rows


def test_generator_is_deterministic() -> None:
    assert list(synthetic_rows(4, seed=42)) == list(synthetic_rows(4, seed=42))


def test_generator_contains_no_real_domains() -> None:
    rows = list(synthetic_rows(10))
    assert all(str(row["requester_email"]).endswith("@example.invalid") for row in rows)


@pytest.mark.parametrize("input_format", list(InputFormat))
def test_generates_each_supported_format(tmp_path: Path, input_format: InputFormat) -> None:
    path = tmp_path / f"input.{input_format.value}"
    generate_dataset(path, input_format=input_format, records=7)
    assert len(list(iter_rows(path, input_format, batch_size=3))) == 7
