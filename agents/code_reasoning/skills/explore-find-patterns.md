---
name: find-patterns
description: Find code patterns — anti-patterns, conventions, repeated structures
---

## Pattern Detection Workflow

1. **Convention detection:**
   - Naming: camelCase, snake_case, PascalCase
   - File organization: by feature, by type, by layer
   - Import style: absolute, relative, barrel exports

2. **Common patterns to check:**
   - Dependency injection (constructor, setter, field)
   - Error handling (try/catch, Result types, error codes)
   - Logging (structured, unstructured, levels)
   - Configuration (env vars, config files, constants)
   - Testing (unit, integration, e2e, mocking strategy)

3. **Anti-pattern detection:**
   - God classes (files > 500 lines)
   - Deep nesting (> 4 levels)
   - Magic numbers/strings
   - Copy-paste code (similar blocks in multiple files)
   - Missing error handling

4. **Report:**
   - Patterns found with examples
   - Conventions summary
   - Anti-patterns with severity and location
   - Recommendations for improvement

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

