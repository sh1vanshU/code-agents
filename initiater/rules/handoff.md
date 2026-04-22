---
dimension: handoff
severity: info
---

# Handoff — Onboarding & Context Transfer

## Purpose
New contributors or operators should be able to get productive quickly. Session and context management should be clear.

## Rules
- [ ] Onboarding steps are documented (clone, install, configure, run)
- [ ] Quick Start section covers the happy path end-to-end
- [ ] Session management is explained with examples
- [ ] Multi-turn conversation flow is documented
- [ ] Agent selection guidance exists (router or direct)
- [ ] Common first-time issues are in Troubleshooting

## Verification
```bash
# Check Quick Start completeness
grep -c '```' README.md  # code blocks in README

# Check session docs
grep -i 'session' README.md Agents.md
```

## References
- `README.md` (Quick Start, Session Management, Troubleshooting)
- `Agents.md` (Multi-Turn Sessions, Typical Workflow)

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

