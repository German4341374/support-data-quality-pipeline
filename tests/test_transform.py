from __future__ import annotations

from copy import deepcopy

from support_data_quality.models import InputRow, PipelineRules
from support_data_quality.transform import normalize_row, quality_scores


def process(data: dict[str, str], rules: PipelineRules):  # type: ignore[no-untyped-def]
    return normalize_row(InputRow(row_number=1, data=data), rules)


def test_normalizes_status_and_priority(valid_row: dict[str, str], rules: PipelineRules) -> None:
    result = process(valid_row, rules)
    assert result.accepted
    assert result.ticket is not None
    assert result.ticket.status.value == "Open"
    assert result.ticket.priority.value == "Critical"


def test_masks_pii_before_model_creation(valid_row: dict[str, str], rules: PipelineRules) -> None:
    result = process(valid_row, rules)
    assert result.ticket is not None
    assert result.ticket.requester_email.endswith("@masked.invalid")
    assert "202-555" not in result.ticket.description


def test_invalid_status_is_rejected(valid_row: dict[str, str], rules: PipelineRules) -> None:
    row = deepcopy(valid_row)
    row["status"] = "Unknown"
    result = process(row, rules)
    assert not result.accepted
    assert {violation.code for violation in result.violations} >= {"invalid_status"}


def test_bad_timestamp_is_rejected(valid_row: dict[str, str], rules: PipelineRules) -> None:
    row = deepcopy(valid_row)
    row["created_at"] = "yesterday-ish"
    result = process(row, rules)
    assert not result.accepted
    assert result.ticket is None


def test_resolved_ticket_requires_resolution(
    valid_row: dict[str, str], rules: PipelineRules
) -> None:
    row = deepcopy(valid_row)
    row["status"] = "done"
    result = process(row, rules)
    assert not result.accepted
    assert "resolved_timestamp_missing" in {item.code for item in result.violations}


def test_active_ticket_cannot_have_resolution(
    valid_row: dict[str, str], rules: PipelineRules
) -> None:
    row = deepcopy(valid_row)
    row["resolved_at"] = "2025-12-31T10:06:00Z"
    result = process(row, rules)
    assert not result.accepted
    assert "active_ticket_has_resolution" in {item.code for item in result.violations}


def test_stale_record_reduces_timeliness(valid_row: dict[str, str], rules: PipelineRules) -> None:
    row = deepcopy(valid_row)
    row["created_at"] = "2020-01-01T00:00:00Z"
    row["updated_at"] = "2020-01-02T00:00:00Z"
    result = process(row, rules)
    assert result.accepted
    assert quality_scores(result, len(rules.required_fields))["timeliness"] == 0.0


def test_corrupt_reader_row_is_quarantined(rules: PipelineRules) -> None:
    result = normalize_row(InputRow(row_number=2, read_error="bad JSON"), rules)
    assert not result.accepted
    assert result.violations[0].code == "read_error"


def test_duplicate_reduces_uniqueness(valid_row: dict[str, str], rules: PipelineRules) -> None:
    result = process(valid_row, rules)
    result.duplicate = True
    assert quality_scores(result, len(rules.required_fields))["uniqueness"] == 0.0
