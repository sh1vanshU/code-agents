# Architecture — Code Agents

## Overview

Code Agents is a CLI-first AI agent platform. Users define agents in YAML, interact via terminal chat, and automate CI/CD pipelines. The system exposes all agents as OpenAI-compatible API endpoints.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         USER INTERFACE                                    │
│                                                                           │
│  code-agents chat          Terminal REPL (chat/)                         │
│  code-agents start         FastAPI Server (app.py)                       │
│  http://localhost:8000/ui  Browser Chat (webui/)                         │
│  Open WebUI / curl         HTTP API (routers/)                           │
└──────────────┬──────────────────────────┬─────────────────────────────────┘
               │                          │
               ▼                          ▼
┌──────────────────────────┐  ┌─────────────────────────────────────────────┐
│    Chat REPL (chat/)      │  │           FastAPI Server                    │
│                           │  │                                             │
│  Agent picker menu        │  │  POST /v1/agents/{name}/chat/completions   │
│  ~30 slash commands       │  │  GET  /v1/agents, /v1/models               │
│    /plan (plan mode)      │  │  GET  /health, /diagnostics, /ui           │
│    /superpower (auto-run) │  │                                             │
│    /setup (in-chat config)│  │  Routers (16):                              │
│    /skills, /memory       │  │    completions → stream.py → backend.py    │
│  Inline delegation        │  │    jenkins, argocd, git_ops, testing       │
│  Skill loading [SKILL:]   │  │    pipeline, redash, elasticsearch          │
│  Agent chaining [DELEGATE]│  │    jira, kibana, k8s, telemetry            │
│  Agentic loop (10 rounds) │  │    webui (browser chat at /ui)              │
│  Auto-run + Superpower    │  │                                             │
│  Tab-completion           │  │                                             │
│  Session persistence      │  │                                             │
│  Token tracking per msg   │  │                                             │
└──────────┬────────────────┘  └──────────────┬─────────────────────────────┘
           │                                  │
           ▼                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        BACKEND LAYER                                      │
│                                                                           │
│  backend.py — dispatches to one of 3 backends:                           │
│                                                                           │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐                     │
│  │   Cursor     │  │  Claude API  │  │  Claude CLI   │                    │
│  │  (SDK/CLI)   │  │  (SDK)       │  │ (subscription)│                    │
│  └─────────────┘  └─────────────┘  └──────────────┘                     │
│                                                                           │
│  Per-agent overrides: CODE_AGENTS_BACKEND_<AGENT>, MODEL_<AGENT>         │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     INTEGRATION LAYER (cicd/)                             │
│                                                                           │
│  ┌──────────┐ ┌──────────┐ ┌────────┐ ┌─────────┐ ┌────────┐          │
│  │ Jenkins   │ │ ArgoCD   │ │  Git   │ │ Testing │ │Pipeline│          │
│  │ CI/CD     │ │ Verify   │ │  Ops   │ │ Runner  │ │ State  │          │
│  └──────────┘ └──────────┘ └────────┘ └─────────┘ └────────┘          │
│  ┌──────────┐ ┌──────────┐ ┌────────┐                                   │
│  │  Jira/   │ │ Kibana   │ │  K8s   │                                   │
│  │Confluence│ │  Logs    │ │(kubectl │                                   │
│  │  (REST)  │ │  (ES)   │ │ + SSH) │                                   │
│  └──────────┘ └──────────┘ └────────┘                                   │
└─────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        AGENT LAYER (13 agents + _shared)                  │
│                                                                           │
│  141 Skills — on-demand loading via [SKILL:name]                          │
│  Per-agent: autorun.yaml (allow/block), skills/*.md, README.md           │
│                                                                           │
│  ┌─────────────┐ ┌─────────────┐ ┌──────────────┐ ┌──────────────┐     │
│  │ code-writer  │ │ code-tester  │ │code-reviewer  │ │code-reasoning│     │
│  │ (write+test) │ │ (test+fix)   │ │(review+design)│ │(analysis+LLD)│     │
│  └─────────────┘ └─────────────┘ └──────────────┘ └──────────────┘     │
│  ┌─────────────┐ ┌─────────────┐ ┌──────────────┐ ┌──────────────┐     │
│  │jenkins-cicd  │ │argocd-verify │ │  git-ops      │ │test-coverage  │     │
│  │(build+deploy)│ │(pods+kibana) │ │(branch+push)  │ │(run+coverage) │     │
│  └─────────────┘ └─────────────┘ └──────────────┘ └──────────────┘     │
│  ┌─────────────┐ ┌─────────────┐ ┌──────────────┐ ┌──────────────┐     │
│  │qa-regression │ │ redash-query │ │  auto-pilot   │ │  jira-ops     │     │
│  │(api+negative)│ │  (SQL)       │ │(full-sdlc)    │ │(tickets+wiki) │     │
│  └─────────────┘ └─────────────┘ └──────────────┘ └──────────────┘     │
│  (pipeline-orchestrator and agent-router merged into auto-pilot)          │
│                                                                           │
│  SDLC Pipeline (auto-pilot:full-sdlc):                                   │
│  Jira → Analysis → Design Review → Code → Test → Review →               │
│  Build → Git Push → Jenkins → Deploy → Verify/Kibana →                   │
│  API Testing → QA Regression → Done                                      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Request Flow

### Chat REPL Path (code-agents chat)

```
User types message
    │
    ▼
chat.py:chat_main()
    ├── Load rules (rules_loader.py — fresh every message)
    ├── Load session scratchpad (session_scratchpad.py — /tmp context)
    ├── Build system context (repo path, bash tool, rules, [Session Memory])
    ├── POST /v1/agents/{agent}/chat/completions
    │     └── routers/completions.py → stream.py
    │           ├── Inject rules into agent.system_prompt
    │           ├── build_prompt() — pack conversation history
    │           └── backend.py:run_agent()
    │                 ├── cursor backend → cursor-agent CLI
    │                 ├── claude backend → claude-agent-sdk
    │                 └── claude-cli backend → claude --print
    ├── Stream response (spinner + timer, auto-collapse >25 lines)
    ├── Extract ```bash commands → auto-run or prompt (Yes/Save/No)
    │     ├── Resolve {placeholders}, run with live timer
    │     └── Feed output back to agent (agentic loop, max 10 rounds)
    └── Save session to chat_history/
```

### API Path (curl / Open WebUI)

```
HTTP POST /v1/agents/{agent}/chat/completions
    │
    ▼
routers/completions.py
    ├── Resolve agent by name/display_name/model
    ├── stream_response() or collect_response()
    │     └── stream.py
    │           ├── load_rules(agent, cwd) — inject into system_prompt
    │           ├── build_prompt(messages) — single or multi-turn
    │           └── run_agent() → backend.py → cursor/claude/claude-cli
    └── Return SSE stream or JSON response
```

---

## Package Structure

### Core

| Module | Purpose |
|--------|---------|
| `app.py` | FastAPI server. CORS, lifespan, request/response logging middleware |
| `main.py` | Uvicorn launcher. Loads env, starts server |
| `config.py` | `AgentConfig`, `Settings`, `AgentLoader` (reads YAML, expands `${VAR}`, per-agent overrides) |
| `backend.py` | Backend dispatcher: cursor CLI, cursor HTTP, claude SDK, claude CLI |
| `stream.py` | SSE streaming, OpenAI-compatible chunks, `build_prompt()` for multi-turn |
| `models.py` | Pydantic request/response models (OpenAI-compatible) |

### Packages

| Package | Purpose |
|---------|---------|
| `cli/` | ~45 CLI commands (`cli.py`), shared helpers, shell tab-completion |
| `chat/` | REPL loop, UI, slash commands, session persistence, streaming, prompt_toolkit input |
| `setup/` | Interactive 7-step wizard, env file parsing and writing |
| `cicd/` | Jenkins, ArgoCD, Git, Testing, Pipeline, Jira, Kibana, K8s integration clients |
| `routers/` | 16 FastAPI route handlers |
| `webui/` | Browser chat at `/ui` (static HTML/CSS/JS, no build step) |

### Configuration & State

| Module | Purpose |
|--------|---------|
| `env_loader.py` | Two-tier config: global (`~/.code-agents/config.env`) + per-repo (`.env.code-agents`) |
| `rules_loader.py` | Two-tier rules: global + project, auto-refresh every message |
| `skill_loader.py` | Skill discovery from `agents/<name>/skills/*.md`, on-demand loading |
| `agent_memory.py` | Persistent agent learnings at `~/.code-agents/memory/<agent>.md` |
| `context_manager.py` | Smart context window: auto-trim to last N pairs, preserve code blocks |
| `token_tracker.py` | Per-message/session/day token tracking, CSV export, cost guard |
| `plan_manager.py` | Plan mode lifecycle (create, approve, reject, execute, complete) |
| `session_scratchpad.py` | Per-session `/tmp` key-value store. Agents write `[REMEMBER:key=value]`, read `[Session Memory]` block. 1-hour TTL |
| `mcp_client.py` | MCP plugin system: stdio + SSE transport, JSON-RPC, service intelligence |

### API Routers

| Router | Prefix / Endpoints |
|--------|--------------------|
| `completions.py` | `POST /v1/agents/{name}/chat/completions` |
| `agents_list.py` | `GET /v1/agents`, `GET /v1/models` |
| `jenkins.py` | `/jenkins/*` — jobs, build, build-and-wait |
| `argocd.py` | `/argocd/*` — status, pods, logs, sync, rollback |
| `git_ops.py` | `/git/*` — branches, diff, log, status, push, checkout, stash, merge, add, commit |
| `testing.py` | `/testing/*` — run, coverage, gaps |
| `pipeline.py` | `/pipeline/*` — start, status, advance, rollback |
| `jira.py` | `/jira/*` — issues, search, transitions, confluence |
| `kibana.py` | `/kibana/*` — search, tail, services |
| `k8s.py` | `/k8s/*` — pods, logs, exec |
| `mcp.py` | `/mcp/*` — servers, tools, call, start, stop |
| `telemetry.py` | `/telemetry/*` — summary, agents, commands, errors |
| `slack_bot.py` | `POST /slack/events`, `GET /slack/status` |

---

## Data Flow: Backends

| Backend | How it works | Requires |
|---------|-------------|---------|
| `cursor` (default) | `cursor_agent_sdk.query()` → spawns `cursor-agent --print` | `CURSOR_API_KEY` + cursor-agent CLI |
| `claude` | `claude_agent_sdk.query()` → Anthropic Messages API | `ANTHROPIC_API_KEY` |
| `claude-cli` | `subprocess: claude --print --output-format json` → Pro/Max subscription auth | `claude` CLI + logged in |

Enable per-agent: `CODE_AGENTS_BACKEND_<AGENT>=claude-cli`. Enable globally: `CODE_AGENTS_BACKEND=claude-cli`.

---

## IDE Extensions

All extensions connect to the same code-agents server API (`/v1/chat/completions`).

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  VS Code     │     │  IntelliJ    │     │  Chrome      │
│  Extension   │     │  Plugin      │     │  Extension   │
│ (Webview +   │     │ (JCEF +      │     │ (Side Panel  │
│  postMessage)│     │  JBCefJSQuery)│    │  + fetch)    │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       │  SSE streaming     │  fetch() direct    │  SSE streaming
       │  via Node.js http  │  from JCEF browser │  via browser fetch
       │                    │                    │
       └────────────────────┴────────────────────┘
                            │
                 ┌──────────▼──────────┐
                 │  Code Agents Server  │
                 │  localhost:8000      │
                 │  /v1/chat/completions│
                 └─────────────────────┘
```

| Extension | Location | UI Rendering | Communication |
|-----------|----------|-------------|---------------|
| VS Code | `extensions/vscode/` | WebviewViewProvider | postMessage ↔ Node.js http |
| IntelliJ | `extensions/intellij/` | JBCefBrowser (JCEF) | JBCefJSQuery ↔ fetch() |
| Chrome | `extensions/chrome/` | Side Panel HTML | fetch() direct |

Shared webview codebase: `extensions/vscode/webview-ui/` (same HTML/CSS/JS in all three).
Build all: `cd extensions && make all`. Test: `make test`. Package: `make package`.

### Architecture Decisions (IDE Extensions)

| Decision | Choice | Why |
|----------|--------|-----|
| VS Code sidebar approach | WebviewViewProvider (not Chat Participant API) | Full UI control, custom branding, works without Copilot installed |
| IntelliJ rendering | JCEF/JBCefBrowser (not Swing) | Reuses same HTML/CSS/JS as VS Code — one codebase, two IDEs |
| Webview framework | Vanilla TypeScript (no React/Vue) | Keeps bundle tiny (~49KB), no framework dependency, faster startup |
| Communication model | VS Code: postMessage proxy via Node.js http; IntelliJ: JCEF direct fetch() | VS Code CSP blocks direct fetch; JCEF has full network access |
| Theme system | CSS custom properties with `--vscode-*` fallbacks | Auto-inherits IDE theme, supports 4 explicit themes + WCAG AA |
| SSE streaming | Node.js `http.request` (not browser fetch) | Extension host can't use browser fetch; gives buffer control + timeouts |
| State management | Custom reactive store (not Redux/MobX) | Zero dependencies, ~100 lines, sufficient for sidebar chat |
| Security: JS injection | Base64 encoding for JCEF postMessage | URL encoding had edge cases with single quotes; Base64 is injection-proof |

---

## Data Flow: Configuration

```
~/.code-agents/
  ├── config.env              Global config (API keys, server, integrations)
  ├── rules/                  Global rules
  │   ├── _global.md          → all agents, all projects
  │   └── code-writer.md      → code-writer agent only
  └── chat_history/           Saved chat sessions

{repo}/
  ├── .env.code-agents        Per-repo config (Jenkins, ArgoCD, testing)
  └── .code-agents/
      └── rules/              Project rules
```

**Load order** (later overrides earlier):
1. `~/.code-agents/config.env` (global, `override=False`)
2. `{cwd}/.env` (legacy fallback, `override=True`)
3. `{cwd}/.env.code-agents` (per-repo, `override=True`)

**Rules merge order:**
1. Global `_global.md` → 2. Global `{agent-name}.md` → 3. Project `_global.md` → 4. Project `{agent-name}.md`

---

## Agent Structure

```
agents/<name>/
  <name>.yaml          # Agent config (lean system prompt + skill index)
  README.md            # Agent documentation
  autorun.yaml         # Per-agent command allowlist/blocklist
  skills/              # Reusable workflows (invoked via /<agent>:<skill> or [SKILL:name])
```

### Agent YAML Schema

```yaml
name: jenkins-cicd                     # kebab-case, used in URLs
display_name: "Jenkins CI/CD Agent"    # UI name
backend: "${CODE_AGENTS_BACKEND:cursor}"
model: "${CODE_AGENTS_MODEL:Composer 2 Fast}"
system_prompt: |                       # supports ${ENV_VAR}
  You are a Jenkins CI/CD agent...
permission_mode: default               # default | acceptEdits | bypassPermissions
api_key: ${CURSOR_API_KEY}
```

### 14 Agents

| Agent | Role |
|-------|------|
| `auto-pilot` | Autonomous orchestrator — full SDLC, pipeline, agent routing |
| `code-reasoning` | Read-only analysis, codebase exploration, architecture tracing |
| `code-writer` | Write/modify code (`acceptEdits`) |
| `code-reviewer` | Review for bugs and design |
| `code-tester` | Write tests, debug (`acceptEdits`) |
| `qa-regression` | Full regression testing (`acceptEdits`) |
| `redash-query` | SQL via Redash |
| `git-ops` | Git branch, push, merge operations |
| `test-coverage` | Run tests, measure coverage (`acceptEdits`) |
| `jenkins-cicd` | Build, deploy, AND ArgoCD verification (3-phase pipeline) |
| `argocd-verify` | Advanced ArgoCD: rollback, canary, incident response |
| `jira-ops` | Jira issues and Confluence pages |
| `security` | OWASP scanning, CVE audit, secrets detection |

---

## 6-Step CI/CD Pipeline

```
1. Connect     → git branches, diff, status
2. Review/Test → code-reviewer + test-coverage
3. Push/Build  → git push + jenkins-build (build-and-wait)
4. Deploy      → jenkins-deploy with build_version
5. Verify      → argocd-verify (pods, logs, health)
6. Rollback    → argocd rollback to previous revision
```

State machine: `pipeline_state.py`. API: `/pipeline/start`, `/pipeline/{id}/status`, `/pipeline/{id}/advance`

**Tech stack:** Python 3.10+ · FastAPI/Uvicorn · Pydantic v2 · YAML config · httpx async · cursor/claude SDKs · Jenkins/ArgoCD/Jira REST · pytest · Poetry

---

## Platform Intelligence Layer

Modules that provide deep codebase understanding, agent self-improvement, and background automation.

| Module | Purpose |
|--------|---------|
| `mindmap.py` | Interactive codebase mindmap generation — visual dependency trees and module relationships |
| `code_review.py` | Automated code review with configurable rulesets and severity scoring |
| `dep_impact.py` | Dependency impact analysis — traces how a change propagates through the codebase |
| `agent_corrections.py` | Agent self-correction system — tracks and learns from past mistakes |
| `workspace_graph.py` | Workspace-level dependency graph across multiple repos |
| `workspace_pr.py` | Cross-workspace PR coordination — linked PRs across repos |
| `git_hooks.py` | Git hook management — pre-commit, pre-push, commit-msg hooks |
| `agent_replay.py` | Session replay — re-execute a previous agent session for debugging or verification |
| `rag_context.py` | RAG-based context retrieval — semantic search over codebase for relevant context injection |
| `live_tail.py` | Real-time log tailing from running services with pattern matching and alerting |
| `pair_mode.py` | Pair programming mode — two agents collaborate on a task with turn-taking |
| `background_agent.py` | Background agent execution — long-running tasks that continue after chat disconnect |

---

## Developer Productivity Layer

Modules that accelerate common developer workflows and reduce manual toil.

| Module | Purpose |
|--------|---------|
| `api_docs.py` | Auto-generate API documentation from route handlers and Pydantic models |
| `code_translator.py` | Translate code between languages (Python/JS/TS/Java/Go) preserving logic and idioms |
| `profiler.py` | Performance profiling integration — identify hot paths, memory leaks, slow queries |
| `schema_viz.py` | Database schema visualization — ER diagrams and relationship mapping |
| `changelog.py` | Automated changelog generation from git history with conventional commit parsing |
| `health_dashboard.py` | System health dashboard — agent uptime, response times, error rates, token usage |

---

## Payment Gateway Domain Layer

Specialized modules for payment processing domain — transaction debugging, compliance, and operational health.

| Module | Purpose |
|--------|---------|
| `txn_flow.py` | Transaction flow tracer — follow a payment through all microservices end-to-end |
| `recon_debug.py` | Reconciliation debugger — identify mismatches between payment records and bank settlements |
| `pci_scanner.py` | PCI-DSS compliance scanner — detect violations in code, configs, and infrastructure |
| `idempotency_audit.py` | Idempotency key audit — verify all payment endpoints handle duplicate requests correctly |
| `state_machine_validator.py` | Payment state machine validator — verify all transitions are legal and terminal states reachable |
| `acquirer_health.py` | Acquirer health monitor — track success rates, latency, and error codes per payment acquirer |
| `retry_analyzer.py` | Retry strategy analyzer — detect infinite retry loops, missing backoff, and retry storms |
| `load_test_gen.py` | Load test generator — create realistic payment traffic patterns for stress testing |
| `postmortem_gen.py` | Postmortem generator — auto-draft incident postmortems from logs, alerts, and timeline data |
| `settlement_parser.py` | Settlement file parser — parse and validate bank settlement files across formats |

---

## Migration Tooling

| Module | Purpose |
|--------|---------|
| `tracing_migration.py` | Tracing migration assistant — migrate from legacy tracing (Jaeger/Zipkin) to OpenTelemetry |

---

## Observability

| Module | Purpose |
|--------|---------|
| `otel.py` | OpenTelemetry integration — distributed tracing, metrics, and log correlation for all agents |
| `logging_config.py` | Structured JSON logging — consistent log format across all modules with request ID correlation |
