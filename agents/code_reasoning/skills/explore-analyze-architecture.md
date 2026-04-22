---
name: analyze-architecture
description: Analyze project architecture — entry points, layers, dependencies
---

## Architecture Analysis Workflow

1. **Project root scan:**
   - Read: README.md, CLAUDE.md, package.json, pom.xml, pyproject.toml, go.mod
   - Check: src/, app/, lib/, cmd/ directory structures
   - Identify: language, framework, build system

2. **Entry points:**
   - Find main() functions, app factories, server startup
   - Identify HTTP routes, CLI commands, event handlers
   - Map: request → handler → service → repository → database

3. **Layer analysis:**
   - Controllers/Routes (HTTP layer)
   - Services (business logic)
   - Repositories/DAOs (data access)
   - Models/Entities (data structures)
   - Config (application configuration)

4. **Dependency flow:**
   - Follow import chains from entry points
   - Identify shared utilities and cross-cutting concerns
   - Note circular dependencies or unusual patterns

5. **Report:**
   - ASCII diagram of architecture layers
   - Key files per layer with brief descriptions
   - Notable patterns (DI, event-driven, microservices, monolith)
   - Potential concerns (god classes, circular deps, missing layers)

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

