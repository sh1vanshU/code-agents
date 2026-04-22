# Code Reviewer Agent

> Review code for bugs, security issues, performance problems

## Identity

| Field | Value |
|-------|-------|
| **Name** | `code-reviewer` |
| **YAML** | `code_reviewer.yaml` |
| **Backend** | `${CODE_AGENTS_BACKEND:cursor}` |
| **Model** | `${CODE_AGENTS_MODEL:Composer 2 Fast}` |
| **Permission** | `default` — ask before each action |

## Capabilities

- Identify bugs, logic errors, and edge cases
- Find security vulnerabilities (OWASP Top 10: injection, XSS, auth bypass)
- Spot performance issues (N+1 queries, unbounded loops, memory leaks)
- Flag error handling gaps and race conditions
- Review test quality and coverage gaps
- Review LLD documents before coding begins — flag risks and missing edge cases

## Boundaries

This agent will **not**:

- Modify any files (it reviews, it does not rewrite)
- Write tests (delegate to `code-tester`)
- Run builds or deployments (delegate to `jenkins-cicd`)
- Nitpick style when the project has no style guide

## Tools & Endpoints

Uses the LLM directly — no API endpoints. This agent works entirely through code reading and analysis.

## Skills

### Own Skills

| Skill | Description |
|-------|-------------|
| `security-review` | Review code for OWASP top 10, auth issues, injection vulnerabilities |
| `bug-hunt` | Identify logic bugs, edge cases, race conditions, null safety issues |
| `pr-review` | Full pull request review — diff analysis, test coverage, style check |
| `design-review` | Review LLD before coding — flag risks, missing edge cases, suggest alternatives (APPROVED or NEEDS-CHANGES) |

### Shared Engineering Skills

Shared skills from `agents/_shared/skills/` are also available to this agent: architecture, code-review, debug, deploy-checklist, documentation, incident-response, standup, system-design, tech-debt, testing-strategy.

## Usage

### Chat REPL
```bash
code-agents chat code-reviewer
```

### Inline Delegation (from another agent)
```
/code-reviewer <your prompt>
```

### Skill Invocation
```
/code-reviewer:security-review <your prompt>
/code-reviewer:pr-review <your prompt>
/code-reviewer:design-review <your prompt>
/code-reviewer:bug-hunt <your prompt>
```

### API
```bash
curl -X POST http://localhost:8000/v1/agents/code-reviewer/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "your prompt"}], "stream": true}'
```

## Example Prompts

1. "Review the auth module for security issues"
2. "Check the new payment endpoint for bugs"
3. "Review the last 3 commits for quality"
4. "Review this LLD before I start coding — flag any risks"

## Autorun Config

This agent has an `autorun.yaml` that defines allowed and blocked commands for auto-execution.

## Rules

Custom rules to guide this agent's behavior:

| Scope | Path |
|-------|------|
| Global | `~/.code-agents/rules/code-reviewer.md` |
| Project | `.code-agents/rules/code-reviewer.md` |

See `code-agents rules create --agent code-reviewer` to create rules.

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

