# Jenkins CI/CD Agent

> Principal DevOps Engineer who owns the CI/CD build and deploy pipeline

## Identity

| Field | Value |
|-------|-------|
| **Name** | `jenkins-cicd` |
| **YAML** | `jenkins_cicd.yaml` |
| **Role** | Principal DevOps Engineer (Build & Deploy) |
| **Backend** | `${CODE_AGENTS_BACKEND:cursor}` |
| **Model** | `${CODE_AGENTS_MODEL:Composer 2 Fast}` |
| **Permission** | `default` — ask before each action |

## Session Scratchpad

Discovered facts (branch, repo, job path, parameters, image tag) persist to `/tmp/code-agents/<session>/state.json` via `[REMEMBER:key=value]` tags. Injected as `[Session Memory]` block on every turn — agent skips re-fetching known values. Reusable facts (branch, job) cached; build results stored for deploy but never prevent re-builds.

## Upfront Questionnaire

For ambiguous requests ("push my changes", "help with CI/CD"), the agent emits multiple `[QUESTION:]` tags at once — shown as a tabbed wizard:
- `[QUESTION:cicd_action]` — Build only / Build+Deploy / Deploy only / Check status / Troubleshoot
- `[QUESTION:deploy_environment_class]` — Dev / QA
- `[QUESTION:cicd_branch]` — Current branch / main / release / develop
- `[QUESTION:cicd_java_version]` — java21 / java17 / java11

Every question includes "Other — describe in detail" for custom input. For explicit commands ("build", "deploy to qa4"), intake is skipped.

## Capabilities

- Git pre-check: current branch, status, uncommitted changes
- List and discover Jenkins build/deploy jobs and their parameters
- Trigger builds, poll for completion, extract build version from logs
- Trigger deployments using the build version as image_tag
- Fetch build/deploy logs and analyze results
- Manage Jenkins pipelines: list jobs, check health, monitor queue, view history
- Deployment strategy: choose environment, rolling vs blue-green, pre/post-deploy checks
- Troubleshoot build failures: parse console log, identify root cause, suggest fix, retry
- Multi-service deployment: dependency-aware ordering, health checks between deploys, rollback on failure
- NON-PROD ONLY: deploys to dev, dev-stable, staging, qa, uat — never production

## Tools & Endpoints

### Git API (for pre-check)
- `GET /git/current-branch` — current branch name
- `GET /git/status` — working tree status
- `GET /git/branches` — list all branches
- `GET /git/log?branch={branch}&limit=5` — recent commits
- `GET /git/diff?base=main&head={branch}` — diff vs main

### Jenkins API — Discovery
- `GET /jenkins/jobs?folder=FOLDER` — list jobs in folder
- `GET /jenkins/jobs/{job_path}/parameters` — get parameters for any job

### Jenkins API — Build & Deploy
- `POST /jenkins/build-and-wait` — trigger build/deploy + poll + extract version
  - Build: `{"job_name": "BUILD_JOB", "parameters": {"branch": "release", "java_version": "java21"}}`
  - Deploy: `{"job_name": "DEPLOY_JOB", "parameters": {"image_tag": "VERSION", "service": "SVC", "env_name": "dev"}}`
  - Returns: `{result, build_number, build_version, duration, log_tail}`

### Jenkins API — Status & Logs
- `GET /jenkins/build/{job_name}/{build_number}/status` — build status
- `GET /jenkins/build/{job_name}/{build_number}/log` — build log
- `GET /jenkins/build/{job_name}/last` — last build info

## Skills

### Own Skills

| Skill | Description |
|-------|-------------|
| `git-precheck` | Detect current branch, check uncommitted changes, warn user |
| `build` | Fetch params, trigger build, poll, extract version from logs |
| `deploy` | Deploy a build version to non-prod environment with confirmation |
| `log-analysis` | Read build/deploy console logs, extract errors, test results, version tags |
| `pipeline-manager` | Manage Jenkins pipelines: list jobs, check health, trigger parameterized builds, monitor queue, view history |
| `deploy-strategy` | Deployment strategy: choose env, rolling vs blue-green, pre-deploy checks, post-deploy verification |
| `build-troubleshoot` | Troubleshoot build failures: parse console log, identify root cause, suggest fix, retry |
| `multi-service-deploy` | Deploy multiple services in dependency order with health checks and rollback on failure |

### Shared Engineering Skills

Shared skills from `agents/_shared/skills/` are also available to this agent: architecture, code-review, debug, deploy-checklist, documentation, incident-response, standup, system-design, tech-debt, testing-strategy.

## Usage

### Chat REPL
```bash
code-agents chat jenkins-cicd
```

### Inline Delegation (from another agent)
```
/jenkins-cicd <your prompt>
```

### Skill Invocation
```
/jenkins-cicd:git-precheck
/jenkins-cicd:build
/jenkins-cicd:deploy
/jenkins-cicd:log-analysis
/jenkins-cicd:pipeline-manager
/jenkins-cicd:deploy-strategy
/jenkins-cicd:build-troubleshoot
/jenkins-cicd:multi-service-deploy
```

### API
```bash
curl -X POST http://localhost:8000/v1/agents/jenkins-cicd/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "your prompt"}], "stream": true}'
```

## Example Prompts

1. "Build {repo}"
2. "Build and deploy {repo}"
3. "Deploy the latest build — which environments are available?"
4. "What's the status of the last build?"
5. "List all jobs in the payments folder"
6. "The last build failed — what went wrong?"
7. "Deploy auth-svc and payment-svc to staging in the right order"
8. "What's the best deployment strategy for staging?"

## Autorun Config

This agent has an `autorun.yaml` that defines allowed and blocked commands for auto-execution.

## Rules

Custom rules to guide this agent's behavior:

| Scope | Path |
|-------|------|
| Global | `~/.code-agents/rules/jenkins-cicd.md` |
| Project | `.code-agents/rules/jenkins-cicd.md` |

See `code-agents rules create --agent jenkins-cicd` to create rules.

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

