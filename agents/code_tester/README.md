# Code Tester Agent

> Principal Test Engineer — owns test writing, debugging, test infrastructure, and test quality

## Identity

| Field | Value |
|-------|-------|
| **Name** | `code-tester` |
| **Role** | Principal Test Engineer |
| **YAML** | `code_tester.yaml` |
| **Backend** | `${CODE_AGENTS_BACKEND:cursor}` |
| **Model** | `${CODE_AGENTS_MODEL:Composer 2 Fast}` |
| **Permission** | `acceptEdits` — auto-approve file edits |

## Capabilities

- Write unit tests, integration tests, and test fixtures
- Debug failing tests — trace root cause, not symptoms
- Add edge case coverage (null, empty, boundary, timeout, error paths)
- Refactor and optimize test suites
- Run tests, parse results, generate structured reports with failure summaries
- Smart failure classification: fix code bugs automatically, STOP for non-code issues (infra, flaky, environment)
- Set up test infrastructure (Testcontainers, WireMock, shared fixtures, test profiles)
- Detect and fix flaky tests — classify root cause, fix or quarantine
- Audit test quality across 6 dimensions, score A/B/C/D
- Debug test failures systematically with regression test coverage
- Create test data factories and builders for reusable, valid test data

## Boundaries

This agent will **not**:

- Implement features (delegate to `code-writer`)
- Review code for security (delegate to `code-reviewer`)
- Run CI/CD pipelines (delegate to `jenkins-cicd`)
- Make architectural decisions — only tests what exists

## Tools & Endpoints

Uses the LLM directly — no API endpoints. This agent works entirely through code reading, test writing, and test execution.

## Skills

### Own Skills

| Skill | Description |
|-------|-------------|
| `unit-test` | Write unit tests for a class or function with mocks and edge cases |
| `debug` | Debug a failing test — trace the root cause and fix it |
| `integration-test` | Write integration tests with real dependencies |
| `test-and-report` | Run tests, parse results, get coverage, generate structured report with failure summary |
| `test-fix-loop` | Run tests, classify failures, fix code bugs via code-writer, STOP for non-code issues (max 5 cycles) |
| `test-infrastructure` | Set up test infrastructure: Testcontainers, WireMock, shared fixtures, test profiles |
| `flaky-test-hunter` | Detect and fix flaky tests: run multiple times, classify root cause, fix or quarantine |
| `test-quality-audit` | Audit existing tests: assertion quality, naming, isolation, mock usage, speed, coverage. Score A/B/C/D |
| `debug-failure` | Debug test failures systematically: reproduce, isolate, trace root cause, fix, add regression test |
| `test-data-factory` | Create test data factories/builders: Builder pattern, randomized valid data, fixture management |

### Shared Engineering Skills

Shared skills from `agents/_shared/skills/` are also available to this agent: architecture, code-review, debug, deploy-checklist, documentation, incident-response, standup, system-design, tech-debt, testing-strategy.

## Usage

### Chat REPL
```bash
code-agents chat code-tester
```

### Inline Delegation (from another agent)
```
/code-tester <your prompt>
```

### Skill Invocation
```
/code-tester:unit-test <your prompt>
/code-tester:debug <your prompt>
/code-tester:test-and-report <your prompt>
/code-tester:test-fix-loop <your prompt>
/code-tester:test-infrastructure <your prompt>
/code-tester:flaky-test-hunter <your prompt>
/code-tester:test-quality-audit <your prompt>
/code-tester:debug-failure <your prompt>
/code-tester:test-data-factory <your prompt>
```

### API
```bash
curl -X POST http://localhost:8000/v1/agents/code-tester/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "your prompt"}], "stream": true}'
```

## Example Prompts

1. "Write unit tests for the PaymentService class"
2. "Debug why test_auth_flow is failing"
3. "Add edge case tests for the retry logic"
4. "Run all tests and give me a structured report"
5. "Run tests, fix any failures, and repeat until green"

## Autorun Config

This agent has an `autorun.yaml` that defines allowed and blocked commands for auto-execution.

## Rules

Custom rules to guide this agent's behavior:

| Scope | Path |
|-------|------|
| Global | `~/.code-agents/rules/code-tester.md` |
| Project | `.code-agents/rules/code-tester.md` |

See `code-agents rules create --agent code-tester` to create rules.

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

