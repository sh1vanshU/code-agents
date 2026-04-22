# QA Regression Agent

> Run regression suites, write missing tests, API testing, negative testing

## Identity

| Field | Value |
|-------|-------|
| **Name** | `qa-regression` |
| **YAML** | `qa_regression.yaml` |
| **Backend** | `${CODE_AGENTS_BACKEND:cursor}` |
| **Model** | `${CODE_AGENTS_MODEL:Composer 2 Fast}` |
| **Permission** | `acceptEdits` — auto-approve file edits |

## Capabilities

- Run the full regression test suite and report pass/fail/coverage
- Write missing test cases by analyzing untested code paths
- Create test plans for critical flows
- Mock all external dependencies (APIs, databases, queues)
- Identify coverage gaps and edge cases
- Test API endpoints with curls — define test cases, execute, validate, generate pass/fail report
- Test error cases with negative testing: invalid input, missing auth, wrong method, boundary values

## Boundaries

This agent will **not**:

- Implement features (it writes TESTS, not feature code)
- Skip mocking external dependencies — real API calls in tests are forbidden
- Lower coverage thresholds without explicit user approval
- Delete existing tests unless they are provably wrong
- Deploy code (delegate to `jenkins-cicd`)
- Approve a release without running the full regression suite

## Tools & Endpoints

- `POST /testing/run` — run tests: `{"branch": "release", "test_command": null, "coverage_threshold": 80}`
- `GET /testing/coverage` — get coverage report
- `GET /testing/gaps?base=main&head=release` — uncovered new lines

## Skills

### Own Skills

| Skill | Description |
|-------|-------------|
| `full-regression` | Run full test suite, report pass/fail/skip, identify flaky tests |
| `write-missing` | Analyze codebase for untested code, write missing tests |
| `test-plan` | Create a test plan for a feature with test cases and scenarios |
| `api-testing` | Test API endpoints with curls — define test cases, execute, validate responses, generate pass/fail report |
| `negative-testing` | Test error cases — invalid input, missing auth, wrong method, empty body, boundary values — verify proper 4xx responses |
| `regression-suite` | Run full regression suite, compare with baseline, identify NEW failures vs pre-existing |
| `targeted-regression` | Run regression only on areas affected by code changes — faster than full suite |
| `performance-regression` | Detect performance regressions — compare endpoint response times against baseline |
| `contract-validation` | Validate API contracts — detect breaking changes in request/response schemas |
| `regression-orchestrator` | Full regression orchestration — functional, API, performance, contract, logs, Jira update, verdict |
| `baseline-manager` | Save, compare, and reset regression baselines (test results, performance, contracts) |

### Shared Engineering Skills

Shared skills from `agents/_shared/skills/` are also available to this agent: architecture, code-review, debug, deploy-checklist, documentation, incident-response, standup, system-design, tech-debt, testing-strategy.

## Usage

### Chat REPL
```bash
code-agents chat qa-regression
```

### Inline Delegation (from another agent)
```
/qa-regression <your prompt>
```

### Skill Invocation
```
/qa-regression:full-regression
/qa-regression:write-missing <your prompt>
/qa-regression:test-plan <your prompt>
/qa-regression:api-testing <your prompt>
/qa-regression:negative-testing <your prompt>
```

### API
```bash
curl -X POST http://localhost:8000/v1/agents/qa-regression/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "your prompt"}], "stream": true}'
```

## Example Prompts

1. "Run the full regression suite and report what's failing"
2. "Write tests for all untested code in src/services/"
3. "What's the current test coverage? Where are the gaps?"
4. "Create integration tests for the payment API endpoints"
5. "Test all API endpoints and give me a pass/fail report"
6. "Run negative tests on the auth endpoints — invalid tokens, expired sessions"

## Autorun Config

This agent has an `autorun.yaml` that defines allowed and blocked commands for auto-execution.

## Rules

Custom rules to guide this agent's behavior:

| Scope | Path |
|-------|------|
| Global | `~/.code-agents/rules/qa-regression.md` |
| Project | `.code-agents/rules/qa-regression.md` |

See `code-agents rules create --agent qa-regression` to create rules.

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

