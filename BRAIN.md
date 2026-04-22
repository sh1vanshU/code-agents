# Code Agents — Brain Map

> Architecture knowledge graph. Inspired by [Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).
> This is a persistent, compounding artifact — not documentation you read once, but a map you navigate.

---

## 1. System Identity

Code Agents is an AI-powered code agent platform. 13 specialist agents exposed as OpenAI-compatible endpoints. CLI-first (`code-agents chat`), server-backed (`localhost:8000`), IDE-integrated (VS Code, IntelliJ, Chrome). Agents are defined in YAML with on-demand skill loading. The system automates: review → test → build → deploy → verify → rollback.

---

## 2. Architecture Layers

```
┌─────────────────────────────────────────────────────────────────┐
│ Layer 6: IDE Extensions                                         │
│   VS Code (WebviewViewProvider) │ IntelliJ (JCEF) │ Chrome      │
├─────────────────────────────────────────────────────────────────┤
│ Layer 5: Web UI                                                  │
│   Browser chat (webui/) │ Shared webview (webview-ui/)           │
├─────────────────────────────────────────────────────────────────┤
│ Layer 4: CLI + Chat REPL                                         │
│   51 commands │ 50+ slash commands │ TUI mode │ prompt_toolkit    │
├─────────────────────────────────────────────────────────────────┤
│ Layer 3: FastAPI Server                                          │
│   /v1/chat/completions │ 17 routers │ 60+ endpoints │ SSE        │
├─────────────────────────────────────────────────────────────────┤
│ Layer 2: Agent System                                            │
│   13 agents │ 154 skills │ auto-delegation │ confidence scoring  │
├─────────────────────────────────────────────────────────────────┤
│ Layer 1: Backend Dispatcher                                      │
│   cursor (CLI/HTTP) │ claude (API) │ claude-cli (subscription)   │
├─────────────────────────────────────────────────────────────────┤
│ Layer 0: Integrations                                            │
│   Jenkins │ ArgoCD │ Jira │ Slack │ K8s │ Kibana │ Redash │ MCP  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Agent Network Graph

```
                              ┌─────────────┐
                              │  auto-pilot  │ ← orchestrator
                              │  (12 skills) │
                              └──────┬───────┘
           ┌──────────┬──────────┬───┴───┬──────────┬──────────┐
           ▼          ▼          ▼       ▼          ▼          ▼
     ┌──────────┐┌──────────┐┌────────┐┌─────────┐┌────────┐┌────────┐
     │code-writer││code-     ││code-   ││code-    ││test-   ││qa-     │
     │(12 skills)││reasoning ││reviewer││tester   ││coverage││regress.│
     │           ││(14 skill)││(7 skil)││(11 skil)││(12 ski)││(15 ski)│
     └─────┬─────┘└──────────┘└────────┘└────┬────┘└───┬────┘└────────┘
           │                                  │        │
           │ writes code    reviews ──────────┘        │
           │                tests ─────────────────────┘
           ▼
     ┌──────────┐     ┌──────────┐     ┌──────────┐
     │ git-ops  │────▶│jenkins-  │────▶│argocd-   │
     │(9 skills)│     │cicd      │     │verify    │
     └──────────┘     │(9 skills)│     │(11 skills)│
                      └──────────┘     └──────────┘
           
     ┌──────────┐     ┌──────────┐     ┌──────────┐
     │ jira-ops │     │redash-   │     │ security │
     │(12 skills│     │query     │     │(6 skills)│
     └──────────┘     │(9 skills)│     └──────────┘
                      └──────────┘

  Shared skills (_shared/): 11 workflows available to all agents
  Total: 154 skills (143 agent-specific + 11 shared)
```

### Delegation Paths


| From          | To            | When                                  |
| ------------- | ------------- | ------------------------------------- |
| auto-pilot    | code-writer   | "write code", "implement", "refactor" |
| auto-pilot    | code-reviewer | "review", "check for bugs"            |
| auto-pilot    | code-tester   | "write tests", "debug test"           |
| auto-pilot    | jenkins-cicd  | "build", "deploy"                     |
| auto-pilot    | security      | "security audit", "scan for CVE"      |
| auto-pilot    | git-ops       | "commit", "branch", "merge"           |
| auto-pilot    | jira-ops      | "create ticket", "update issue"       |
| jenkins-cicd  | argocd-verify | after deploy → verify health          |
| code-writer   | code-reviewer | after write → auto-verify (optional)  |
| code-writer   | code-tester   | after write → run tests               |
| test-coverage | code-tester   | generate tests for uncovered code     |


---

## 4. Data Flow: Chat Message

```
User types "review auth.py"
    │
    ▼
┌─ CLI/Chat REPL ─────────────────────────────────────┐
│  prompt_toolkit input → message queue → slash check   │
│  Agent routing: keywords match → "code-reviewer"      │
└──────────────────────┬────────────────────────────────┘
                       ▼
┌─ FastAPI Server ─────────────────────────────────────┐
│  POST /v1/chat/completions                            │
│  { model: "code-reviewer", messages: [...] }          │
│                                                       │
│  stream.py → build_prompt():                          │
│    system prompt (143 words)                          │
│    + skills index (7 skills listed)                   │
│    + agent memory (~/.code-agents/memory/)            │
│    + session scratchpad (/tmp state)                  │
│    + rules (global + project)                         │
│    + conversation history (context_window=5)          │
└──────────────────────┬────────────────────────────────┘
                       ▼
┌─ Backend Dispatcher ─────────────────────────────────┐
│  backend.py → dispatch(agent, prompt)                 │
│                                                       │
│  cursor:     cursor_agent_sdk.query() → cursor CLI    │
│  claude:     claude_agent_sdk.query() → Anthropic API │
│  claude-cli: subprocess → claude --print              │
└──────────────────────┬────────────────────────────────┘
                       ▼
┌─ SSE Response ───────────────────────────────────────┐
│  data: {"choices":[{"delta":{"content":"..."}}]}      │
│  data: {"choices":[{"delta":{"content":"..."}}]}      │
│  data: [DONE]                                         │
│                                                       │
│  → Chat REPL: renders markdown in terminal            │
│  → IDE Extension: renders in webview sidebar          │
│  → Web UI: renders in browser                         │
└───────────────────────────────────────────────────────┘
```

---

## 5. Data Flow: CI/CD Pipeline

```
User: "deploy auth-service to QA"
    │
    ▼
auto-pilot → [SKILL:workflow-planner]
    │
    ├─ Step 1: code-reviewer  → review latest changes
    ├─ Step 2: code-tester    → run test suite
    ├─ Step 3: git-ops        → create release branch
    ├─ Step 4: jenkins-cicd   → trigger build job
    │           │
    │           ├─ POST /jenkins/build-and-wait
    │           ├─ Poll status every 30s
    │           └─ On success → trigger deploy
    │
    ├─ Step 5: jenkins-cicd   → deploy to QA
    │           │
    │           └─ POST /jenkins/deploy (JENKINS_DEPLOY_JOB_QA)
    │
    ├─ Step 6: argocd-verify  → verify deployment
    │           │
    │           ├─ GET /argocd/apps/{app}/status
    │           ├─ GET /argocd/apps/{app}/pods
    │           ├─ GET /argocd/apps/{app}/logs
    │           └─ Health check: all pods Running, no CrashLoopBackOff
    │
    └─ Step 7: jira-ops       → update ticket status
                │
                └─ POST /jira/transition (→ "Deployed to QA")
```

---

## 6. Data Flow: IDE Extension

```
┌─ VS Code ──────────────────────────────────────────┐
│                                                     │
│  User right-clicks code → "Review with Code Agents" │
│       │                                             │
│       ▼                                             │
│  codeActions.ts → extract selection + filePath      │
│       │                                             │
│       ▼                                             │
│  ChatViewProvider.ts → injectContext(text, agent)    │
│       │                                             │
│       ▼                                             │
│  ApiClient.ts → streamChat() via Node.js http       │
│       │    POST /v1/chat/completions {stream: true}  │
│       │                                             │
│       ▼                                             │
│  postMessage({type: 'streamToken', token})           │
│       │                                             │
│       ▼                                             │
│  Webview (webview-ui/) → MessageBubble renders      │
│       │    renderMarkdown() + highlight()            │
│       │                                             │
│       ▼                                             │
│  User sees streaming response in sidebar chat       │
└─────────────────────────────────────────────────────┘

┌─ IntelliJ ─────────────────────────────────────────┐
│  Same flow but:                                     │
│  - JBCefBrowser renders the webview HTML             │
│  - JCEF fetch() calls server directly (no proxy)    │
│  - JBCefJSQuery bridges Kotlin ↔ JavaScript         │
│  - Base64-encoded JSON for injection-safe messaging  │
└─────────────────────────────────────────────────────┘
```

---

## 7. Module Dependency Map

### Core Modules


| Module                   | Purpose                                | Depends on                             |
| ------------------------ | -------------------------------------- | -------------------------------------- |
| `app.py`                 | FastAPI server, CORS, lifespan         | config.py, all routers                 |
| `config.py`              | AgentConfig, Settings, YAML loader     | env_loader.py                          |
| `backend.py`             | Dispatch to cursor/claude/claude-cli   | config.py                              |
| `stream.py`              | SSE streaming, build_prompt()          | config.py, backend.py, agent_memory.py |
| `env_loader.py`          | Two-tier env: global + per-repo        | —                                      |
| `skill_loader.py`        | On-demand [SKILL:name] loading         | config.py                              |
| `rules_loader.py`        | Global + project rules injection       | env_loader.py                          |
| `agent_memory.py`        | Persistent learnings per agent         | env_loader.py                          |
| `session_scratchpad.py`  | Per-session [REMEMBER:] state          | —                                      |
| `context_manager.py`     | Smart conversation trimming            | config.py                              |
| `knowledge_graph.py`     | AST-based project structure index      | parsers/                               |
| `confidence_scorer.py`   | Response confidence 1-5, auto-delegate | —                                      |
| `requirement_confirm.py` | Spec-before-execution gate             | —                                      |


### CLI Modules


| Module               | Purpose                                | Commands                                         |
| -------------------- | -------------------------------------- | ------------------------------------------------ |
| `cli.py`             | Main CLI, init, plugin, readme, export | init, plugin, readme, export                     |
| `cli_server.py`      | Server management                      | start, restart, shutdown, status, agents, doctor |
| `cli_git.py`         | Git operations                         | diff, branches, commit, review, pr-preview       |
| `cli_cicd.py`        | CI/CD operations                       | test, pipeline, release, coverage, qa-suite      |
| `cli_analysis.py`    | Code analysis                          | audit, security, deadcode, complexity, techdebt  |
| `cli_reports.py`     | Reports                                | standup, oncall-report, sprint-report, incident  |
| `cli_tools.py`       | Utilities                              | update, version, changelog, onboard, watchdog    |
| `cli_doctor.py`      | Diagnostics                            | doctor (env, backend, server, integrations, IDE) |
| `cli_completions.py` | Shell completions                      | completions, help                                |
| `registry.py`        | Command registry                       | — (maps command names to handlers)               |


### Routers (18)


| Router                   | Endpoints                                                    | Integration       |
| ------------------------ | ------------------------------------------------------------ | ----------------- |
| `completions.py`         | `/v1/chat/completions`, `/v1/agents/{name}/chat/completions` | OpenAI-compatible |
| `agents_list.py`         | `/v1/agents`, `/v1/models`                                   | Agent discovery   |
| `jenkins.py`             | `/jenkins/*` (7 endpoints)                                   | Jenkins REST API  |
| `argocd.py`              | `/argocd/*` (14 endpoints)                                   | ArgoCD REST API   |
| `git_ops.py`             | `/git/*` (10 endpoints)                                      | Git CLI           |
| `jira.py`                | `/jira/*` (6 endpoints)                                      | Jira REST API     |
| `k8s.py`                 | `/k8s/*` (7 endpoints)                                       | kubectl           |
| `pipeline.py`            | `/pipeline/*` (5 endpoints)                                  | State machine     |
| `testing.py`             | `/testing/*` (3 endpoints)                                   | Test runners      |
| `elasticsearch.py`       | `/elasticsearch/*` (2 endpoints)                             | Elasticsearch     |
| `kibana.py`              | `/kibana/*` (2 endpoints)                                    | Kibana            |
| `redash.py`              | `/redash/*` (4 endpoints)                                    | Redash API        |
| `slack_bot.py`           | `/slack/*` (2 endpoints)                                     | Slack Bot Bridge  |
| `telemetry.py`           | `/telemetry/*` (4 endpoints)                                 | Internal metrics  |
| `knowledge_graph.py`     | `/knowledge-graph/*` (4 endpoints)                           | AST parsers       |
| `mcp.py`                 | `/mcp/*` (5 endpoints)                                       | MCP protocol      |
| `atlassian_oauth_web.py` | `/oauth/atlassian/*` (3 endpoints)                           | OAuth 2.0         |


---

## 8. Configuration Inheritance

```
Priority (later overrides earlier):

1. Defaults (hardcoded in config.py)
   │
2. Global config (~/.code-agents/config.env)
   │  API keys, server settings, user profile
   │
3. Per-repo config (~/.code-agents/repos/{name}/config.env)
   │  Jenkins, ArgoCD, Jira, testing overrides
   │
4. Agent YAML (agents/{name}/{name}.yaml)
   │  System prompt, skills, backend/model override
   │
5. Environment variables (CODE_AGENTS_*)
   │  CODE_AGENTS_BACKEND, CODE_AGENTS_MODEL, etc.
   │
6. Per-agent env overrides (CODE_AGENTS_BACKEND_<AGENT>)
   │
7. Runtime (slash commands, chat settings)
   │  /model, /backend, /theme, /superpower
```

---

## 9. Integration Protocol Map


| Integration         | Protocol                 | Auth                           | Key Files                                              |
| ------------------- | ------------------------ | ------------------------------ | ------------------------------------------------------ |
| **Jenkins**         | REST API + polling       | Basic Auth (user + API token)  | `routers/jenkins.py`, `cicd/jenkins_client.py`         |
| **ArgoCD**          | REST API + session token | Username/password → JWT        | `routers/argocd.py`, `cicd/argocd_client.py`           |
| **Jira**            | REST API v2              | Basic Auth (email + API token) | `routers/jira.py`, `cicd/jira_client.py`               |
| **Confluence**      | REST API v2              | Same as Jira                   | `cicd/jira_client.py`                                  |
| **Slack**           | Webhook + Events API     | Bot token + signing secret     | `routers/slack_bot.py`                                 |
| **Kubernetes**      | kubectl CLI              | kubeconfig                     | `routers/k8s.py`, `cicd/k8s_client.py`                 |
| **Kibana**          | REST API                 | Basic Auth                     | `routers/kibana.py`, `cicd/kibana_client.py`           |
| **Elasticsearch**   | REST API                 | API key or Basic Auth          | `routers/elasticsearch.py`, `elasticsearch_client.py`  |
| **Redash**          | REST API                 | API key                        | `routers/redash.py`, `cicd/redash_client.py`           |
| **MCP**             | JSON-RPC over stdio/SSE  | None (local)                   | `routers/mcp.py`, `mcp_client.py`                      |
| **Git**             | CLI (subprocess)         | SSH key or HTTPS               | `routers/git_ops.py`, `cicd/git_client.py`             |
| **Atlassian OAuth** | OAuth 2.0                | Client ID + secret             | `routers/atlassian_oauth_web.py`, `atlassian_oauth.py` |


---

## 10. Skill Categories (154 total)


| Category          | Skills                                                                    | Agents              |
| ----------------- | ------------------------------------------------------------------------- | ------------------- |
| **Code Analysis** | architecture, explore, debug, deps, impact, blame, flow-trace, complexity | code-reasoning (14) |
| **Code Writing**  | implement, refactor, migrate, java-upgrade, performance, error-handling   | code-writer (12)    |
| **Code Review**   | review, security-review, style-check, pr-review                           | code-reviewer (7)   |
| **Testing**       | unit-test, integration-test, mock-strategy, flaky-hunt, tdd               | code-tester (11)    |
| **Coverage**      | coverage-analysis, coverage-boost, gap-detection, autonomous-boost        | test-coverage (12)  |
| **QA**            | regression-suite, baseline, smoke-test, e2e, performance-test             | qa-regression (15)  |
| **CI/CD**         | build, deploy, artifact, pipeline-status, rollback                        | jenkins-cicd (9)    |
| **Deployment**    | sync, verify-pods, canary, rollback, log-scan, health-check               | argocd-verify (11)  |
| **Git**           | branch, merge, conflict, release, tag, cherry-pick                        | git-ops (9)         |
| **Project Mgmt**  | create-issue, transition, sprint, acceptance, confluence                  | jira-ops (12)       |
| **Data**          | query, schema, dashboard, data-validation, migration                      | redash-query (9)    |
| **Security**      | owasp-scan, cve-audit, secrets-detect, compliance                         | security (6)        |
| **Orchestration** | workflow-planner, delegate, confidence-check, plan-execute                | auto-pilot (12)     |
| **Shared**        | standup, incident-response, deploy-checklist, tech-debt, testing-strategy | _shared (11)        |


---

## 11. Security Model

```
┌─ Permission Layers ─────────────────────────────────┐
│                                                      │
│  1. Agent YAML: permission_mode = "ask" (default)    │
│     → Agent must ask user before executing commands   │
│                                                      │
│  2. Autorun allowlist (per-agent autorun.yaml)       │
│     → Safe commands auto-execute in agentic loop      │
│     → Example: git status, curl localhost, ls         │
│                                                      │
│  3. Autorun blocklist (_shared/autorun.yaml)         │
│     → HARD BLOCK: rm, git push, DROP TABLE, kill      │
│     → Cannot be overridden by agent config            │
│                                                      │
│  4. Runtime modes:                                    │
│     → /superpower: auto-execute safe commands         │
│     → /sandbox: restrict writes to project dir        │
│     → /confirm: require spec before execution         │
│     → dry-run: CODE_AGENTS_DRY_RUN=true              │
│                                                      │
│  5. Token guard: CODE_AGENTS_MAX_SESSION_TOKENS       │
│     → Stops agentic loop when exceeded                │
│                                                      │
│  6. Rate limiting: per-user RPM + daily token budgets │
└──────────────────────────────────────────────────────┘
```

---

## 12. Extension Architecture

```
┌─ Shared Webview (webview-ui/) ───────────────────────┐
│  49KB JS │ 43KB CSS │ Vanilla TypeScript │ Vite build │
│                                                       │
│  Components: Toolbar, MessageList, MessageBubble,     │
│    ChatInput, SlashPalette, PlanTracker, ApprovalCard  │
│  Views: Chat, Welcome, Settings, History               │
│  Theme: "Terminal Noir" — 4 themes, WCAG AA, 13 agent │
│    accent colors, DM Sans + JetBrains Mono             │
│  Markdown: custom renderer + regex syntax highlighter  │
└───────────────────────┬───────────────────────────────┘
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
┌─ VS Code ────┐ ┌─ IntelliJ ───┐ ┌─ Chrome ─────┐
│ postMessage   │ │ JBCefJSQuery │ │ fetch()      │
│ ↕             │ │ ↕            │ │ ↕            │
│ Node.js http  │ │ JCEF fetch() │ │ browser API  │
│ to server     │ │ to server    │ │ to server    │
│               │ │              │ │              │
│ 10 commands   │ │ 8 actions    │ │ context menu │
│ 8 settings    │ │ settings UI  │ │ GitHub/Jira  │
│ status bar    │ │ status bar   │ │ extraction   │
└───────────────┘ └──────────────┘ └──────────────┘
```

---

## 13. File Count


| Directory              | Files   | Purpose                    |
| ---------------------- | ------- | -------------------------- |
| `code_agents/`         | ~60     | Core Python modules        |
| `code_agents/cli/`     | 13      | CLI commands + registry    |
| `code_agents/routers/` | 18      | FastAPI route handlers     |
| `code_agents/chat/`    | ~15     | Chat REPL + TUI            |
| `code_agents/cicd/`    | ~10     | Integration clients        |
| `code_agents/parsers/` | ~8      | Multi-language AST parsers |
| `code_agents/webui/`   | 3       | Browser chat UI            |
| `agents/`              | 14 dirs | 13 agents + _shared        |
| `agents/*/skills/`     | 150     | Skill workflow files       |
| `extensions/vscode/`   | 48      | VS Code extension          |
| `extensions/intellij/` | 22      | IntelliJ plugin            |
| `extensions/chrome/`   | 16      | Chrome extension           |
| `tests/`               | 96      | 3759 tests                 |
| `initiater/`           | 16      | Audit system (14 rules)    |
| **Total**              | ~450+   |                            |


---

## 14. Evolution Log


| Date          | Milestone                                                                                                                                                                                                                      |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 2026-03-31    | 92+ files changed: SDLC pipeline, MCP, roadmap                                                                                                                                                                                 |
| 2026-04-05    | 15 agents overhauled, questionnaire, SmartOrchestrator                                                                                                                                                                         |
| 2026-04-06    | Scratchpad, streaming, questionnaire, jenkins-cicd fixes                                                                                                                                                                       |
| 2026-04-07-08 | TUI, 16→13 agents, Knowledge Graph, Skills L3, export, panels                                                                                                                                                                  |
| 2026-04-08-09 | VS Code + IntelliJ extensions (80+ files), security hardening, 14 audit rules pass                                                                                                                                             |
| 2026-04-09    | 28 new modules: Platform Intelligence (12), Dev Productivity (6), Payment Domain (10), Migration (1), Observability (2). Security hardening: path traversal, SQL injection, SSRF, secret masking, atomic writes. 13 bugs fixed |


---

## 15. New Module Layers (2026-04-09)

### Architecture Decision: Layered Module Organization

New modules are organized into functional layers rather than flat `code_agents/` dumping:


| Layer                      | Modules                                                                                                                                                           | Purpose                                                                    |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| **Platform Intelligence**  | mindmap, code_review, dep_impact, agent_corrections, workspace_graph, workspace_pr, git_hooks, agent_replay, rag_context, live_tail, pair_mode, background_agent  | Deep codebase understanding, agent self-improvement, background automation |
| **Developer Productivity** | api_docs, code_translator, profiler, schema_viz, changelog, health_dashboard                                                                                      | Accelerate common workflows, reduce manual toil                            |
| **Payment Gateway Domain** | txn_flow, recon_debug, pci_scanner, idempotency_audit, state_machine_validator, acquirer_health, retry_analyzer, load_test_gen, postmortem_gen, settlement_parser | Payment-specific debugging, compliance, operational health                 |
| **Migration Tooling**      | tracing_migration                                                                                                                                                 | Assisted migration from legacy systems to modern stacks                    |
| **Observability**          | otel (OpenTelemetry), logging_config (structured JSON)                                                                                                            | Distributed tracing, metrics, consistent structured logging                |


### Cross-Cutting Patterns

- **All 28 modules follow the same integration pattern:** core module in `code_agents/` + CLI handler in `cli/` + slash command handler in `chat/` + registry entry + shell completions + test file
- **Lazy loading maintained:** All new modules use deferred imports — only loaded when their CLI command or slash command is invoked
- **Security-first:** Path traversal prevention, parameterized queries, URL validation, secret masking, and atomic file writes applied across all new I/O-touching modules
- **OpenTelemetry (`otel.py`):** Provides trace context propagation across agent delegations, so a single user request can be traced through multiple agent handoffs
- **Structured logging (`logging_config.py`):** JSON log format with request ID correlation, replacing ad-hoc `print()` and inconsistent `logging` calls

