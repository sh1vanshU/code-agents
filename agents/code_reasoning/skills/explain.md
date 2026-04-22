---
name: explain
description: Explain architecture, design patterns, and data flows in the codebase
---

## Workflow

1. **Identify the scope.** Determine what the user wants explained: a single file, a module, a service, or the entire system architecture.

2. **Read the project context files first.** Check for `CLAUDE.md`, `README.md`, or `docs/` in the repo root to understand the overall architecture and tech stack.

3. **Read the relevant source files.** Navigate to the code under analysis. Read the main entry points, then follow imports and dependencies to understand the structure.

4. **Identify the architecture pattern.** Name it explicitly: MVC, microservices, event-driven, layered, hexagonal, etc. Explain how the codebase implements this pattern.

5. **Map the key components.** For each major component:
   - Its responsibility (one sentence)
   - What it depends on (imports, calls)
   - What depends on it (callers, consumers)
   - Key data structures it uses

6. **Explain data flows.** Trace how data enters the system, transforms through layers, and exits. Use numbered steps:
   ```
   1. Request arrives at FastAPI route (routers/completions.py:45)
   2. Route calls build_prompt() which packs conversation history
   3. Prompt sent to backend via run_agent() (backend.py:12)
   4. Response streamed back via SSE (stream.py:88)
   ```

7. **Identify design patterns in use.** Name specific patterns: factory, strategy, observer, middleware chain, dependency injection, etc. Reference the exact files and lines.

8. **Summarize with a high-level diagram** using text-based notation (ASCII art or markdown lists showing relationships between components).
