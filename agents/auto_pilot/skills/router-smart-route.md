---
name: smart-route
description: Analyze user intent, match to best agent, consider task type, required tools, and agent capabilities. Explain why.
---

## Overview

Deeply analyze the user's request to route them to the optimal specialist agent. Go beyond keyword matching — understand the task's requirements and match them to agent capabilities.

## Workflow

### Step 1 — Classify the Request

Determine the primary task category:

| Category | Signals |
|----------|---------|
| **Code understanding** | "how does", "explain", "trace", "where is", "architecture" |
| **Code writing** | "implement", "add feature", "fix bug", "refactor", "create" |
| **Code review** | "review", "check quality", "security audit", "find issues" |
| **Testing** | "write tests", "debug test", "why is this failing" |
| **Test execution** | "run tests", "coverage report", "regression" |
| **Git operations** | "branch", "diff", "commit history", "merge" |
| **CI/CD build** | "build", "Jenkins", "compile", "artifact" |
| **Deployment** | "deploy", "release", "push to prod/dev" |
| **Verification** | "pods", "ArgoCD", "health check", "is it running" |
| **Database/SQL** | "query", "SQL", "Redash", "data", "schema" |
| **Jira/Project** | "ticket", "Jira", "Confluence", "sprint", "story" |
| **Logs** | "Kibana", "logs", "errors in prod", "log search" |
| **Full workflow** | "end to end", "full pipeline", "from start to finish" |
| **Incident** | "down", "broken", "errors spiking", "outage" |

### Step 2 — Match to Agent

| Agent | Best For | Tools Available |
|-------|----------|----------------|
| `code-reasoning` | Read-only analysis, architecture understanding, flow tracing | File reading, code search |
| `code-writer` | Implementing features, fixing bugs, refactoring | File read/write, code generation |
| `code-reviewer` | Quality review, security audit, PR review, design review | Diff analysis, pattern matching |
| `code-tester` | Writing new tests, debugging test failures | Test frameworks, debugging |
| `qa-regression` | Running test suites, writing missing tests, coverage gaps | Test runner, coverage reports |
| `git-ops` | Branch management, diffs, commit history, push | Git CLI operations |
| `jenkins-cicd` | Build and deploy via Jenkins in one session | Jenkins API |
| `argocd-verify` | Pod health, image verification, log scanning, rollback | ArgoCD API |
| `redash-query` | SQL queries, schema exploration, data analysis | Redash API |
| `jira-ops` | Ticket management, Confluence pages, sprint tracking | Jira/Confluence API |
| `auto-pilot` | Multi-step workflows, full SDLC, incident management, CI/CD pipelines | All agents + all APIs |
| `pipeline-orchestrator` | (Merged into auto-pilot) Use auto-pilot instead | Pipeline state API |

### Step 3 — Consider Complexity

- **Single-domain task** (one agent can handle it): Route directly to that agent.
- **Multi-domain task** (needs 2+ agents): Route to `auto-pilot` which can orchestrate.
- **Ambiguous task**: Ask 1-2 clarifying questions, then route.

### Step 4 — Respond

Provide:
1. **Primary recommendation** — the best agent and WHY
2. **Alternative** (optional) — if another agent could also work, mention it
3. **Invocation hint** — how to call the agent (`/agent-name` in chat, or the API endpoint)
4. **Relevant skills** — if the agent has a specific skill for this task, mention it

Example response:
```
Recommended: code-reviewer
Why: You want a quality review of recent changes — code-reviewer specializes in
PR review, security audits, and design review. It has a `pr-review` skill that
analyzes diffs and provides structured feedback.

Alternative: auto-pilot (if you also want fixes applied after the review)

Invoke: /code-reviewer or /code-reviewer:pr-review
```
