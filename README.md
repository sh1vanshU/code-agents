# Code Agents

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Tests: 4723 passing](https://img.shields.io/badge/tests-4723%20passing-brightgreen.svg)]()

AI-powered code agent platform with interactive chat and a built-in CI/CD pipeline. Define agents in YAML, chat with them from the terminal, and automate: **review → test → build → deploy → verify → rollback**.

## Install

```bash
# Step 1: Clone and install
git clone git@github.com:code-agents-org/code-agents.git ~/.code-agents
bash ~/.code-agents/install.sh

# Step 2: Pick up ~/.local/bin (the installer adds this to your shell config)
# Prefer: close and reopen the terminal (avoids re-running a broken ~/.zshrc).
# Or, only for this session — no sourcing required:
export PATH="$HOME/.local/bin:$PATH"
# If you use zsh and want to reload config (needs a valid ~/.zshrc):
#   source ~/.zshrc
# bash:
#   source ~/.bashrc
# If `source` errors, fix or comment the failing lines in that file, or rely on
# `export PATH=...` above / a new terminal window instead.

# Step 3: Initialize in your project
cd /path/to/your-project
code-agents init          # smart project detection + configure keys
code-agents start         # start the server (background)
code-agents chat          # interactive chat — pick an agent, start talking

# Update to latest
code-agents update        # git pull + reinstall deps + refresh completions
```

**Detailed setup (local LLM, env vars, backends):** see [setup.md](setup.md).

### Prerequisites

| Tool | Required | Install |
|------|----------|---------|
| Python 3.10+ | Yes | `brew install python@3.12` or [python.org](https://www.python.org/downloads/) |
| Poetry | Auto-installed | `curl -sSL https://install.python-poetry.org \| python3 -` |
| Git | Yes | `brew install git` or `apt install git` |
| kubectl | For K8s features | `brew install kubectl` |

## Interactive Chat

`code-agents chat` is the primary way to interact. Pick an agent from the menu, then talk:

```
$ code-agents chat

  Select an agent:
    1.  auto-pilot        Autonomous orchestrator — delegates, routes, pipelines
    2.  code-reasoning    Analyze code, explain architecture, trace flows
    3.  code-reviewer     Review code for bugs, security issues, style
    ...

  Pick agent [1-13]: 2

  you › Explain the architecture of this project
  code-reasoning › This project follows a layered architecture...

  you › /code-reviewer Review the auth module for security issues
  Delegating to code-reviewer...
  (back to code-reasoning)
```

**Key features:** auto-detects git repo, auto-starts server, multi-turn sessions with persistence, real-time streaming, agent switching (`/agent <name>`), inline delegation (`/<agent> <prompt>`), Tab-completion, command execution with approval, plan mode, superpower mode, background agents, pair programming mode, live tail, agent replay.

Chat commands: `/help /agent /run /exec /rules /skills /tokens /session /plan /superpower /export /mcp /blame /investigate /kb /generate-tests /deps /pair /refactor /verify /qa-suite /pr-preview /coverage-boost /config-diff /flags /pr-describe /postmortem /dep-upgrade /review-buddy /db-migrate /oncall-summary /test-impact /runbook /sprint-dashboard /explain /mindmap /review /dep-impact /corrections /bg /tasks /replay /traces /tail /api-docs /translate /profile /schema /changelog /dashboard /txn-flow /recon /pci-scan /idempotency /validate-states /acquirer-health /retry-audit /load-test /postmortem-gen /settlement /migrate-tracing /<agent> <prompt> /<agent>:<skill>` (and more — `/help` for full list)

## CLI Commands

```bash
code-agents help    # full help with all args
```

### Core Workflow
| Command | Description |
|---------|-------------|
| `init [--profile]` | Configure keys, write global + per-repo config |
| `start [--fg]` | Start server (background). `--fg` for foreground |
| `chat [agent] [--resume <id>]` | Interactive chat. No args = agent picker |
| `setup` | Full interactive setup wizard |
| `shutdown` / `restart` | Stop or restart the server |
| `status` / `doctor` | Health check / diagnose issues |
| `config` / `logs [N]` | Show config / tail log file |

### Development
| Command | Description |
|---------|-------------|
| `test [branch]` | Run tests (auto-detects pytest/jest/maven/gradle/go) |
| `review [base] [head]` | AI code review via code-reviewer agent |
| `commit [--auto\|--dry-run]` | Smart commit with conventional message |
| `diff [base] [head]` | Git diff. Default: `main HEAD` |
| `branches` | List branches, highlight current |
| `security [--json\|--category]` | OWASP top 10 security scan |
| `deadcode [--language\|--json]` | Find unused imports, functions, endpoints |
| `coverage-boost [--dry-run\|--target N]` | Auto-boost test coverage |
| `qa-suite [--analyze\|--write\|--commit]` | Auto-generate QA regression test suite |
| `audit` | Dependency vulnerability + license audit |
| `complexity` | Cyclomatic + cognitive complexity analysis |
| `export` | Export CLAUDE.md / .cursorrules for Claude Code or Cursor |
| `mindmap [--mermaid\|--html]` | Visual repo structure (ASCII/Mermaid/HTML) |
| `api-docs [--format]` | Generate OpenAPI/Markdown/HTML API docs |
| `translate <file> --to <lang>` | Cross-language code translation |
| `profiler <file>` | cProfile analysis with optimization suggestions |
| `schema [--format]` | ER diagrams from live DB or SQL files |
| `changelog-gen` | Auto-generate changelog from git history + PRs |
| `dashboard` | Code health: tests, coverage, complexity, PRs |
| `impact [--package]` | Dependency upgrade impact scanner |
| `install-hooks` | AI-powered pre-commit and pre-push git hooks |
| `pair` | AI pair programming with file watcher |
| `tail <service>` | Real-time log streaming with anomaly detection |
| `replay [--session]` | Time travel debugging with session traces |
| `index` | Build RAG vector index for smart context |
| `bg [list\|cancel]` | Manage background agents |
| `migrate-tracing` | Jaeger/Datadog/Zipkin to OpenTelemetry migration |

### Productivity
| Command | Description |
|---------|-------------|
| `pr-describe [--base]` | Generate PR description from branch diff |
| `review-buddy [--all\|--fix]` | Pre-push code review against conventions |
| `test-impact [--run\|--base]` | Smart test runner — only impacted tests |
| `explain "<question>"` | Ask questions about the codebase |
| `dep-upgrade [--package\|--all]` | Scan and upgrade outdated dependencies |
| `db-migrate "<description>"` | Generate DB migration from plain English |
| `runbook <name> [--list\|--execute]` | Execute runbooks with safety gates |
| `postmortem --from <time>` | Generate incident postmortem report |
| `oncall-summary [--hours N]` | Summarize on-call alerts + standup |
| `sprint-dashboard [--days N]` | Sprint velocity + cycle time dashboard |

### Payment Gateway
| Command | Description |
|---------|-------------|
| `txn-flow <txn-id>` | Transaction journey visualizer |
| `recon [--date\|--merchant]` | Reconciliation debugger (order vs settlement) |
| `pci-scan [--strict]` | PCI-DSS compliance scanner |
| `audit-idempotency` | Payment endpoint idempotency auditor |
| `validate-states` | Transaction state machine validator |
| `acquirer-health [--acquirer]` | Acquirer integration health monitor |
| `retry-audit` | Payment retry strategy analyzer |
| `load-test [--format k6\|locust\|jmeter]` | Load test scenario generator |
| `postmortem-gen [--incident]` | Incident postmortem auto-generator |
| `settlement <file>` | Settlement file parser (Visa/MC/UPI) |

### CI/CD & Reporting
| Command | Description |
|---------|-------------|
| `pipeline start\|status\|advance\|rollback` | 6-step CI/CD pipeline management |
| `release <version> [--dry-run]` | End-to-end release automation |
| `incident <service> [--rca\|--save]` | Investigate service incident |
| `oncall-report [--days N\|--save\|--slack]` | On-call handoff report |
| `pr-preview [base]` | Preview PR: diff stats, risk score, tests |
| `changelog` | Auto-generate CHANGELOG from git history |
| `sprint-velocity [--sprints N]` | Sprint velocity tracking from Jira |
| `morning` | Morning standup assistant |
| `onboard [--save\|--full]` | Generate onboarding guide |
| `repos [add\|remove]` | Manage multi-repo support |
| `sessions [--all\|delete\|clear]` | Manage saved chat sessions |
| `agents` / `curls` / `version` | List agents / show API curls / version info |

## Agent Rules

Persistent instructions injected into agent system prompts. Auto-refresh on every message.

| Tier | Location | Scope |
|------|----------|-------|
| Global | `~/.code-agents/rules/` | All projects |
| Project | `{repo}/.code-agents/rules/` | This project only |

File names: `_global.md` (all agents) or `<agent-name>.md` (single agent).

```bash
code-agents rules create                      # project rule → all agents
code-agents rules create --agent code-writer  # project rule → code-writer only
code-agents rules create --global             # global rule → all agents, all projects
code-agents rules list [--agent <name>]       # list active rules
code-agents rules edit <path>                 # open in $EDITOR
```

In chat: `/rules` shows active rules for the current agent.

## Agents (18)

| Agent | Role | Permissions |
|---|---|---|
| `auto-pilot` | Autonomous orchestrator — delegates to sub-agents, runs full workflows, pipeline orchestration, agent routing | Read-only |
| `code-reasoning` | Explains architecture, traces flows, analyzes code, codebase exploration | Read-only |
| `code-writer` | Writes/modifies code, refactors, implements features | Auto-approve edits |
| `code-reviewer` | Reviews for bugs, security issues, style violations | Read-only |
| `code-tester` | Writes tests, debugs, optimizes code quality | Auto-approve edits |
| `redash-query` | SQL queries, schema exploration via Redash | Read-only |
| `git-ops` | Git branches, diffs, logs, push | Read-only |
| `test-coverage` | Runs test suites, coverage reports, finds gaps | Auto-approve edits |
| `jenkins-cicd` | Build, deploy, AND ArgoCD verification via Jenkins — upfront questionnaire, session scratchpad, end-to-end CI/CD | Read-only |
| `argocd-verify` | Checks ArgoCD pods, scans logs, rollbacks | Read-only |
| `qa-regression` | Runs regression suites, writes missing tests, eliminates manual QA | Auto-approve edits |
| `jira-ops` | Jira/Confluence: ticket lifecycle, sprint planning, release tracking | Read-only |
| `security` | Vulnerability scanning, dependency audit, secrets detection, compliance review | Read-only |
| `github-actions` | Trigger, monitor, retry, and debug GitHub Actions workflows | Read-only |
| `grafana-ops` | Search dashboards, query metrics, investigate alerts, correlate deployments | Read-only |
| `terraform-ops` | Terraform plan/apply/drift-detect with safety gates | Read-only |
| `db-ops` | PostgreSQL safe queries, schema inspection, migration generation | Read-only |
| `pr-review` | Automated PR review — fetch, analyze, post inline comments | Read-only |
| `debug-agent` | Autonomous debugging: reproduce, trace, root cause, fix, verify | Read-only |

## CI/CD Pipeline

6-step deployment pipeline:

```
1. Connect      → Verify repo, show branch diff
2. Review/Test  → AI code review + run tests + verify coverage
3. Push/Build   → Push code, trigger Jenkins build
4. Deploy       → Trigger Jenkins deployment job
5. Verify       → Check ArgoCD pods, scan logs for errors
6. Rollback     → Revert to previous revision (if anything fails)
```

REST APIs: `/pipeline/*`, `/git/*`, `/testing/*`, `/jenkins/*`, `/argocd/*`, `/k8s/*`, `/jira/*`, `/kibana/*`, `/mcp/*`, `/telemetry/*`, `/github-actions/*`, `/grafana/*`, `/terraform/*`, `/db/*`, `/pr-review/*`

**Dashboards:** Chat UI: `http://localhost:8000/ui` · Telemetry: `http://localhost:8000/telemetry-dashboard`

## Environment Variables

| Variable | Description |
|----------|-------------|
| `CURSOR_API_KEY` / `ANTHROPIC_API_KEY` | Backend API keys |
| `CODE_AGENTS_BACKEND` | Global backend: `cursor`, `claude`, `claude-cli` |
| `CODE_AGENTS_MODEL` | Global model (default: `Composer 2 Fast`) |
| `CODE_AGENTS_NICKNAME` | User name in REPL prompt (default: `you`) |
| `CODE_AGENTS_THEME` | `dark` (default), `light`, `minimal` |
| `CODE_AGENTS_AUTO_RUN` | `true` (default) / `false` to disable auto-run |
| `CODE_AGENTS_DRY_RUN` | `true` to show commands without executing |
| `CODE_AGENTS_MAX_LOOPS` | Max agentic loop rounds (default: `10`) |
| `JENKINS_URL` / `JENKINS_USERNAME` / `JENKINS_API_TOKEN` | Jenkins CI/CD |
| `ARGOCD_URL` / `ARGOCD_AUTH_TOKEN` / `ARGOCD_APP_NAME` | ArgoCD config |
| `JIRA_URL` / `JIRA_EMAIL` / `JIRA_API_TOKEN` | Jira integration |
| `KIBANA_URL` / `KIBANA_USERNAME` / `KIBANA_PASSWORD` | Kibana log viewer |
| `ELASTICSEARCH_URL` / `ELASTICSEARCH_API_KEY` | Elasticsearch integration |
| `REDASH_BASE_URL` / `REDASH_API_KEY` | Redash database queries |
| `CODE_AGENTS_CONTEXT_WINDOW` | Conversation pairs to keep (default: `5`) |
| `CODE_AGENTS_MAX_SESSION_TOKENS` | Stop loop when exceeded |
| `CODE_AGENTS_REQUIRE_CONFIRM` | Spec-before-execution gate (default: `true`) |
| `CODE_AGENTS_SANDBOX` | Restrict writes to project dir |
| `CODE_AGENTS_CORS_ORIGINS` | Custom CORS origins (comma-separated, default: localhost) |
| `CURSOR_API_URL` | OpenAI-compatible URL for Cursor HTTP mode |
| `CODE_AGENTS_SLACK_WEBHOOK_URL` | Slack notifications |
| `CODE_AGENTS_SLACK_BOT_TOKEN` | Slack Bot Bridge |
| `HOST` / `PORT` | Server bind (default: `0.0.0.0:8000`) |

Full list with defaults: `.env.example`. Per-agent overrides: `CODE_AGENTS_BACKEND_<AGENT>`, `CODE_AGENTS_MODEL_<AGENT>`.

## Testing

```bash
poetry run pytest       # 4723 tests
code-agents doctor      # diagnose setup
code-agents test        # run tests on target repo
```

## Open WebUI Integration

1. `code-agents start`
2. Open WebUI → Settings → Connections → OpenAI
3. URL: `http://localhost:8000/v1`, Key: any string
4. All 18 agents appear as models

## Docker

```bash
docker build -t code-agents .
docker run -p 8000:8000 -e CURSOR_API_KEY=your-key code-agents
```

## Export for Claude Code / Cursor

Generate editor-specific context files from your project's agent configuration:

```bash
code-agents export              # auto-detect editor, write CLAUDE.md or .cursorrules
code-agents export --claude     # force CLAUDE.md output
code-agents export --cursor     # force .cursorrules output
code-agents export --dry-run    # preview without writing
```

The export command builds a context file from your agent configs, project rules, and skill index so external editors have full project awareness.

## Project Structure

```
code-agents/
  install.sh                    # One-command installer
  pyproject.toml                # Poetry config, CLI entry points
  agents/<name>/                # 19 agent subfolders (18 agents + _shared)
    <name>.yaml                 #   Agent config (system prompt + skill index)
    skills/*.md                 #   Reusable workflows (154 total)
    autorun.yaml                #   Per-agent command allowlist/blocklist
  code_agents/
    cli/                        #   ~60 CLI commands
    chat/                       #   Chat REPL (UI, commands, history, streaming)
      tui/                      #   Textual TUI (Claude Code-style interface)
    cicd/                       #   Jenkins, ArgoCD, Git, K8s, GitHub Actions, Terraform clients
    routers/                    #   17 FastAPI route handlers
    parsers/                    #   Multi-language AST parsers (Python/JS/TS/Java/Go)
    webui/                      #   Browser chat UI + telemetry dashboard
    app.py / config.py          #   FastAPI app + settings + agent loader
    backend.py / stream.py      #   Backend dispatcher + SSE streaming
    knowledge_graph.py          #   Project structure index for AI context
    requirement_confirm.py      #   Spec-before-execution gate
    command_panel.py            #   Rich command panels for setup/config flows
    session_scratchpad.py       #   /tmp session context persistence ([REMEMBER:] tags)
    action_log.py               #   Audit trail for agent actions
    diff_preview.py             #   Inline annotated diff rendering
    skill_marketplace.py        #   Community skill sharing
    voice_mode.py / voice_output.py  # Voice input/output
  extensions/                   # IDE plugins & browser extensions
    vscode/                    #   VS Code extension (chat sidebar, 10 commands, SSE streaming)
    intellij/                  #   IntelliJ plugin (JCEF, Kotlin, all JetBrains IDEs)
    chrome/                    #   Chrome extension (side panel chat, GitHub/Jira context)
  tests/                        # 4723 tests (190+ test files)
  initiater/                    # Project audit system (14 rules)
```

## Contributing

1. Fork → `git checkout -b my-feature`
2. `poetry install --with dev`
3. Make changes → `poetry run pytest`
4. Submit PR

## License

[MIT](LICENSE) — Copyright (c) 2026 Code Agents Contributors (Regulated by RBI)
