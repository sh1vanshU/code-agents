---
dimension: security
severity: critical
---

# Security — Secrets, Auth & OWASP

## Purpose
A server exposing API endpoints must handle secrets safely, validate inputs, and follow security best practices.

## Rules
- [ ] No hardcoded API keys or secrets in source code
- [ ] .gitignore excludes .env, credentials, and key files
- [ ] API keys use environment variable injection (`${VAR}` syntax)
- [ ] permission_mode is set appropriately per agent (not all bypassPermissions)
- [ ] Input validation on chat completion requests (message format, types)
- [ ] No path traversal via agent name or cwd parameter
- [ ] CORS is configured (not wildcard in production)
- [ ] TLS verification is on by default (opt-out only for dev)
- [ ] Dependencies are pinned and free of known vulnerabilities
- [ ] OAuth tokens are stored securely (not in plain text logs)

## Verification
```bash
# Search for hardcoded keys
grep -rn 'sk-ant-\|sk-proj-\|api_key.*=.*["\x27][A-Za-z0-9]' code_agents/ agents/

# Check .gitignore
cat .gitignore | grep -E '\.env|secret|key'

# Check CORS config
grep -n 'CORS\|allow_origins' code_agents/app.py
```

## References
- `code_agents/app.py` (CORS)
- `code_agents/config.py` (env var handling)
- `agents/*.yaml` (permission_mode, api_key)
- `.gitignore`

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

