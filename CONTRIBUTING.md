# Contributing

Use Python 3.12, `uv`, and Conventional Commits. Create a focused branch, add tests for behavior changes, and run:

```bash
make lint
make typecheck
make test
```

Never commit `.env`, production exports, quarantine data, database state, or generated reports containing sensitive data. Pull requests should explain the data-quality rule affected, migration impact, and resume/idempotency considerations.
