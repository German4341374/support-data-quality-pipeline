from __future__ import annotations

from pathlib import Path

import pytest

from support_data_quality.config import database_url, load_rules, rules_hash


def test_loads_example_configuration() -> None:
    path = Path(__file__).parents[1] / "config" / "rules.example.yaml"
    rules = load_rules(path)
    assert rules.batch_size == 1000
    assert len(rules_hash(rules)) == 64


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        database_url()


def test_database_url_requires_postgresql(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///tmp.db")
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        database_url()
