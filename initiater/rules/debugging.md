---
dimension: debugging
severity: warning
---

# Debugging — Diagnostics & Error Handling

## Purpose
When things break, clear diagnostics and error messages save hours of guessing.

## Rules
- [ ] /diagnostics endpoint exists and covers all backends
- [ ] /diagnostics shows package version, backend paths, agent list
- [ ] /health endpoint returns meaningful status
- [ ] scripts/verify-server.sh works and tests key endpoints
- [ ] Error responses include actionable messages (not just status codes)
- [ ] Backend failures (cursor-agent exit codes) are translated to clear errors
- [ ] Streaming errors are surfaced in the SSE payload

## Verification
```bash
# Check diagnostics endpoint
curl -s http://localhost:8000/diagnostics 2>/dev/null | python3 -m json.tool

# Run verify script
bash scripts/verify-server.sh 2>/dev/null
```

## References
- `code_agents/app.py` (diagnostics, health)
- `scripts/verify-server.sh`
- `code_agents/backend.py` (error handling)

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

