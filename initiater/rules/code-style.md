---
dimension: code-style
severity: info
---

# Code Style — Formatting & Conventions

## Purpose
Consistent code style reduces cognitive load and merge conflicts across contributors.

## Rules
- [ ] Consistent formatting tool configured (black, ruff, or similar)
- [ ] Linter configured (ruff, flake8, or similar)
- [ ] Type hints on public API functions
- [ ] No unused imports in committed code
- [ ] Consistent naming conventions (snake_case for Python, kebab-case for agent names)
- [ ] pyproject.toml has formatter/linter config sections
- [ ] Import ordering is consistent (stdlib, third-party, local)

## Verification
```bash
# Check for formatter config
grep -A3 '\[tool.black\]\|\[tool.ruff\]' pyproject.toml

# Check for unused imports
poetry run ruff check --select F401 code_agents/ 2>/dev/null || echo "ruff not configured"

# Check type hints on public functions
grep -n 'def [a-z].*):$' code_agents/*.py  # missing return type hints
```

## References
- `pyproject.toml`
- `code_agents/*.py`

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

