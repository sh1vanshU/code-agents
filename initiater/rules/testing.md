---
dimension: testing
severity: critical
---

# Testing — Coverage & CI

## Purpose
Tests catch regressions before they reach users. Without tests for core modules, changes are risky.

## Rules
- [ ] Test files exist for core modules (config, backend, stream, routers)
- [ ] pytest is configured in pyproject.toml
- [ ] Tests can run with `poetry run pytest`
- [ ] Agent YAML loading is tested (valid YAML, missing fields, env var expansion)
- [ ] API endpoints have integration tests (list agents, chat completions)
- [ ] Streaming responses are tested
- [ ] Session management is tested
- [ ] CI pipeline runs tests on every PR
- [ ] Test coverage is measured and reported

## Verification
```bash
# Check for test files
ls tests/ 2>/dev/null || echo "No tests/ directory"

# Check pytest config
grep -A5 '\[tool.pytest' pyproject.toml

# Run tests
poetry run pytest -v
```

## References
- `tests/`
- `pyproject.toml`
- `code_agents/`

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

