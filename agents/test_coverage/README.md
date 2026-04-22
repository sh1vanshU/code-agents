# Test Coverage Agent

> Run test suites, generate coverage reports, find gaps

## Identity

| Field | Value |
|-------|-------|
| **Name** | `test-coverage` |
| **YAML** | `test_coverage.yaml` |
| **Backend** | `${CODE_AGENTS_BACKEND:cursor}` |
| **Model** | `${CODE_AGENTS_MODEL:Composer 2 Fast}` |
| **Permission** | `acceptEdits` — auto-approve file edits |

## Capabilities

- Run the test suite (auto-detects pytest, jest, maven, gradle, go)
- Generate and parse coverage reports
- Identify new code without test coverage (comparing against a base branch)
- Report coverage percentage and uncovered lines
- Block pipeline progression if coverage is below threshold

## Important Rules

- Always runs tests before reporting coverage
- Reports BOTH overall coverage and incremental (new code) coverage
- Lists specific files and line numbers that lack tests
- If tests fail, shows the failure output and does NOT proceed to coverage analysis
- Coverage threshold default is 100% — configurable per request

## Tools & Endpoints

- `POST /testing/run` — run tests: `{"branch": "feature-branch", "test_command": null, "coverage_threshold": 100}`
- `GET /testing/coverage` — get latest coverage report
- `GET /testing/gaps?base=main&head=feature-branch` — uncovered new lines

## Skills

### Own Skills

| Skill | Description |
|-------|-------------|
| `run-coverage` | Run tests with coverage, report percentages by file |
| `find-gaps` | Identify files and functions below coverage threshold |
| `coverage-diff` | Compare coverage before and after changes |
| `coverage-plan` | Plan to reach target coverage (analyze, prioritize, estimate effort) |
| `write-unit-tests` | Write JUnit 5 unit tests (Mockito, AssertJ, edge cases) |
| `write-integration-tests` | Write Spring integration tests (Testcontainers, MockMvc) |
| `write-e2e-tests` | Write end-to-end tests (full request flow, WireMock, side effects) |
| `jacoco-report` | Parse and report JaCoCo XML coverage with per-class metrics |
| `coverage-gate` | Pipeline quality gate (PASS/FAIL on coverage threshold) |

### Shared Engineering Skills

Shared skills from `agents/_shared/skills/` are also available to this agent: architecture, code-review, debug, deploy-checklist, documentation, incident-response, standup, system-design, tech-debt, testing-strategy.

## Usage

### Chat REPL
```bash
code-agents chat test-coverage
```

### Inline Delegation (from another agent)
```
/test-coverage <your prompt>
```

### Skill Invocation
```
/test-coverage:run-coverage
/test-coverage:find-gaps
/test-coverage:coverage-diff
/test-coverage:coverage-plan
/test-coverage:write-unit-tests
/test-coverage:write-integration-tests
/test-coverage:write-e2e-tests
/test-coverage:jacoco-report
/test-coverage:coverage-gate
```

### API
```bash
curl -X POST http://localhost:8000/v1/agents/test-coverage/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "your prompt"}], "stream": true}'
```

## Example Prompts

1. "Run tests and show coverage report"
2. "Which files have less than 80% coverage?"
3. "Show uncovered lines in the auth module"
4. "Create a coverage plan to reach 80% — prioritize payment classes"
5. "Write unit tests for RefundService with edge cases"
6. "Write integration tests for OrderController with real PostgreSQL"
7. "Write E2E tests for the full order-to-payment flow"
8. "Parse the JaCoCo report and show per-package coverage"
9. "Run coverage gate at 80% threshold — can we deploy?"

## Autorun Config

This agent has an `autorun.yaml` that defines allowed and blocked commands for auto-execution.

## Rules

Custom rules to guide this agent's behavior:

| Scope | Path |
|-------|------|
| Global | `~/.code-agents/rules/test-coverage.md` |
| Project | `.code-agents/rules/test-coverage.md` |

See `code-agents rules create --agent test-coverage` to create rules.

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

