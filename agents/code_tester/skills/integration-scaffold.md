---
name: integration-scaffold
description: Integration scaffold — generate docker-compose and test fixtures for integration testing
tags: [testing, integration, docker, fixtures]
---

# Integration Test Scaffold

## Workflow

1. **Identify services** — Determine external dependencies: databases, caches, queues, APIs.
2. **Generate docker-compose** — Create a `docker-compose.test.yml` with required service containers and health checks.
3. **Create fixtures** — Build setup/teardown helpers: seed data, create tables, configure queues.
4. **Write test template** — Produce a base integration test class with container lifecycle management.
5. **Add CI config** — Suggest pipeline steps to spin up containers, run tests, and tear down.
6. **Output** — Return all generated files with usage instructions.

## Notes

- Use official images with pinned versions (e.g., `postgres:16-alpine`, `redis:7-alpine`).
- Include wait-for-ready logic to avoid test flakiness from slow container startup.
- Keep test data minimal and deterministic for fast, reproducible runs.
