# Changelog

All notable changes to Code Agents are documented here.

## [0.7.0] — 2026-04-09

### Added — 80 Features Mega Session
- **Security Suite (10):** OWASP scanner, encryption audit, vuln chain, input audit, rate limit audit, privacy scanner, session audit, ACL matrix, secret rotation, compliance report (PCI/SOC2/GDPR)
- **Code Intelligence (10):** code explainer, code smell, tech debt tracker, import optimizer, dead code eliminator, clone detector, naming audit, ADR generator, comment audit, type adder
- **Payment Gateway (10):** txn flow visualizer, recon debugger, PCI scanner, idempotency audit, state machine validator, acquirer health, retry analyzer, load test gen, postmortem gen, settlement parser
- **Platform Intelligence (12):** mindmap, code review, dep impact, agent corrections, workspace graph, git hooks, agent replay, RAG context, live tail, pair mode, background agents, command advisor
- **DevOps (4):** CI self-healing, headless/CI mode, batch operations, OTel migration
- **Testing (4):** mutation testing, property tests, test style matching, visual regression
- **Developer Productivity (8):** snippets, env diff, ownership, velocity, PR split, license audit, config validator, release notes
- **Enterprise (5):** PR thread agent, team KB, onboarding, browser agent, live preview
- **Frontier (7):** spec validator, screenshot-to-code, archaeology, perf proof, contract testing, self-benchmark, lang migration
- **Global Orchestrator:** full-audit with 14 scanners + 15 quality gates

### Fixed — 13 Bug Fixes
- ANSI escape codes rendering as ?[33m (patch_stdout raw=True)
- `green` UnboundLocalError in chat_commands.py
- Questionnaire horizontal layout (\r\n in raw mode)
- Arrow key echo in command panel (os.read vs sys.stdin)
- [SKILL:] tags showing in response output
- Response text indent in agent box
- Spinner hiding input prompt
- SQL injection in LIMIT clause, path traversal, SSRF, curl URL quoting

### Changed
- Version: 0.3.0 → 0.7.0
- Tests: 4925 → 8000+ (3000+ new tests)
- CLI commands: 84 → 130+
- Slash commands: 84 → 140+
- Features: 113 → 162

## [0.6.0] — 2026-04-09

### Added — API & Database Tools (Session 3/10)
- **Endpoint Generator** — `code-agents endpoint-gen` generates CRUD endpoints (routes, models, tests) for FastAPI, Express, Flask, Django
- **API Spec Sync Checker** — `code-agents api-sync` detects drift between OpenAPI/Swagger specs and code routes
- **Response Optimizer** — `code-agents response-optimize` scans for missing pagination, N+1 queries, no field selection
- **REST to gRPC Converter** — `code-agents rest-to-grpc` generates `.proto` definitions from REST endpoints
- **API Changelog Generator** — `code-agents api-changelog` diffs two spec versions, flags breaking changes
- **SQL Query Optimizer** — `code-agents query-optimize` analyzes SQL for SELECT *, missing LIMIT, wildcard LIKE, missing indexes
- **Database Schema Designer** — `code-agents schema-design` transforms entity JSON into schemas with FK, indexes, constraints
- **ORM Anti-Pattern Reviewer** — `code-agents orm-review` detects N+1, raw SQL injection, lazy loading issues
- **2 new routers** — `/api-tools/` and `/db-tools/` API endpoints
- **8 new skill files** across code-writer, pr-review, and db-ops agents
- **8 new test files** with 64+ tests

---

## [0.5.0] — 2026-04-09

### Added — Debugging & Testing Tools (Session 2/10)
- **Stack Trace Decoder** — `code-agents stack-decode` Python/Java/JS/Go stack trace parsing with local file mapping and fix suggestions
- **Log Analyzer** — `code-agents log-analyze` JSON + plain text log parsing, correlation, timeline, root cause identification
- **Environment Differ** — `code-agents env-diff` config comparison with secret masking and critical key alerts
- **Memory Leak Scanner** — `code-agents leak-scan` static analysis for unclosed resources, growing caches, listener leaks
- **Deadlock Scanner** — `code-agents deadlock-scan` concurrency hazard detection (race conditions, async issues, lock ordering)
- **Edge Case Suggester** — `code-agents edge-cases` AST-based edge case suggestion (null, empty, boundary, unicode, error)
- **Mock Builder** — `code-agents mock-build` generate mock classes with realistic return values and error scenarios
- **Test Fixer** — `code-agents test-fix` diagnose pytest failures and suggest targeted fixes
- **Integration Scaffolder** — `code-agents integration-scaffold` generate docker-compose + fixtures for 8 services
- **2 new routers** — `/debug-tools/` and `/test-tools/` API endpoints
- **9 new skill files** across debug-agent and code-tester
- **9 new test files** with 64 tests

### Added — Code Understanding & Navigation (Session 1/10)
- **Code Explainer** — `code-agents explain-code` AST-powered explanation of functions, classes, modules with edge cases, side effects, and complexity scoring
- **Usage Tracer** — `code-agents usage-trace` find all usages of any symbol across the codebase, grouped by type
- **Codebase Navigator** — `code-agents nav` semantic codebase search with natural language queries and concept expansion
- **Git Story** — `code-agents git-story` reconstruct the full history behind any line of code (blame, PR, Jira, contributors)
- **Call Chain Analyzer** — `code-agents call-chain` trace callers and callees as a visual tree with depth control
- **Code Example Finder** — `code-agents examples` find real code examples for any concept, ranked by relevance
- **Dependency Graph Visualizer** — Enhanced with Mermaid and Graphviz DOT output formats
- **MCP Server Generator** — Skill to generate complete MCP servers from REST/gRPC API specs
- **Shared Utilities** — `_ast_helpers.py`, `_git_helpers.py`, `_pattern_matchers.py` reusable across 15+ modules
- **Router** — `/code-nav/` API endpoints for all code understanding tools
- **7 new skill files** in `agents/code-reasoning/skills/`
- **8 new test files** with 74 tests

---

## [0.4.0] — 2026-04-09

### Added
- **Repo mindmap** — `code-agents mindmap` / `/mindmap` generates visual repo structure (ASCII/Mermaid/HTML)
- **AI code review** — `code-agents review` / `/review` inline annotated terminal diffs with categorized findings
- **Dependency impact scanner** — `code-agents impact` / `/dep-impact` blast radius analysis for dependency upgrades
- **Agent corrections** — `/corrections` lets agents learn from user corrections mid-session
- **Multi-repo orchestration** — `code-agents workspace` / `/workspace-cross-deps` cross-repo deps, coordinated PRs
- **Git hooks agent** — `code-agents install-hooks` AI-powered pre-commit/pre-push analysis
- **Agent replay** — `code-agents replay` / `/replay` time travel debugging with session trace recording
- **RAG context injection** — `code-agents index` builds vector store for smart context retrieval
- **Live tail mode** — `code-agents tail` / `/tail` real-time log streaming with anomaly detection
- **Pair programming mode** — `code-agents pair` / `/pair` file watcher with proactive AI suggestions
- **Background agents** — `code-agents bg` / `/bg` push tasks to background, Ctrl+F to foreground, parallel execution with macOS notifications
- **API docs generator** — `code-agents api-docs` / `/api-docs` generates OpenAPI/Markdown/HTML from API routes
- **Code translator** — `code-agents translate` / `/translate` regex-based cross-language translation
- **Performance profiler** — `code-agents profiler` / `/profile` cProfile analysis with optimization suggestions
- **Database schema visualizer** — `code-agents schema` / `/schema` ER diagrams from live DB or SQL files
- **Automated changelog** — `code-agents changelog-gen` / `/changelog` from git history + PRs
- **Code health dashboard** — `code-agents dashboard` / `/dashboard` tests, coverage, complexity, PRs in one view
- **Transaction flow visualizer** — `code-agents txn-flow` / `/txn-flow` trace transaction journey through microservices
- **Reconciliation debugger** — `code-agents recon` / `/recon` order vs settlement mismatch detection
- **PCI-DSS compliance scanner** — `code-agents pci-scan` / `/pci-scan` payment code compliance checks
- **Idempotency key auditor** — `code-agents audit-idempotency` / `/idempotency` payment endpoint safety
- **Transaction state machine validator** — `code-agents validate-states` / `/validate-states` state transition validation
- **Acquirer health monitor** — `code-agents acquirer-health` / `/acquirer-health` success rates, latency, alerts
- **Payment retry analyzer** — `code-agents retry-audit` / `/retry-audit` retry strategy audit
- **Load test generator** — `code-agents load-test` / `/load-test` k6/Locust/JMeter scenario generation
- **Incident postmortem generator** — `code-agents postmortem-gen` / `/postmortem-gen` structured postmortem builder
- **Settlement file parser** — `code-agents settlement` / `/settlement` Visa/Mastercard/UPI file parsing and validation
- **OpenTelemetry migration tool** — `code-agents migrate-tracing` / `/migrate-tracing` Jaeger/Datadog/Zipkin to OTel
- **GitHub Actions agent** — `agents/github_actions/` trigger, monitor, retry, debug workflows
- **Grafana Ops agent** — `agents/grafana_ops/` dashboards, metrics, alerts, deploy correlation
- **Terraform/IaC agent** — `agents/terraform_ops/` plan/apply/drift-detect with safety gates
- **Postgres/DB agent** — `agents/db_ops/` safe queries, schema inspection, migration generation
- **PR Review Bot agent** — `agents/pr_review/` automated PR review with inline comments
- **Debug Agent** — autonomous debugging: reproduce, trace, root cause, fix, verify
- **action_log.py** — audit trail for all agent actions
- **diff_preview.py** — inline annotated diff rendering for code review
- **skill_marketplace.py** — community skill sharing and discovery
- **voice_mode.py** / **voice_output.py** — voice input and TTS output
- **cli/cli_cost.py** — cost estimation and display
- **cli/cli_skill.py** — skill management CLI
- **cli/cli_undo.py** — undo last agent action
- **cli/cli_voice.py** — voice mode CLI commands
- **cicd/db_client.py** — PostgreSQL integration client
- **cicd/github_actions_client.py** — GitHub Actions API client
- **cicd/pr_review_client.py** — PR review API client
- **cicd/terraform_client.py** — Terraform CLI wrapper
- **routers/db.py** — PostgreSQL API endpoints
- **routers/github_actions.py** — GitHub Actions API endpoints
- **routers/pr_review.py** — PR review API endpoints
- **routers/terraform.py** — Terraform API endpoints
- 964+ new tests across 27+ new test files

### Fixed
- ANSI escape codes rendering as raw `?[33m` in chat output
- Command execution `green` UnboundLocalError + questionnaire horizontal layout
- Auto-quote curl URLs with `?` or `&` to prevent shell glob/backgrounding
- Input prompt disappearing during agent thinking/spinner
- Response text not indented inside agent response box
- Strip `[SKILL:]` tags from display + fix arrow key echo in command panel

### Security
- Direct API access — remove localhost proxy, hit real service URLs with masked auth headers

### Changed
- Agent count: 13 → 18 (6 new agents)
- CLI commands: ~45 → ~60 (16 new commands)
- Slash commands: ~30 → ~60 (28 new slash commands)
- Tests: 3759 → 4723 (964 new tests)
- Skills: 141 → 154 (13 new skills)
- Routers: 13 → 17 (4 new routers)
- Updated CLAUDE.md, AGENTS.md with all 28 new features

## [Unreleased]

### Added
- **Session scratchpad** — `session_scratchpad.py` persists discovered facts (branch, job path, image tag) to `/tmp/code-agents/<session>/state.json` across agent turns. Agents write via `[REMEMBER:key=value]` tags in responses, read via `[Session Memory]` block injected into system prompt. Distinguishes reusable facts (cached) from build results (never prevents re-build). Auto-cleanup after 1 hour. Clears on agent switch
- **Upfront questionnaire for jenkins-cicd** — ambiguous requests trigger a multi-question tabbed wizard (`[QUESTION:cicd_action]`, `[QUESTION:deploy_environment_class]`, `[QUESTION:cicd_branch]`, `[QUESTION:cicd_java_version]`). Explicit commands ("build", "deploy") skip intake. Multiple `[QUESTION:]` tags now use `ask_multiple_tabbed()` for batched input
- **Enter-to-submit questionnaire** — replaced Y/n confirmation with "Press Enter to submit · Ctrl+C to cancel" for faster flow
- **New questionnaire templates** — `cicd_action`, `cicd_branch`, `cicd_java_version`, `cicd_sub_env` for CI/CD intake
- **Documentation** — `ROADMAP.md` **Major Refactor** marked complete (Phases 1–5); the same short **Codebase refactor (Phases 1–5) — COMPLETED** paragraph appended to every other `*.md` file in the repo for consistent status (full checklist remains in `ROADMAP.md`)
- **Telemetry dashboard** — `telemetry.py` SQLite analytics (record events, get_summary, agent_usage, top_commands, errors, CSV export). Web dashboard at `http://localhost:8000/telemetry-dashboard` (dark theme, charts). `routers/telemetry.py` with 4 API endpoints: summary, agents, commands, errors. `/stats` slash command for quick terminal stats
- **Voice input** — `voice_input.py` speech-to-text (optional SpeechRecognition dep). `/voice` slash command to listen, transcribe, confirm/edit/send. Engine configurable via `CODE_AGENTS_VOICE_ENGINE` (google, whisper)
- **prompt_toolkit input** — `chat_input.py` replaces readline `input()` with `prompt_toolkit.PromptSession`. Fixed input bar at bottom, output scrolls above, dropdown autocomplete for slash commands and agent names. Falls back to `input()` if unavailable
- **Terminal layout** — `terminal_layout.py` ANSI fixed-input at bottom. `/layout on|off` slash command to toggle. `CODE_AGENTS_SIMPLE_UI` to disable
- **Endpoint runner** — `/endpoints run` executes discovered endpoints and reports results. `run_endpoints.md` skill for qa-regression. Config: `.code-agents/endpoints.example.yaml`, `.code-agents/sanity.example.yaml`
- **Web UI redesign** — quick action pills, scroll-to-bottom button, agent pill, focus glow
- **Init Quick Links** — after `code-agents init`, shows clickable URLs for Chat UI, Telemetry, Health, Docs
- **Endpoint scanner** — `endpoint_scanner.py` background scan on `code-agents init`, catalogs all API endpoints in the repo. `/endpoints` command in chat to browse discovered routes
- **Sanity checker** — `sanity_checker.py` per-repo validation rules + Kibana monitoring integration for repo health checks
- **`/endpoints` slash command** — browse all discovered API endpoints in the current repo
- **`/btw` and `/bash` commands** — completed and available in chat
- **Ctrl+C graceful interrupt** — single Ctrl+C interrupts agent response and opens user input prompt. Double Ctrl+C (within 1 second) exits `code-agents chat` entirely
- **Command validation filter** — `_is_valid_command(cmd)` in `chat_commands.py` rejects English text accidentally wrapped in ```bash blocks
- **Context-aware questionnaire suggestions** — agent infers relevant questions from the task context, with Q&A persistence across session
- **Role-calibrated agent behavior** — agents adapt tone and detail level based on `CODE_AGENTS_USER_ROLE` (Junior/Senior/Lead/Principal/Manager)
- **safe-checkout skill** — git-ops agent skill for safe branch checkout with stash/restore workflow
- **Full git operations** — checkout, stash, merge, add, commit via `/git/*` endpoints and `git_client.py`. Git-ops agent can now switch branches, stash dirty changes, merge branches, stage files, and commit code
- **Tab selector Edit option** — command approval Tab selector now has 3 options (Yes/Edit/No). Edit lets users modify the proposed command or give feedback to the agent for regeneration
- **test_git_client.py expanded** — 14 new tests for checkout, stash, merge, add, commit (24 total, up from 10)
- **MCP plugin system** — `mcp_client.py` with stdio + SSE transport, JSON-RPC, service intelligence (MCP_SERVICE_MAP, AGENT_MCP_AFFINITY, get_smart_mcp_context). `/mcp/*` router with 5 endpoints (servers, tools, call, start, stop). `/mcp` slash command in chat
- **Interactive questionnaire** — `questionnaire.py` with multiple-choice + "Other" option, 7 templates, `[QUESTION:]` tag interception for structured user input
- **User profile & designation** — `CODE_AGENTS_USER_ROLE` env var for role-based prompt tailoring (Junior/Senior/Lead/Principal/Manager)
- **Slack notifications** — `notifications.py` for webhook alerts on build/deploy/test status (`CODE_AGENTS_SLACK_WEBHOOK_URL`)
- **Rate limiter** — `rate_limiter.py` with per-user RPM + daily token budgets (`CODE_AGENTS_RATE_LIMIT_RPM`, `CODE_AGENTS_RATE_LIMIT_TPD`)
- **`/export` slash command** — export conversation to markdown file
- **`/mcp` slash command** — list configured MCP servers and tools
- **MCP config template** — `.code-agents/mcp.example.yaml` for MCP server configuration
- **test_questionnaire.py** — 18 new tests for interactive Q&A system
- **Jira/Confluence agent** — `jira-ops` agent with 4 skills for issue management, transitions, search, and Confluence page operations (`/jira/*` endpoints)
- **Kibana log viewer** — `/kibana/*` endpoints for log search, filtering, and tail across services
- **Plan mode** — `/plan` command to create, approve, status, edit, reject execution plans before running (`plan_manager.py`)
- **Superpower mode** — `/superpower` auto-executes all commands except blocklisted ones for maximum autonomy
- **SDLC pipeline** — 13-step full-SDLC orchestration skill covering the complete software development lifecycle
- **System analysis + design review skills** — architecture analysis and design review workflows
- **API testing skills** — `api-testing` and `negative-testing` skills for comprehensive API validation
- **Smart test failure classification** — auto-classifies failures as code bug, infra issue, flaky test, or env problem
- **Impact analysis skill** — assess change impact across codebase before implementation
- **Local build support** — `CODE_AGENTS_BUILD_CMD` env var for running local builds without Jenkins
- Token tracking: per message/session/day/month/year with CSV export (`~/.code-agents/token_usage.csv`)
- `/tokens` command in chat — view usage breakdown by session, daily, monthly, yearly, backend/model
- Auto-fill `BUILD_VERSION` placeholder from previous build output
- Vertical Tab selector for command approval
- Safe Ctrl+O collapse/expand for long responses
- Session summary on exit with token counts and cost
- **On-demand skill loading** — lean system prompts (~500 tokens) with `[SKILL:name]` tags for autonomous skill loading
- **Agent-specific colors** — each agent gets a unique terminal color for welcome box and response labels
- **Cross-agent skill sharing** — agents can use other agents' skills via `[SKILL:agent:skill]` syntax (e.g. auto-pilot uses jenkins-cicd:build)
- **Version bump CLI** — `code-agents version-bump <major|minor|patch>` with `__version__.py` as single source of truth
- **Agent skills system** — 53 reusable workflows across 14 agents, dual invocation: user (`/<agent>:<skill>`) + agent autonomous (`[SKILL:name]`)
- **Agent subfolders** — each agent has its own directory with YAML, README.md, and skills/
- **Backend/model env var placeholders** — `${CODE_AGENTS_BACKEND:cursor}` and `${CODE_AGENTS_MODEL:Composer 2 Fast}` in all agent YAMLs
- `/skills` command in chat — list available skills for current agent or all agents
- **Auto-run safe commands** — read-only curls and git commands auto-execute in agentic loop (POST/mutations still ask)
- **Agentic loop** — recursive up to 10 rounds, agent chains commands without user typing "ok"
- **Per-message token display** — `✻ Response took 3s · request: 1,234 tokens, response: 567 tokens`
- **Spinner for agent feedback** — spinner+timer while agent processes fed-back command output
- **User nickname** — `CODE_AGENTS_NICKNAME` replaces "you" in REPL prompt, asked on first chat
- **Agent name UPPERCASE** — bold uppercase agent labels in responses (`JENKINS-CICD ›`)
- **Per-agent token summary** — shows token breakdown when switching agents with `/agent`
- **`/setup` slash command** — configure integrations (argocd, jenkins, redash) from inside chat
- **Web UI** — browser-based chat at `/ui` with dark theme, SSE streaming, agent colors, markdown rendering
- **Multi-model routing** — `CODE_AGENTS_MODEL_<AGENT>` and `CODE_AGENTS_BACKEND_<AGENT>` per-agent overrides
- **Agent memory** — persistent learnings at `~/.code-agents/memory/<agent>.md`, `/memory` slash command
- **Agent chaining** — `[DELEGATE:agent-name]` for auto-delegation between agents
- **Dry-run mode** — `CODE_AGENTS_DRY_RUN=true` shows commands without executing
- **Custom themes** — `CODE_AGENTS_THEME=dark|light|minimal` for terminal color schemes
- **Safety guards** — `CODE_AGENTS_AUTO_RUN` toggle, auto-run audit log, configurable max loops, cost guard
- Crash logging to `~/.code-agents/crash.log` for debugging terminal crashes
- Async connection validator for backend health checks (cursor/claude/claude-cli)
- `gemini.md` — Gemini IDE context file
- `RELEASE-NOTES.md` — release notes for version tracking
- `ROADMAP.md` — future ideas and planned implementations

### Added (cont.)
- **`/btw` side-messages** — send context to the agent mid-execution without interrupting the current task
- **`/bash` direct shell** — execute shell commands directly from chat without agent intermediation
- **`/stats` quick stats** — terminal summary of session usage, agent activity, and command counts
- **`/export` conversation export** — export conversation to markdown file
- **Init flags (14 profiles)** — `--profile --backend --server --jenkins --argocd --jira --kibana --redash --elastic --atlassian --testing --build --k8s --notifications` for targeted `code-agents init` configuration

### Changed
- **Project restructure** — code_agents/ split into 4 subpackages: `cli/`, `chat/`, `setup/`, `cicd/`
- **Lean system prompts** — all 14 agent YAMLs rewritten from ~2500 to ~500 tokens (workflows moved to skills)
- **Centralized URL** — `CODE_AGENTS_PUBLIC_BASE_URL` defaults to `https://code-agents.example.com:8000`, falls back to `http://127.0.0.1:{PORT}`
- Jenkins CI/CD agent: git pre-check → branch/java selection → build → deploy → verify workflow
- Version bumped to 0.3.0 with session scratchpad and upfront questionnaire
- 14 agents, 25 CLI commands, ~30 slash commands, 344 tests, 71 skills, 15 routers

### Fixed
- Terminal crash from raw mode corruption in Ctrl+O and Tab selector (setcbreak instead of setraw)
- Build version extraction for Docker multi-stage builds
- Output box uses full terminal width (no 100-char cap)
- Stale jenkins-build/jenkins-deploy references removed
- Backward-compat stubs removed — clean package imports only

## [0.2.0] — 2026-03-25

### Added
- **Auto-Pilot agent** — autonomous orchestrator that delegates to sub-agents
- **Jenkins CI/CD agent** — merged build + deploy into single agent
- **QA Regression agent** — eliminate manual testing
- **Claude CLI backend** — use Claude subscription, no API key needed
- **Agent rules system** — global + project rules, auto-refresh mid-chat
- **Chat history persistence** — auto-save sessions, resume with `/resume`
- **Command execution engine** — detect ```bash blocks, run with approval
- **Agentic loop** — command output fed back to agent automatically
- **Shell tab-completion** — `code-agents` CLI + in-chat slash commands
- **Agent welcome messages** — red bordered box with capabilities + examples
- **Jenkins job discovery** — list jobs, fetch parameters, build-and-wait
- **Code-agents update** — pull latest + reinstall dependencies
- **Makefile** — 40+ targets for all operations
- 13 agents, 23 CLI commands, 247 tests

### Changed
- Centralized .env config: global (`~/.code-agents/config.env`) + per-repo (`.env.code-agents`)
- Rewritten core agent system prompts (senior engineer quality)
- Claude Code-style REPL: spinner, timer, markdown rendering, Tab selector
- Split god files: chat.py, cli.py, setup.py into focused modules

### Fixed
- 10 bugs found in code review (placeholder saving, Jenkins path stripping, race conditions, shallow copies)
- Workspace trust: auto-trust via `--trust` flag, removed slow pre-flight check
- Terminal crash: signal-safe raw mode with guaranteed restore

## [0.1.0] — 2026-03-20

### Added
- Initial release: 12 agents, FastAPI server, OpenAI-compatible API
- Interactive chat REPL with streaming
- Jenkins CI/CD integration (build + deploy)
- ArgoCD deployment verification
- Git operations agent
- Redash SQL query agent
- Pipeline orchestrator (6-step CI/CD)
- Open WebUI integration
