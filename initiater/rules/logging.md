---
dimension: logging
severity: warning
---

# Logging — Observability & Diagnostics

## Purpose
Good logging helps debug production issues without reproducing them locally. Bad logging leaks secrets or drowns signal in noise.

## Rules
- [ ] Python logging module used (not bare print statements for operational output)
- [ ] Log levels used appropriately (DEBUG for verbose, INFO for operations, WARNING/ERROR for problems)
- [ ] No API keys, tokens, or secrets in log output
- [ ] Request/response logging available at DEBUG level
- [ ] Structured logging format (or easily parseable)
- [ ] Agent name included in log messages for multi-agent debugging

## Verification
```bash
# Check for print vs logging usage
grep -rn 'print(' code_agents/ | grep -v '__pycache__'
grep -rn 'logging\.\|logger\.' code_agents/ | head -20

# Check for secrets in log statements
grep -rn 'log.*api_key\|log.*secret\|log.*token' code_agents/
```

## References
- `code_agents/*.py`
- `code_agents/routers/*.py`

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

