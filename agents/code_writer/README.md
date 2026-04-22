# Code Writer Agent

> Principal Software Engineer who implements production-grade code across all layers

## Identity

| Field | Value |
|-------|-------|
| **Name** | `code-writer` |
| **YAML** | `code_writer.yaml` |
| **Backend** | `${CODE_AGENTS_BACKEND:cursor}` |
| **Model** | `${CODE_AGENTS_MODEL:Composer 2 Fast}` |
| **Permission** | `acceptEdits` — auto-approve file edits |

## Capabilities

- Implement new features from requirements or descriptions
- Fix bugs with minimal, targeted changes
- Refactor code for clarity, performance, or maintainability
- Generate complete vertical slices from specs (Jira, OpenAPI, LLD)
- Apply refactoring patterns: extract, rename, move, introduce interface, design patterns
- Upgrade Java versions with deprecated API replacement and new feature enablement
- Upgrade Spring Boot versions following migration guides step by step
- Upgrade library dependencies with CVE scanning and breaking change fixes
- Optimize performance: N+1 queries, caching, lazy loading, async, pagination, indexes
- Create new files, modules, and functions
- Write code and run tests in a loop until green (max 5 cycles)
- Read Jira tickets and implement code end-to-end from ticket to working code
- Detect build tool, run local builds, parse errors, fix and rebuild (max 3 cycles)

## Boundaries

This agent will **not**:

- Run tests beyond verifying its own changes (delegate to `code-tester` or `test-coverage`)
- Review code for bugs/security (delegate to `code-reviewer`)
- Execute CI/CD builds or deployments (delegate to `jenkins-cicd`)
- Perform git operations beyond what's needed for the change
- Make changes unrelated to the user's request

## Tools & Endpoints

Uses the LLM directly — no API endpoints. This agent works entirely through code reading and file editing. After writing code, runs tests. Custom build command: `$CODE_AGENTS_BUILD_CMD`.

## Skills

### Own Skills

| Skill | Description |
|-------|-------------|
| `implement` | Implement a feature from requirements — create files, write code, add tests |
| `refactor` | Refactor code for clarity, DRY, SOLID principles |
| `fix-bug` | Fix a reported bug — locate, understand, fix, verify |
| `write-and-test` | Write code, run tests, fix failures, repeat until green (max 5 cycles) |
| `write-from-jira` | Read Jira ticket, implement code, write tests, verify — end-to-end from ticket to working code |
| `local-build` | Detect build tool, run build, parse errors, fix and rebuild (max 3 cycles) |
| `generate-from-spec` | Full code generation from specification (Jira, OpenAPI, LLD) to complete vertical slice |
| `refactoring` | Code refactoring patterns — extract, rename, move, introduce interface, apply design patterns |
| `java-upgrade` | Java version upgrade — deprecated API replacement, new feature enablement, build config updates |
| `spring-upgrade` | Spring Boot upgrade — migration guide, config changes, deprecated API replacement, dependency alignment |
| `dependency-upgrade` | Library dependency upgrades — scan outdated deps, check CVEs, upgrade with breaking change fixes |
| `performance-optimize` | Performance optimization — N+1 queries, caching, lazy loading, async, pagination, indexes |

### Shared Engineering Skills

Shared skills from `agents/_shared/skills/` are also available to this agent: architecture, code-review, debug, deploy-checklist, documentation, incident-response, standup, system-design, tech-debt, testing-strategy.

## Usage

### Chat REPL
```bash
code-agents chat code-writer
```

### Inline Delegation (from another agent)
```
/code-writer <your prompt>
```

### Skill Invocation
```
/code-writer:implement <your prompt>
/code-writer:fix-bug <your prompt>
/code-writer:write-and-test <your prompt>
/code-writer:write-from-jira TEAM-1234
/code-writer:local-build
/code-writer:generate-from-spec Implement the API from openapi.yaml
/code-writer:refactoring Extract PaymentService into smaller classes
/code-writer:java-upgrade Upgrade from Java 17 to 21
/code-writer:spring-upgrade Upgrade Spring Boot from 3.0 to 3.5
/code-writer:dependency-upgrade Scan and upgrade all outdated dependencies
/code-writer:performance-optimize Fix N+1 queries in OrderService
```

### API
```bash
curl -X POST http://localhost:8000/v1/agents/code-writer/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "your prompt"}], "stream": true}'
```

## Example Prompts

1. "Add input validation to the login function"
2. "Refactor the UserService to use dependency injection"
3. "Create a retry mechanism for failed API calls"
4. "Pick up TEAM-1234 and implement it with tests"
5. "Write the feature and keep running tests until they all pass"
6. "Generate the full vertical slice from openapi.yaml for the /payments endpoint"
7. "Extract the God class OrderProcessor into focused service classes"
8. "Upgrade our project from Java 17 to Java 21"
9. "Upgrade Spring Boot from 3.0 to 3.5 following migration guides"
10. "Scan all dependencies for CVEs and upgrade them"
11. "Find and fix N+1 queries in the order listing endpoint"

## Autorun Config

This agent has an `autorun.yaml` that defines allowed and blocked commands for auto-execution.

## Rules

Custom rules to guide this agent's behavior:

| Scope | Path |
|-------|------|
| Global | `~/.code-agents/rules/code-writer.md` |
| Project | `.code-agents/rules/code-writer.md` |

See `code-agents rules create --agent code-writer` to create rules.

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

