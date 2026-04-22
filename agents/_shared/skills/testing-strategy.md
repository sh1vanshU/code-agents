---
name: testing-strategy
description: Design test strategies and test plans. Trigger with "how should we test", "test strategy for", "write tests for", "test plan", "what tests do we need", or when the user needs help with testing approaches, coverage, or test architecture.
---

# Testing Strategy

Design effective testing strategies balancing coverage, speed, and maintenance.

## Testing Pyramid

```
        /  E2E  \         Few, slow, high confidence
       / Integration \     Some, medium speed
      /    Unit Tests  \   Many, fast, focused
```

## Strategy by Component Type

- **API endpoints**: Unit tests for business logic, integration tests for HTTP layer, contract tests for consumers
- **Data pipelines**: Input validation, transformation correctness, idempotency tests
- **Frontend**: Component tests, interaction tests, visual regression, accessibility
- **Infrastructure**: Smoke tests, chaos engineering, load tests

## What to Cover

Focus on: business-critical paths, error handling, edge cases, security boundaries, data integrity.

Skip: trivial getters/setters, framework code, one-off scripts.

## Output

Produce a test plan with: what to test, test type for each area, coverage targets, and example test cases. Identify gaps in existing coverage.

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

