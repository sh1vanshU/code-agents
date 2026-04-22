---
dimension: vision
severity: info
---

# Vision — Project Goals & Scope

## Purpose
A clear vision prevents scope creep and helps contributors prioritize work.

## Rules
- [ ] Project purpose is stated clearly (what problem it solves)
- [ ] Target users are identified
- [ ] Key features are listed
- [ ] Non-goals or out-of-scope items are stated
- [ ] Relationship to upstream tools (Cursor, Claude) is explained
- [ ] Roadmap or future direction exists (even if informal)

## Verification
```bash
# Check for vision/goals in docs
grep -i 'goal\|purpose\|vision\|non-goal\|scope' README.md
```

## References
- `README.md` (What is this?)
- `LICENSE`

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

