# syntax=docker/dockerfile:1.7
FROM python:3.12.13-slim-bookworm AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app
RUN pip install --no-cache-dir uv==0.11.7
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.12.13-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN groupadd --gid 10001 pipeline \
    && useradd --uid 10001 --gid pipeline --no-create-home --shell /usr/sbin/nologin pipeline
WORKDIR /app
COPY --from=builder --chown=pipeline:pipeline /app/.venv /app/.venv
COPY --chown=pipeline:pipeline src ./src
COPY --chown=pipeline:pipeline migrations ./migrations
COPY --chown=pipeline:pipeline config ./config
RUN mkdir -p /app/data /app/artifacts && chown -R pipeline:pipeline /app/data /app/artifacts

USER 10001:10001
ENTRYPOINT ["support-data-quality"]
CMD ["--help"]
