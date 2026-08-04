"""Typed pipeline models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class InputFormat(StrEnum):
    CSV = "csv"
    JSONL = "jsonl"
    PARQUET = "parquet"


class TicketStatus(StrEnum):
    OPEN = "Open"
    IN_PROGRESS = "In Progress"
    PENDING = "Pending"
    RESOLVED = "Resolved"
    CLOSED = "Closed"


class TicketPriority(StrEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class PipelineRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    batch_size: int = Field(default=1000, ge=1, le=50_000)
    source_system: str = Field(min_length=2, max_length=100)
    reference_time: datetime
    timeliness_days: int = Field(default=90, ge=1, le=3650)
    quality_threshold: float = Field(default=0.85, ge=0, le=1)
    required_fields: list[str]
    status_mapping: dict[str, str]
    priority_mapping: dict[str, str]
    allowed_statuses: list[str]
    allowed_priorities: list[str]

    @field_validator("status_mapping", "priority_mapping", mode="after")
    @classmethod
    def normalize_mapping_keys(cls, value: dict[str, str]) -> dict[str, str]:
        return {key.strip().casefold(): mapped.strip() for key, mapped in value.items()}


class NormalizedTicket(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    ticket_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=3, max_length=500)
    description: str = Field(default="", max_length=20_000)
    status: TicketStatus
    priority: TicketPriority
    requester_email: str = Field(min_length=10, max_length=200)
    assignee: str | None = Field(default=None, max_length=200)
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    source_system: str = Field(min_length=2, max_length=100)

    @field_validator("requester_email")
    @classmethod
    def validate_masked_email(cls, value: str) -> str:
        if not value.endswith("@masked.invalid"):
            raise ValueError("requester email must be masked before validation")
        return value

    @model_validator(mode="after")
    def validate_dates(self) -> NormalizedTicket:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        if self.resolved_at is not None and self.resolved_at < self.created_at:
            raise ValueError("resolved_at cannot be earlier than created_at")
        return self


class InputRow(BaseModel):
    row_number: int = Field(ge=1)
    data: dict[str, Any] | None = None
    read_error: str | None = None


class Violation(BaseModel):
    code: str
    dimension: Literal["completeness", "uniqueness", "validity", "consistency", "timeliness"]
    message: str


class ProcessedRow(BaseModel):
    row_number: int
    ticket: NormalizedTicket | None
    masked_raw: dict[str, Any]
    violations: list[Violation]
    duplicate: bool = False

    @property
    def accepted(self) -> bool:
        return (
            self.ticket is not None
            and not any(
                violation.dimension in {"validity", "consistency"} for violation in self.violations
            )
            and not self.duplicate
        )


class QualityAccumulator(BaseModel):
    records: int = 0
    dimension_totals: dict[str, float] = Field(
        default_factory=lambda: {
            "completeness": 0.0,
            "uniqueness": 0.0,
            "validity": 0.0,
            "consistency": 0.0,
            "timeliness": 0.0,
        }
    )

    def add(self, scores: dict[str, float]) -> None:
        self.records += 1
        for dimension, score in scores.items():
            self.dimension_totals[dimension] = self.dimension_totals.get(dimension, 0.0) + score

    def averages(self) -> dict[str, float]:
        if self.records == 0:
            return {dimension: 0.0 for dimension in self.dimension_totals}
        return {
            dimension: round(total / self.records, 6)
            for dimension, total in self.dimension_totals.items()
        }

    def overall(self) -> float:
        values = list(self.averages().values())
        return round(sum(values) / len(values), 6) if values else 0.0


class RunSummary(BaseModel):
    run_id: str
    status: str
    input_path: str
    input_hash: str
    input_format: InputFormat
    config_hash: str
    dry_run: bool
    incremental: bool
    total_records: int
    accepted_records: int
    quarantined_records: int
    duplicate_records: int
    loaded_records: int
    unchanged_records: int
    resumed_from_offset: int
    batches_committed: int
    duration_seconds: float
    records_per_second: float
    quality_dimensions: dict[str, float]
    quality_score: float
    quality_threshold: float
    quality_gate_passed: bool
    report_json: str | None = None
    report_markdown: str | None = None
