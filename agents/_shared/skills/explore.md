---
name: explore
description: Invoke the Explore agent for read-only codebase investigation
---

## Using Explore Subagent

When you need to search or analyze the codebase before making changes, delegate to the Explore agent:

```
[SUBAGENT:explore] Search for all implementations of the PaymentProcessor interface
```

The Explore agent will:
1. Search the codebase using Glob, Grep, and Read tools
2. Report findings with file paths and line numbers
3. Return results to you for further action

Use explore BEFORE:
- Writing new code (understand existing patterns first)
- Code review (gather evidence)
- Debugging (trace the code path)
- Architecture decisions (understand current structure)

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

