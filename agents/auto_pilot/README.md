# Auto-Pilot — Full Autonomy

> Autonomous orchestrator — delegates to sub-agents, runs full workflows

## Identity

| Field | Value |
|-------|-------|
| **Name** | `auto-pilot` |
| **YAML** | `auto_pilot.yaml` |
| **Backend** | `${CODE_AGENTS_BACKEND:cursor}` |
| **Model** | `${CODE_AGENTS_MODEL:Composer 2 Fast}` |
| **Permission** | `default` — ask before each action |

## Capabilities

- Delegate tasks to specialist sub-agents via HTTP API
- Call Jenkins, ArgoCD, Git, and Testing endpoints directly
- Chain multiple steps: analyze results, decide next action, repeat
- Execute end-to-end workflows (build+deploy, review+fix, investigate)
- Run full SDLC from Jira ticket to production deploy with verification
- Manage 6-step CI/CD pipelines (merged from pipeline-orchestrator): connect, review, build, deploy, verify, rollback
- Plan multi-step workflows before executing with user approval
- Coordinate incident response across agents with severity assessment

## Specialist Sub-Agents

| Agent | Purpose |
|-------|---------|
| `code-reasoning` | Read-only code analysis, architecture, data flows |
| `code-writer` | Write/modify code, implement features, fix bugs |
| `code-reviewer` | Review code for bugs, security, performance |
| `code-tester` | Write tests, debug failures |
| `qa-regression` | Full regression testing, write missing tests |
| `git-ops` | Git branches, diffs, logs, push |
| `redash-query` | SQL queries via Redash |

## Tools & Endpoints

### Sub-Agent API (all via `POST /v1/agents/{name}/chat/completions`)
- `code-reasoning` — read-only code analysis
- `code-writer` — write/modify code
- `code-reviewer` — review code
- `code-tester` — write tests, debug
- `qa-regression` — full regression testing
- `git-ops` — git operations
- `redash-query` — SQL queries via Redash

### Pipeline State API
- `POST /pipeline/start` — begin 6-step pipeline
- `GET /pipeline/{run_id}/status` — current pipeline state
- `POST /pipeline/{run_id}/advance` — advance to next step
- `POST /pipeline/{run_id}/fail` — mark step failed
- `POST /pipeline/{run_id}/rollback` — trigger rollback

### Direct API Endpoints
- `POST /jenkins/build-and-wait` — trigger Jenkins build + poll + extract version
- `GET /jenkins/jobs?folder=...` — list Jenkins jobs
- `GET /jenkins/jobs/{job_path}/parameters` — get job parameters
- `GET /argocd/apps/{app_name}/status` — ArgoCD app status
- `GET /argocd/apps/{app_name}/pods` — list pods
- `GET /git/current-branch` — current git branch
- `GET /git/status` — working tree status
- `GET /git/diff?base=main&head=release` — git diff
- `POST /testing/run` — run tests

## Skills

### Own Skills

| Skill | Description |
|-------|-------------|
| `build-deploy` | Full autonomous build, deploy, and verify workflow |
| `review-fix` | Code review, apply fixes, run tests, and verify |
| `investigate` | Research a problem across code, git history, logs, and databases |
| `full-sdlc` | Master 13-step SDLC: Jira -> analysis -> design review -> code -> test -> review -> build -> push -> Jenkins -> deploy -> verify -> API test -> QA -> done |
| `cicd-pipeline` | 6-step CI/CD pipeline: connect -> review -> build -> deploy -> verify -> rollback (merged from pipeline-orchestrator) |
| `workflow-planner` | Plan multi-step workflows before executing: analyze, identify agents, create plan, get user approval |
| `incident-manager` | Incident management: detect, assess severity, coordinate investigation, recommend fix or rollback |

### Cross-Agent Skills

This agent can invoke skills from other agents directly:

| Skill | Description |
|-------|-------------|
| `jenkins-cicd:git-precheck` | Check branch, status, uncommitted changes |
| `jenkins-cicd:build` | Fetch params, trigger build, poll, extract version |
| `jenkins-cicd:deploy` | Deploy build version to non-prod with confirmation |
| `jenkins-cicd:log-analysis` | Read console logs, extract errors and versions |
| `argocd-verify:health-check` | Check app sync, pod health, image tags |
| `argocd-verify:log-scan` | Scan pod logs for errors |
| `argocd-verify:rollback` | Rollback to previous ArgoCD revision |
| `git-ops:branch-summary` | Current branch, recent commits, diff vs main |
| `code-reviewer:security-review` | OWASP top 10, auth issues, injection |
| `code-reviewer:pr-review` | Full PR review with diff analysis |
| `code-reviewer:design-review` | Review LLD before coding, flag risks, validate patterns |
| `qa-regression:full-regression` | Run full test suite, report results |
| `qa-regression:api-testing` | Test API endpoints with curls, generate pass/fail report |
| `jira-ops:read-ticket` | Fetch and parse Jira ticket details |
| `code-reasoning:system-analysis` | Analyze codebase for a requirement, output structured LLD |

### Shared Engineering Skills

Shared skills from `agents/_shared/skills/` are also available to this agent: architecture, code-review, debug, deploy-checklist, documentation, incident-response, standup, system-design, tech-debt, testing-strategy.

## Usage

### Chat REPL
```bash
code-agents chat auto-pilot
```

### Inline Delegation (from another agent)
```
/auto-pilot <your prompt>
```

### Skill Invocation
```
/auto-pilot:build-deploy <your prompt>
/auto-pilot:full-sdlc <your prompt>
/auto-pilot:investigate <your prompt>
/auto-pilot:cicd-pipeline <your prompt>
/auto-pilot:workflow-planner <your prompt>
/auto-pilot:incident-manager <your prompt>
```

### API
```bash
curl -X POST http://localhost:8000/v1/agents/auto-pilot/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "your prompt"}], "stream": true}'
```

## Example Prompts

1. "Build and deploy {repo} to dev"
2. "Review the latest changes, fix issues, and run tests"
3. "Run the full CI/CD pipeline for release branch"
4. "Check what changed since last deploy, review, and build"
5. "Pick up TEAM-1234 and take it from Jira to deployed"

## Autorun Config

This agent has an `autorun.yaml` that defines allowed and blocked commands for auto-execution.

## Rules

Custom rules to guide this agent's behavior:

| Scope | Path |
|-------|------|
| Global | `~/.code-agents/rules/auto-pilot.md` |
| Project | `.code-agents/rules/auto-pilot.md` |

See `code-agents rules create --agent auto-pilot` to create rules.

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

