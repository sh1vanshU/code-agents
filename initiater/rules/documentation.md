---
dimension: documentation
severity: critical
---

# Documentation — Sync & Completeness

## Purpose
Users discover agents and features through README.md, Agents.md, and the router. If these diverge, users get confused or miss capabilities.

## Rules
- [ ] README.md "Included Agents" table lists all active agents
- [ ] Agents.md has a section for every active agent
- [ ] auto-pilot.yaml system prompt lists all specialist agents
- [ ] API endpoint documentation matches actual routes in code
- [ ] Environment variable table in README covers all vars used in code
- [ ] YAML configuration reference documents all supported fields
- [ ] Troubleshooting section is current (no references to removed features)
- [ ] Quick Start instructions work on a fresh clone

## Verification
```bash
# Compare agent YAMLs vs README mentions
diff <(ls agents/*.yaml | xargs -I{} basename {} .yaml | sort) \
     <(grep -oP '`[a-z_]+`' README.md | tr -d '`' | sort -u)

# Check all env vars in code are documented
grep -rhoP '\bos\.environ\[.([A-Z_]+).\]' code_agents/ | sort -u
grep -oP '[A-Z_]{3,}' README.md | sort -u
```

## References
- `README.md`
- `Agents.md`
- `agents/auto_pilot/auto_pilot.yaml` (orchestrator with specialist list)
- `code_agents/config.py`

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

