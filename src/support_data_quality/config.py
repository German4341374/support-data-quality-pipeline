"""Configuration loading and hashing."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import yaml
from pydantic import TypeAdapter

from support_data_quality.models import PipelineRules


def load_rules(path: Path) -> PipelineRules:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return TypeAdapter(PipelineRules).validate_python(data)


def rules_hash(rules: PipelineRules) -> str:
    canonical = json.dumps(rules.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def database_url() -> str:
    value = os.getenv("DATABASE_URL")
    if not value or not value.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("DATABASE_URL must be a PostgreSQL connection URL")
    return value
