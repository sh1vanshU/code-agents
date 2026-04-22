---
name: search-codebase
description: Systematic codebase search — find files, patterns, and usages
---

## Search Codebase Workflow

1. **Understand the query** — what is the user looking for? A class, function, pattern, file, or concept?

2. **Broad search first:**
   - Use Glob to find files matching a pattern: `**/*.java`, `**/Payment*.py`
   - Use Grep to search content: `class PaymentService`, `def authenticate`
   - Check project root for README, CLAUDE.md, package.json, pom.xml for structure clues

3. **Narrow down:**
   - Read the most relevant files found in step 2
   - Follow imports/references to trace dependencies
   - Check test files for usage examples

4. **Report findings:**
   - List matching files with line numbers
   - Show key code snippets (not full files)
   - Explain relationships between found items
   - Suggest next steps for the user

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

