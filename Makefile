.DEFAULT_GOAL := help
.PHONY: help setup lint typecheck test test-unit build up down clean demo run benchmark

help:
	@echo "setup lint typecheck test test-unit build up down clean demo run benchmark"

setup:
	@test -f .env || cp .env.example .env
	uv sync --all-groups --frozen

lint:
	uv run ruff format --check src tests
	uv run ruff check src tests

typecheck:
	uv run mypy src

test-unit:
	uv run pytest -m "not integration"

test:
	uv run pytest --cov=support_data_quality --cov-report=term-missing

build:
	uv build
	docker build --target runtime -t support-data-quality-pipeline:local .

up:
	docker compose up -d database
	docker compose --profile tools run --rm pipeline migrate

down:
	docker compose --profile tools down

demo:
	docker compose --profile tools run --rm pipeline generate-demo data/demo.jsonl --format jsonl --records 10000

run:
	docker compose --profile tools run --rm pipeline run data/demo.jsonl --incremental

benchmark:
	./scripts/benchmark.sh 100000

clean:
	docker compose --profile tools down --volumes --remove-orphans
	rm -rf .venv .pytest_cache .mypy_cache .ruff_cache dist build htmlcov
	find artifacts data -type f ! -name '.gitkeep' -delete
