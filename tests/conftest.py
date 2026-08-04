from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from support_data_quality.models import PipelineRules


@pytest.fixture
def rules() -> PipelineRules:
    return PipelineRules(
        schema_version=1,
        batch_size=2,
        source_system="test-desk",
        reference_time=datetime(2026, 1, 1, tzinfo=UTC),
        timeliness_days=90,
        quality_threshold=0.80,
        required_fields=[
            "ticket_id",
            "title",
            "status",
            "priority",
            "requester_email",
            "created_at",
            "updated_at",
        ],
        status_mapping={"open": "Open", "done": "Resolved"},
        priority_mapping={"p1": "Critical", "low": "Low"},
        allowed_statuses=["Open", "In Progress", "Pending", "Resolved", "Closed"],
        allowed_priorities=["Low", "Medium", "High", "Critical"],
    )


@pytest.fixture
def valid_row() -> dict[str, str]:
    return {
        "ticket_id": "SD-1",
        "title": "VPN connection timeout",
        "description": "Contact user@example.invalid at +1-202-555-0100",
        "status": "open",
        "priority": "p1",
        "requester_email": "user@example.invalid",
        "assignee": "engineer-1",
        "created_at": "2025-12-31T10:00:00Z",
        "updated_at": "2025-12-31T10:05:00Z",
        "resolved_at": "",
        "source_system": "test-desk",
    }


@pytest.fixture
def database_url_value() -> str:
    value = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not value:
        pytest.skip("PostgreSQL integration URL is not configured")
    return value
