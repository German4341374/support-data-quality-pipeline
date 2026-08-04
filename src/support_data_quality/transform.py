"""Normalization and business-rule evaluation."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError

from support_data_quality.masking import mask_email, mask_mapping, mask_text
from support_data_quality.models import (
    InputRow,
    NormalizedTicket,
    PipelineRules,
    ProcessedRow,
    Violation,
)

WHITESPACE = re.compile(r"\s+")


def _text(value: Any) -> str:
    return WHITESPACE.sub(" ", str(value or "").strip())


def _date(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def normalize_row(row: InputRow, rules: PipelineRules) -> ProcessedRow:
    raw = row.data or {}
    masked_raw = mask_mapping(raw)
    violations: list[Violation] = []
    if row.read_error:
        violations.append(
            Violation(code="read_error", dimension="validity", message=row.read_error)
        )
        return ProcessedRow(
            row_number=row.row_number,
            ticket=None,
            masked_raw=masked_raw,
            violations=violations,
        )

    missing = [field for field in rules.required_fields if not _text(raw.get(field))]
    for field in missing:
        violations.append(
            Violation(
                code="required_fields_missing",
                dimension="completeness",
                message=f"Missing required field: {field}",
            )
        )
    normalized_status = rules.status_mapping.get(
        _text(raw.get("status")).casefold(), _text(raw.get("status"))
    )
    normalized_priority = rules.priority_mapping.get(
        _text(raw.get("priority")).casefold(), _text(raw.get("priority"))
    )
    if normalized_status not in rules.allowed_statuses:
        violations.append(
            Violation(
                code="invalid_status",
                dimension="validity",
                message=f"Unsupported status: {normalized_status or '(empty)'}",
            )
        )
    if normalized_priority not in rules.allowed_priorities:
        violations.append(
            Violation(
                code="invalid_priority",
                dimension="validity",
                message=f"Unsupported priority: {normalized_priority or '(empty)'}",
            )
        )

    try:
        created_at = _date(raw.get("created_at"))
        updated_at = _date(raw.get("updated_at"))
        resolved_value = raw.get("resolved_at")
        resolved_at = _date(resolved_value) if _text(resolved_value) else None
        ticket = NormalizedTicket.model_validate(
            {
                "ticket_id": _text(raw.get("ticket_id")),
                "title": mask_text(_text(raw.get("title"))),
                "description": mask_text(_text(raw.get("description"))),
                "status": normalized_status,
                "priority": normalized_priority,
                "requester_email": mask_email(_text(raw.get("requester_email"))),
                "assignee": mask_text(_text(raw.get("assignee"))) or None,
                "created_at": created_at,
                "updated_at": updated_at,
                "resolved_at": resolved_at,
                "source_system": _text(raw.get("source_system")) or rules.source_system,
            }
        )
    except (ValueError, ValidationError) as error:
        violations.append(
            Violation(code="schema_validation", dimension="validity", message=str(error))
        )
        return ProcessedRow(
            row_number=row.row_number,
            ticket=None,
            masked_raw=masked_raw,
            violations=violations,
        )

    if ticket.status in {"Resolved", "Closed"} and ticket.resolved_at is None:
        violations.append(
            Violation(
                code="resolved_timestamp_missing",
                dimension="consistency",
                message="Resolved or Closed ticket must have resolved_at",
            )
        )
    if ticket.status in {"Open", "In Progress", "Pending"} and ticket.resolved_at is not None:
        violations.append(
            Violation(
                code="active_ticket_has_resolution",
                dimension="consistency",
                message="Active ticket cannot have resolved_at",
            )
        )
    if ticket.updated_at < rules.reference_time - timedelta(days=rules.timeliness_days):
        violations.append(
            Violation(
                code="stale_record",
                dimension="timeliness",
                message=f"Record is older than {rules.timeliness_days} days at reference time",
            )
        )
    return ProcessedRow(
        row_number=row.row_number,
        ticket=ticket,
        masked_raw=masked_raw,
        violations=violations,
    )


def quality_scores(row: ProcessedRow, required_field_count: int) -> dict[str, float]:
    dimensions = {violation.dimension for violation in row.violations}
    completeness_penalty = sum(
        1 for violation in row.violations if violation.code == "required_fields_missing"
    )
    return {
        "completeness": max(0.0, 1 - completeness_penalty / max(1, required_field_count)),
        "uniqueness": 0.0 if row.duplicate else 1.0,
        "validity": 0.0 if "validity" in dimensions else 1.0,
        "consistency": 0.0 if "consistency" in dimensions else 1.0,
        "timeliness": 0.0 if "timeliness" in dimensions else 1.0,
    }
