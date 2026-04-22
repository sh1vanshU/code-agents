---
dimension: environment
severity: warning
---

# Environment — Config & Secrets Management

## Purpose
Proper environment handling ensures the project works on first setup and secrets are never committed.

## Rules
- [ ] .env.example exists and documents all required environment variables
- [ ] .env.example has placeholder values (not real keys)
- [ ] All ${VAR} references in agent YAMLs have corresponding .env.example entries
- [ ] Default values are documented for optional variables
- [ ] Environment variable expansion works in system_prompt fields
- [ ] Server fails gracefully when required vars are missing (clear error message)
- [ ] .env is in .gitignore

## Verification
```bash
# Check .env.example exists
test -f .env.example && echo "exists" || echo "MISSING"

# Find all ${VAR} references in agent YAMLs
grep -hoP '\$\{[A-Z_]+\}' agents/*.yaml | sort -u

# Compare with .env.example
grep -oP '^[A-Z_]+' .env.example 2>/dev/null | sort -u
```

## References
- `.env.example`
- `.gitignore`
- `agents/*.yaml`
- `code_agents/config.py`

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

