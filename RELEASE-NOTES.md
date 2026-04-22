# Release Notes — Code Agents

## v0.7.0 — 2026-04-11

### Highlights

**Module Reorganization** — 174 flat files in `code_agents/` restructured into 12 thematic subdirectories: `core/`, `agent_system/`, `security/`, `reviews/`, `testing/`, `observability/`, `git_ops/`, `knowledge/`, `api/`, `devops/`, `ui/`, `domain/`. All 819 internal imports updated. Backward-compatible re-exports preserved in `__init__.py` stubs.

**TypeScript Terminal Client** — Full 10-phase implementation of a TypeScript/Ink/oclif terminal client in `terminal/`. Two-process architecture: Python FastAPI server stays as the headless engine, TS client consumes the OpenAI-compatible HTTP/SSE API. 54 source files, 79 tests. Features: React-based streaming UI, slash command system, session persistence interoperable with Python, oclif CLI with ~50 commands.

**71 New Developer Productivity Tools (Sessions 4-10)** — Massive expansion across code quality, security, testing, knowledge, observability, and DevOps. Every tool ships with CLI command, chat slash command, and tests. Examples: mutation testing, contract testing, property tests, visual regression, dead code elimination, clone detection, naming audit, encryption audit, vulnerability chain analysis, privacy scanner, compliance reports, architecture reviews, performance proofs, ADR generation, code archaeology, team knowledge base, onboarding agent.

**Integration Health Checks** — Credential validation + live connectivity checks for all 7 integrations (Jenkins, ArgoCD, Jira, Kibana, Grafana, Elasticsearch, Redash). Wired into `code-agents doctor` and `code-agents env-health`.

**Security Hardening** — 9 security fixes in the TypeScript terminal: input sanitization, CSP headers, rate limiting, dependency audit, secure session storage, XSS prevention, path traversal guards, command injection prevention, secure defaults.

**OTel Span Wiring** — OpenTelemetry spans added to `backend.py`, `stream.py`, `skill_loader.py`, and all router handlers. Distributed tracing across agent calls, skill loading, and SSE streaming.

**600+ New Tests** — Test suite expanded significantly with 611 tests covering the 71 new tools plus 79 TypeScript terminal tests. Total test count across Python and TS exceeds 5300.

### Module Reorganization (12 Subdirectories)

| Directory | Purpose | Module Count |
|-----------|---------|--------------|
| `core/` | App, backend, config, env, models, stream, logging, rate limiting | 17 |
| `agent_system/` | Memory, replay, corrections, skills, rules, orchestrator, scratchpad | 19 |
| `security/` | OWASP, PCI, encryption, ACL, compliance, privacy, secrets, vulns | 18 |
| `reviews/` | Code review, smell detection, dead code, imports, naming, tech debt | 23 |
| `testing/` | Mutation, contract, property, visual regression, benchmarks, specs | 19 |
| `observability/` | OTel, profiler, health dashboard, live tail, log analysis, tracing | 25 |
| `git_ops/` | Changelog, PR describe/split, hooks, blame, conflict resolver | 16 |
| `knowledge/` | Knowledge graph, RAG, code explainer, translator, onboarding, QA | 33 |
| `api/` | API docs, schema viz, endpoint generator, ORM reviewer | 13 |
| `devops/` | Background agents, batch ops, CI self-heal, config validator, env diff | 18 |
| `ui/` | Mindmap, voice, browser agent, screenshot-to-code, live preview | 11 |
| `domain/` | Payment tools, pair mode, sprint dashboard, dep impact, incidents | 28 |

### New Tools (Sessions 4-10)

**Security Tools**: OWASP scanner, encryption audit, vulnerability chain analysis, input validation audit, rate limit audit, privacy scanner, compliance report generator, secret rotation planner, ACL matrix builder, session audit.

**Code Quality Tools**: Clone detector, naming audit, code smell detector, dead code eliminator, import optimizer, type adder, comment audit, architecture reviewer, style matcher, pattern suggester.

**Testing Tools**: Mutation testing, contract testing, property-based tests, visual regression testing, test style enforcer, benchmark regression tracker, edge case suggester, test gap finder, spec validator, self-benchmarking.

**Knowledge Tools**: Code archaeology, code explainer, ADR generator, team knowledge base, onboarding agent, code ownership tracker, snippet library, design doc generator, teach mode, pair replay coach.

**Observability Tools**: Log analyzer, incident replay, leak finder, deadlock detector, cognitive monitor, stack decoder, NL monitoring query builder, auto-observability instrumenter, call chain analyzer.

**DevOps Tools**: Dockerfile optimizer, Helm debugger, K8s manifest generator, self-tuning CI, env cloner, outage topology mapper, sandbox provisioner, conversational deploy.

**Git Tools**: PR split, release notes generator, semantic merge, conflict resolver, cherry-pick advisor, commit splitter, git story narrator, branch cleanup, blame investigator.

### Logging

- **Phase 3**: Loggers added to 128 modules with consistent `code_agents.<subdir>.<module>` naming
- **Phase 5**: OTel spans wired into backend, stream, and skill_loader

### Bug Fixes

- Questionnaire horizontal alignment fix
- Deploy environment variable follow-up
- 4 pre-existing test_backend test failures fixed
- Background agent detail view layout (Claude Code style)

---

## v0.4.0 — 2026-04-09

### Highlights

**28 New Platform Features** — Massive expansion across platform intelligence, developer productivity, and payment gateway tooling. Every feature ships with both a CLI command and a chat slash command.

**6 New Agents** — GitHub Actions, Grafana Ops, Terraform/IaC, Postgres/DB, PR Review Bot, and Debug Agent. Total: 18 agents (19 subfolders including `_shared`).

**964+ New Tests** — Test suite grew from 3759 to 4723 tests across 190+ test files.

### Platform Intelligence
- **Repo Mindmap** (`mindmap` / `/mindmap`) — Visual repo structure in ASCII, Mermaid, or HTML
- **AI Code Review** (`review` / `/review`) — Inline annotated terminal diffs with categorized findings
- **Dependency Impact Scanner** (`impact` / `/dep-impact`) — Blast radius analysis for dependency upgrades
- **Agent Corrections** (`/corrections`) — Agents learn from user corrections mid-session
- **Multi-Repo Orchestration** (`workspace` / `/workspace-cross-deps`) — Cross-repo deps, coordinated PRs
- **Git Hooks Agent** (`install-hooks`) — AI-powered pre-commit and pre-push analysis
- **Agent Replay** (`replay` / `/replay`) — Time travel debugging with session trace recording
- **RAG Context Injection** (`index`) — Vector store for smart context retrieval
- **Live Tail Mode** (`tail` / `/tail`) — Real-time log streaming with anomaly detection
- **Pair Programming Mode** (`pair` / `/pair`) — File watcher with proactive AI suggestions
- **Background Agents** (`bg` / `/bg`) — Push tasks to background, Ctrl+F to foreground, parallel execution

### Developer Productivity
- **API Docs Generator** (`api-docs` / `/api-docs`) — OpenAPI/Markdown/HTML from API routes
- **Code Translator** (`translate` / `/translate`) — Cross-language translation (regex-based pairs)
- **Performance Profiler** (`profiler` / `/profile`) — cProfile analysis with optimization suggestions
- **Database Schema Visualizer** (`schema` / `/schema`) — ER diagrams from live DB or SQL files
- **Automated Changelog** (`changelog-gen` / `/changelog`) — Changelog from git history + PRs
- **Code Health Dashboard** (`dashboard` / `/dashboard`) — Tests, coverage, complexity, PRs in one view

### Payment Gateway Tools
- **Transaction Flow Visualizer** (`txn-flow` / `/txn-flow`) — Trace transaction journey through microservices
- **Reconciliation Debugger** (`recon` / `/recon`) — Order vs settlement mismatch detection
- **PCI-DSS Compliance Scanner** (`pci-scan` / `/pci-scan`) — Payment code compliance checks
- **Idempotency Key Auditor** (`audit-idempotency` / `/idempotency`) — Payment endpoint safety
- **State Machine Validator** (`validate-states` / `/validate-states`) — State transition validation
- **Acquirer Health Monitor** (`acquirer-health` / `/acquirer-health`) — Success rates, latency, alerts
- **Payment Retry Analyzer** (`retry-audit` / `/retry-audit`) — Retry strategy audit
- **Load Test Generator** (`load-test` / `/load-test`) — k6/Locust/JMeter scenario generation
- **Postmortem Generator** (`postmortem-gen` / `/postmortem-gen`) — Incident postmortem builder
- **Settlement Parser** (`settlement` / `/settlement`) — Visa/Mastercard/UPI file parsing

### Migration
- **OpenTelemetry Migration** (`migrate-tracing` / `/migrate-tracing`) — Jaeger/Datadog/Zipkin to OTel

### New Agents
- `github-actions` — Trigger, monitor, retry, debug GitHub Actions workflows
- `grafana-ops` — Search dashboards, query metrics, investigate alerts
- `terraform-ops` — Terraform plan/apply/drift-detect with safety gates
- `db-ops` — PostgreSQL safe queries, schema inspection, migration generation
- `pr-review` — Automated PR review with inline comments
- `debug-agent` — Autonomous debugging: reproduce, trace, root cause, fix, verify

### New Modules
- `action_log.py` — Audit trail for agent actions
- `diff_preview.py` — Inline annotated diff rendering
- `skill_marketplace.py` — Community skill sharing
- `voice_mode.py` / `voice_output.py` — Voice input/output
- `cli/cli_cost.py` — Cost estimation and display
- `cli/cli_skill.py` — Skill management CLI
- `cli/cli_undo.py` — Undo last agent action
- `cli/cli_voice.py` — Voice mode CLI
- `cicd/db_client.py` — PostgreSQL integration client
- `cicd/github_actions_client.py` — GitHub Actions API client
- `cicd/pr_review_client.py` — PR review API client
- `cicd/terraform_client.py` — Terraform CLI wrapper
- `routers/db.py`, `routers/github_actions.py`, `routers/pr_review.py`, `routers/terraform.py` — New API routers

### Bug Fixes
- ANSI escape codes rendering as raw `?[33m` in chat output
- Command execution `green` UnboundLocalError + questionnaire horizontal layout
- Auto-quote curl URLs with `?` or `&` to prevent shell glob/backgrounding
- Input prompt disappearing during agent thinking/spinner
- Response text not indented inside agent response box
- Strip `[SKILL:]` tags from display + fix arrow key echo in command panel

### Security
- Direct API access — remove localhost proxy, hit real service URLs with masked auth

---

## v0.3.0 — 2026-04-06

### Highlights

**Session Scratchpad** — Agents persist discovered facts (branch, job path, image tag) to `/tmp` via `[REMEMBER:key=value]` tags. Injected as `[Session Memory]` block on every turn. Saves ~3 API calls per build flow. Reusable facts cached; build results stored for deploy reference but never prevent re-builds. 1-hour TTL, clears on agent switch.

**Upfront Questionnaire** — Jenkins-CICD agent asks all relevant questions at once for ambiguous requests via a tabbed wizard. Explicit commands ("build", "deploy to qa4") skip intake and act directly.

**Enter-to-Submit** — Questionnaire confirmation replaced with "Press Enter to submit · Ctrl+C to cancel" for faster flow.

### New Modules
- `session_scratchpad.py` — per-session `/tmp` key-value store with `[REMEMBER:]` tag capture
- `test_session_scratchpad.py` — 29 tests

### Changes
- Jenkins-CICD: session memory instructions, intake questionnaire for ambiguous requests
- Skills `build.md` / `deploy.md`: check `[Session Memory]`, skip known steps, `[REMEMBER:]` at discovery points
- Questionnaire: 4 new CI/CD templates, multiple `[QUESTION:]` tags use tabbed wizard
- `chat_response.py`: capture `[REMEMBER:]` tags, batch `[QUESTION:]` into tabbed wizard
- `chat.py`: inject scratchpad into system prompt, stale cleanup on startup
- `chat_slash_agents.py`: clear scratchpad on `/agent` switch

---

## v0.2.0 — 2026-03-25

### Highlights

**Auto-Pilot Agent** — A fully autonomous orchestrator that delegates to sub-agents (code-writer, jenkins-cicd, argocd-verify) and runs complete workflows without manual intervention.

**Claude CLI Backend** — Use your Claude Pro/Max subscription directly. No API key needed. Set `CODE_AGENTS_BACKEND=claude-cli` and go.

**Agent Rules System** — Two-tier rules (global + per-project) that inject context into agent system prompts. Auto-refresh on every message. Manage via `code-agents rules` CLI or `/rules` in chat.

**Interactive Chat Overhaul** — Claude Code-style REPL with spinner + timer, vertical Tab selector for command approval, Ctrl+O collapse/expand for long responses, auto-collapse after 25 lines, session persistence with `/resume`.

**Token Tracking** — Per message/session/day/month/year tracking with CSV export. `/tokens` command shows usage breakdown by backend and model.

### New Agents
- **auto-pilot** — Autonomous orchestrator, delegates to sub-agents
- **jenkins-cicd** — Merged build + deploy into single agent (replaces jenkins-build + jenkins-deploy)
- **qa-regression** — Full regression testing, eliminates manual QA

### New CLI Commands
- `code-agents rules` — Manage agent rules (list/create/edit/delete)
- `code-agents sessions` — List saved chat sessions
- `code-agents update` — Pull latest + reinstall dependencies
- `code-agents restart` — Restart server (shutdown + start)
- `code-agents completions --install` — Shell tab-completion for zsh/bash

### New Chat Features
- Inline agent delegation: `/<agent> <prompt>` for one-shot delegation
- Tab-completion for slash commands and agent names
- `/tokens` — Token usage breakdown (session, daily, monthly, yearly)
- `/exec <cmd>` — Run command and feed output to agent
- `/history` + `/resume` — Session persistence
- Agent welcome messages in red bordered box with capabilities + examples
- Auto-fill `BUILD_VERSION` from previous build output
- Trusted command auto-approval (save to rules)

### Backend Improvements
- 3 backends: cursor-agent-sdk, claude-agent-sdk, claude CLI (subscription)
- Centralized .env config: global (`~/.code-agents/config.env`) + per-repo (`.env.code-agents`)
- Jenkins job discovery with parameter introspection
- Build-and-wait with automatic version extraction (7 regex patterns)
- Async connection validator for backend health checks

### Bug Fixes
- Terminal crash from raw mode corruption in Ctrl+O and Tab selector
- Build version extraction for Docker multi-stage builds
- Output box uses full terminal width (no 100-char cap)
- Stale jenkins-build/jenkins-deploy references removed
- Shallow copy mutation leaks in backend.py and stream.py
- Race condition in rules file read/write (now uses fcntl locking)
- Chat startup latency reduced (removed slow workspace trust check)

---

## v0.1.0 — 2026-03-20

### Highlights

**Initial Release** — 12 agents, FastAPI server, OpenAI-compatible API endpoints.

### Features
- Interactive chat REPL with streaming
- Jenkins CI/CD integration (build + deploy)
- ArgoCD deployment verification
- Git operations agent
- Redash SQL query agent
- Pipeline orchestrator (6-step CI/CD)
- Open WebUI integration
- Agent router for automatic delegation


