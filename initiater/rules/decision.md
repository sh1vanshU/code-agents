---
dimension: decision
severity: info
---

# Decision — Architecture Decision Records

## Purpose
Key architectural choices should be documented so future contributors understand *why* things are built the way they are, not just *how*.

## Rules
- [ ] Backend abstraction choice is documented (why cursor + claude, not just one)
- [ ] YAML config approach is explained (why YAML, not code-based agents)
- [ ] OpenAI compatibility choice is documented (why mimic OpenAI API)
- [ ] Session management approach is explained
- [ ] Permission model design rationale exists
- [ ] Streaming implementation choice is documented (SSE, reasoning_content)

## Verification
```bash
# Check for ADR directory or inline decisions
test -d docs/adr && echo "ADR directory exists"
grep -l 'design\|architecture\|decision' README.md Agents.md
```

## References
- `README.md` (What is this?, Using the Claude Backend)
- `Agents.md` (Permission Modes, Agent Resolution)
- `code_agents/backend.py`
- `code_agents/stream.py`

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

