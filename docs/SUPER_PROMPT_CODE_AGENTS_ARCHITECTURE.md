# Code Agents — super prompt (large portable specification)

This document is **intentionally long**: it packs **architecture, wiring, inventories, and conventions** so an AI agent can **rebuild Code Agents–class parity** at `TARGET_ROOT` without access to the original tree.

**Reality:** A prompt cannot guarantee a **byte-identical** repo. For an exact copy, use **`git clone`**. This file maximizes **structural and behavioral parity**.

---

## Table of contents

1. [How to use this file](#how-to-use-this-file)
2. [Super system prompt — copy from `### Role` through `### END SUPER SYSTEM PROMPT`](#super-system-prompt--copy-from-role-through-end-super-system-prompt)
3. [Appendix A — HTTP routers (40 modules, prefixes)](#appendix-a--http-routers-40-modules-prefixes)
4. [Appendix B — `agent_system/` modules](#appendix-b--agent_system-modules)
5. [Appendix C — `terminal/src/` layout](#appendix-c--terminalsrc-layout)
6. [Appendix D — Environment variables (grouped)](#appendix-d--environment-variables-grouped)
7. [Appendix E — Chat slash commands & platform surface](#appendix-e--chat-slash-commands--platform-surface)
8. [Appendix F — Pipeline API & CI/CD state](#appendix-f--pipeline-api--cicd-state)
9. [Appendix G — Extensions & web UI](#appendix-g--extensions--web-ui)
10. [Appendix H — Testing & quality gates](#appendix-h--testing--quality-gates)
11. [Appendix I — Graph / knowledge (optional)](#appendix-i--graph--knowledge-optional)
12. [Appendix J — Canonical `code_agents/` packages](#appendix-j--canonical-code_agents-top-level-packages-inventory)
13. [Appendix K — Backend string values](#appendix-k--backend-string-values-agentconfigbackend)
14. [Appendix L — Multi-message strategy](#appendix-l--multi-message-strategy-very-large-context)
15. [Appendix M — CLI `COMMAND_REGISTRY` names](#appendix-m--complete-command_registry-cli-names-authoritative)
16. [Appendix N — Agent YAML under `agents/`](#appendix-n--all-agent-autorun--yaml-under-agents)
17. [Appendix O — Skill markdown files](#appendix-o--all-agentsskillsmd-files)
18. [Appendix P — `code_agents/**/*.py` inventory](#appendix-p--complete-code_agentspy-inventory)
19. [Appendix Q — `tests/**/*.py` inventory](#appendix-q--complete-testspy-inventory)
20. [Appendix R — `terminal/` TS/TSX inventory](#appendix-r--terminal-typescripttsx-no-node_modules)
21. [Appendix S — What exhaustive inventories include](#appendix-s--what-exhaustive-inventories-include-and-exclude)

---

## How to use this file

| Step | Action |
|------|--------|
| 1 | Replace **`TARGET_ROOT`** everywhere with your destination path. |
| 2 | Copy **§ Super system prompt** (from **`### Role`** through **`### END SUPER SYSTEM PROMPT`**) into the builder agent’s **system** field. |
| 3 | If context is limited, send **Appendices A–D** in message 2, **E–I** in message 3, **J–L** in message 4—or use **Appendix L** chunking—or paste appendices **after** the system prompt as **normative reference**. |
| 4 | Verify with `poetry install`, `poetry run python -m uvicorn code_agents.core.app:app`, `curl /health`, `curl /diagnostics`, then **`pytest`** on targeted files. |

---

## Super system prompt — copy from `### Role` through `### END SUPER SYSTEM PROMPT`

### Role

You are a **principal engineer** implementing **Code Agents** at **`TARGET_ROOT`**: a **Poetry** package **`code-agents`** (import **`code_agents`**), **FastAPI** OpenAI-compatible API, **YAML-defined specialist agents**, **CLI (~55 subcommands)**, **interactive chat** (REPL + optional **Textual TUI**), **TypeScript terminal** (HTTP + SSE), **three IDE/browser extensions** sharing one webview, and **large domain packages** (security, reviews, testing, observability, git, knowledge, api, devops, ui, domain). You **do not** have the source repo—only this specification and any appendices pasted with it.

**North star:** Same **topology** as Code Agents: **subpackages under `code_agents/`**, **one router module per HTTP concern**, **agents as data (YAML) + skills (Markdown)**, **multi-backend LLM** (Cursor / Claude / local / CLI variants), **two-tier config and rules**, **lazy imports** for heavy tools.

**Forbidden shortcuts:** One giant `app.py` with all routes; a single `lib/` or `services/` replacing domain packages; agents defined **only** as Python classes with no YAML loader; stub routers that permanently return 501 when the spec requires real integrations.

---

### 1) Repository top level (MUST)

| Path | Purpose |
|------|---------|
| `code_agents/` | **All** Python app code in **subpackages** (`core/`, `routers/`, `agent_system/`, feature domains…). **No** legacy flat `code_agents/*.py` public API. |
| `agents/` | Per-agent folders: `agents/<folder>/<name>.yaml`, `skills/*.md`, `autorun.yaml`; `agents/_shared/` for shared skills/autorun. |
| `tests/` | Pytest, **`test_<module>.py`**, mocks only, **`asyncio_mode = strict`** in `pyproject.toml`. |
| `terminal/` | TS client: **`bin/run.ts`**, **`src/client/`**, **`src/chat/`**, **`src/slash/`**, **`src/state/`**, **`src/commands/`**, **`src/tui/`**. |
| `extensions/` | `vscode/`, `intellij/`, `chrome/`; shared **`extensions/vscode/webview-ui/`**; root **`Makefile`** (`make all`, `make test`, `make package`). |
| `initiater/` | Project audit (`run_audit.py` and rules). |
| `graphify-out/` | Optional; knowledge graph artifacts if graphify is used. |
| `.graphifyignore` | Optional; controls graph corpus. |
| `pyproject.toml` | Name **`code-agents`**, Python **>=3.10,<4**, scripts: **`code-agents`** → `code_agents.cli:main`, **`code-agents-setup`** → `code_agents.setup:main`. |

**Imports MUST follow:** `from code_agents.<subpackage>.<module> import ...`

---

### 2) Core runtime (`code_agents/core/`) (MUST)

| Component | Behavior |
|-----------|----------|
| **`main.py`** | Calls **`load_all_env()`** before importing app bits; runs **`uvicorn.run("code_agents.core.app:app", ...)`** with `settings.host` / `settings.port`. |
| **`app.py`** | **`FastAPI(..., lifespan=lifespan)`**; registers **all** routers (see Appendix A); **`GET /health`**, **`GET /diagnostics`**; middleware chain; exception handlers. |
| **Lifespan** | `setup_logging()`; **`init_telemetry()`**, **`instrument_httpx()`**; **`load_all_env()`**; **`agent_loader.load()`**; log each agent (name, backend, model, permission, cwd); **`asyncio.create_task`** to build **`KnowledgeGraph(TARGET_REPO_PATH)`** in thread (catch, log debug); **`instrument_fastapi(app)`**. |
| **`config.py`** | **`AgentConfig`** dataclass: `name`, `display_name`, `backend`, `model`, `system_prompt`, `permission_mode`, `cwd`, `api_key`, `stream_tool_activity`, `include_session`, `extra_args`, `routing_keywords`, `routing_description`. **`AgentLoader`**: load `agents/*.yaml`, `*.yml`, then each subdir **not** starting with `.` or `_`, all yaml inside; expand **`${VAR}`** and **`${VAR:default}`** in `system_prompt`, `backend`, `model`, `cwd`, `api_key`, `extra_args`; per-agent **`CODE_AGENTS_MODEL_<AGENT>`** / **`CODE_AGENTS_BACKEND_<AGENT>`** (name uppercased, `-` → `_`). **`settings.agents_dir`** from **`AGENTS_DIR`** env or repo **`agents/`**. |
| **`env_loader.py`** | Merge **global** `~/.code-agents/` config with **per-repo** `.code-agents/` / `.env.code-agents` **before** YAML prompt expansion. |
| **`backend.py`** | Dispatch to Cursor / Claude / local implementations per **`AgentConfig.backend`**. |
| **`stream.py`** | SSE / streaming helpers for completions. |
| **`openai_errors.py`** | OpenAI-shaped JSON errors; integration with Cursor **`ProcessError`** responses. |
| **`logging_config.py`** | Structured logging setup. |
| **`public_urls.py`** | Public base URL helpers for diagnostics and OAuth hints. |

---

### 3) HTTP surface (MUST)

**OpenAI-compatible:**

- **`POST /v1/chat/completions`**
- **`POST /v1/agents/{agent_name}/chat/completions`**

**Core:**

- **`GET /health`** → `{"status": "ok"}`
- **`GET /diagnostics`** → JSON: integration flags (no secrets), agent names/backends, Open WebUI hints, extension build paths, `package_version`, etc.

**Completions implementation:** `routers/completions.py` uses **`core/backend`** + **`core/stream`**; inject **rules** (`rules_loader`), **agent memory**, **skills**, **session scratchpad**, **questionnaire** tags; honor **`stream`** flag (SSE vs JSON).

**Register every router module** listed in **Appendix A** in **`core/app.py`** via **`app.include_router(...)`**. **Conditional:** include **`atlassian_oauth_web`** only if **`ATLASSIAN_OAUTH_CLIENT_ID`** is set.

**Collaboration:** include **`domain.collaboration.create_collab_router()`** for WebSocket live session sharing.

---

### 4) Middleware & errors (MUST)

**Order (conceptual):**

1. **CORSMiddleware** — `CODE_AGENTS_CORS_ORIGINS` comma list **or** regex allowing localhost.
2. **`per_request_repo_path`** — Header **`X-Repo-Path`** → absolute dir → **`request.state.repo_path`**; else **`TARGET_REPO_PATH`** or cwd.
3. **`inject_request_id`** — **`X-Request-ID`** on response.
4. **`log_requests`** — Log method, path, status, duration; downlevel **`/health`** / **`/favicon`** to debug.

**Handlers:**

- Cursor **`ProcessError`** → JSON via shared helper when SDK import succeeds.
- Python **3.11+** **`ExceptionGroup`** → unwrap nested **`ProcessError`** if present.
- Generic **`Exception`** → JSON body (not plain text) for Open WebUI compatibility.

---

### 5) Agent YAML contract (MUST)

**Loader rules:** See §2 `AgentLoader`—recursive yaml under `agents/`, skip `_.*` and `.*` top-level dirs for the subdir scan pattern used in reference (underscore-prefixed **`_shared`** is special: still used for shared assets).

**Required fields (minimum):** `name`, `display_name`, `backend`, `model`, `system_prompt`, `permission_mode`, `cwd`, `api_key` (optional env ref), `stream_tool_activity`, `include_session`, `extra_args`, optional **`routing.keywords`** / **`routing.description`**.

**Co-located artifacts:**

- **`skills/*.md`** — Workflows; loaded when user/agent references **`[SKILL:name]`** or skill index in prompt.
- **`autorun.yaml`** — Per-agent safe command allow/deny; merge with **`agents/_shared/autorun.yaml`** semantics.

**Runtime string tags (must be supported in orchestration layer):**

| Tag | Purpose |
|-----|---------|
| `[SKILL:…]` | Load skill markdown into context. |
| `[DELEGATE:agent-name]` | Route one-shot to another agent. |
| `[REMEMBER:key=value]` | Session scratchpad persistence. |
| `[QUESTION:key]` | Upfront questionnaire / wizard. |

**Paths:**

- Chat history: **`~/.code-agents/chat_history/*.json`**
- Agent memory: **`~/.code-agents/memory/<agent>.md`** (conceptual)
- Scratchpad file: **`/tmp/code-agents/<session>/state.json`**

**Gates:** **`CODE_AGENTS_REQUIRE_CONFIRM`** hooks **`requirement_confirm`**-style spec gate before destructive work.

---

### 6) Specialist agents — folder names (MUST)

Implement **18** agents + **`_shared`**, each under **`agents/<snake_case_folder>/`** with **`<name>.yaml`** where **`name`** in YAML uses **hyphens** (e.g. `code-writer`) matching URL paths:

| Folder | YAML `name` (typical) |
|--------|------------------------|
| `code_writer` | `code-writer` |
| `code_reasoning` | `code-reasoning` |
| `code_reviewer` | `code-reviewer` |
| `code_tester` | `code-tester` |
| `test_coverage` | `test-coverage` |
| `git_ops` | `git-ops` |
| `jenkins_cicd` | `jenkins-cicd` |
| `argocd_verify` | `argocd-verify` |
| `qa_regression` | `qa-regression` |
| `auto_pilot` | `auto-pilot` |
| `jira_ops` | `jira-ops` |
| `security` | `security` |
| `redash_query` | `redash-query` |
| `github_actions` | `github-actions` |
| `grafana_ops` | `grafana-ops` |
| `terraform_ops` | `terraform-ops` |
| `db_ops` | `db-ops` |
| `pr_review` | `pr-review` |
| `debug_agent` | `debug-agent` |
| `_shared` | (shared skills/autorun only) |

Each agent exposes **`/v1/agents/<name>/chat/completions`** (hyphenated name).

---

### 7) Domain packages under `code_agents/` (MUST exist)

Split features **by domain**, many modules each, **lazy import** where expensive:

| Package | Role (summary) |
|---------|----------------|
| `security/` | OWASP, secrets, vulns, compliance, encryption, input validation, … |
| `reviews/` | Code review, smell, tech debt, imports, dead code, clones, naming, types, … |
| `testing/` | Mutation, property tests, gaps, error immunizer, regression oracle, … |
| `observability/` | OTel helpers, profiling, log analysis, incident replay, perf, … |
| `git_ops/` | Hooks, PR helpers, blame, semantic merge, … |
| `knowledge/` | RAG, docs, graph, workspace PR, verbal architect, … |
| `api/` | OpenAPI, compat, schema, ORM review, REST→gRPC, … |
| `devops/` | CI heal, connection validator, background agents, terraform/k8s helpers, … |
| `ui/` | Voice, browser, screenshots, mindmaps, … |
| `domain/` | Payments-adjacent (txn flow, PCI, settlement, acquirer health, load tests, …), collaboration, notifications, sprint, … |
| `cicd/` | **`pipeline_state`**, Jenkins/Argo clients consumed by routers and auto-pilot. |
| `parsers/` | Python/JS/TS/Java/Go AST utilities. |
| `analysis/` | Security scan, complexity, dead code, bugs, impact heatmap, … |
| `generators/` | Changelog, API docs, tests, QA suite, test data. |
| `integrations/` | Elasticsearch, MCP, Slack, Redash, … |
| `reporters/` | Env health, incident, morning, oncall, sprint. |
| `tools/` | Coverage, commit, refactor, watch, vscode extension helpers. |
| `webui/` | Static browser chat + FastAPI router mounted at **`/ui`**. |

---

### 8) `agent_system/` (MUST)

Implement modules aligned with **Appendix B** (or equivalent names): orchestration, **skill_loader**, **rules_loader**, **agent_memory**, **session_scratchpad**, **plan_manager**, **questionnaire**, **question_parser**, **agent_replay**, **subagent_dispatcher**, **agent_corrections**, **bash_tool**, **requirement_confirm**, **smart_orchestrator**, **context_capsule**, optional **prompt_evolver**, **swarm_debugger**, **decision_fatigue_reducer**, **scope_creep_guard**, **skill_marketplace**.

**Central types (high connectivity in architecture):** **`SmartOrchestrator`**, **`AgentConfig`** — wire these as first-class, not ad hoc dicts.

---

### 9) CLI, chat, TUI, setup (MUST)

- **`code_agents/cli/`** — Entry **`cli.py`**: registry of **many** subcommands (`init`, `doctor`, `start`, `export`, `curls`, productivity tools, …). Match **“CLI-first”** product shape.
- **`code_agents/chat/`** — Async REPL, **slash_registry**, slash handlers (nav, session, agents, ops, config), streaming response handling, **Plan mode**, message queue, history persistence.
- **`code_agents/tui/`** — Textual full-screen app (optional **`CODE_AGENTS_TUI`**).
- **`code_agents/setup/`** — Interactive **`code-agents-setup`** wizard.

---

### 10) TypeScript terminal (`terminal/`) (MUST)

Mirror **Appendix C** conceptually:

- **`client/ApiClient.ts`** — SSE streaming, POST completions.
- **`client/AgentService.ts`**, **`Orchestrator.ts`**, **`TagParser.ts`**, **`SkillLoader.ts`**, **`ConfidenceScorer.ts`**, etc.
- **`state/`** — Zustand store, **`SessionHistory`**, **`Scratchpad`**, **`TokenTracker`**, config.
- **`chat/`** — Ink **`ChatApp`**, hooks **`useChat`**, **`useStreaming`**, **`useAgenticLoop`**, **`PlanMode`**, **`Questionnaire`**, **`StreamingResponse`**.
- **`slash/`** — **`registry.ts`**, **`router.ts`**, handlers **agents**, **session**, **nav**, **ops**, **config**.
- **`commands/`** — `chat`, `start`, `stop`, `status`, `agents`, `doctor`, `init`.
- **`tui/`** — Rich TUI components (**`FullScreenApp`**, **`DiffView`**, **`FileTree`**, …).
- Tests: **vitest** under **`terminal/tests/`** (or project convention).

Session files **interchangeable** with Python chat under **`~/.code-agents/chat_history/`**.

---

### 11) Extensions (MUST)

- **`extensions/vscode/`**, **`extensions/intellij/`**, **`extensions/chrome/`**
- Shared UI: **`extensions/vscode/webview-ui/`**
- Build: **`extensions/Makefile`** — `make all`, `make test`, `make package`
- Diagnostics in **`GET /diagnostics`** may report whether **`dist/extension.js`**, JetBrains distributions, **`manifest.json`** exist.

---

### 12) Dependencies (`pyproject.toml`) (MUST)

**Runtime (representative):** `fastapi`, `uvicorn[standard]`, `pydantic>=2`, `httpx`, `pyyaml`, `requests`, `elasticsearch>=8,<9`, `prompt-toolkit`, `textual`, `questionary`, `opentelemetry-*`, `structlog`, `claude-agent-sdk`, optional **`cursor-agent-sdk`** (Poetry optional group / git dep).

**Dev:** `pytest`, `pytest-asyncio`, `mcp`, `graphifyy` (optional).

---

### 13) `.env.example` (MUST)

Document **all** categories in **Appendix D** at placeholder values: API keys, **`CURSOR_API_URL`**, **`CODE_AGENTS_BACKEND`**, **`CODE_AGENTS_MODEL`**, limits (**`CODE_AGENTS_MAX_SESSION_TOKENS`**, **`CODE_AGENTS_CONTEXT_WINDOW`**, **`CODE_AGENTS_MAX_LOOPS`**), **`CODE_AGENTS_AUTO_RUN`**, **`CODE_AGENTS_DRY_RUN`**, **`CODE_AGENTS_REQUIRE_CONFIRM`**, **`HOST`**, **`PORT`**, **`TARGET_REPO_PATH`**, **`AGENTS_DIR`**, **`CODE_AGENTS_PUBLIC_BASE_URL`**, **`CODE_AGENTS_CORS_ORIGINS`**, **`CODE_AGENTS_HTTP_ONLY`**, OTEL vars, Jenkins, ArgoCD, Jira, Kibana, Grafana, GitHub, Slack, DB, Elasticsearch, Terraform, K8s, Redash, etc.

---

### 14) Build order (SHOULD)

1. `pyproject.toml` + package skeleton + **`core/app.py`** (**`/health`**, **`/diagnostics`**, lifespan).
2. **`core/config.py`** + **`core/env_loader.py`** (full loader semantics).
3. **`routers/completions.py`** + **`core/backend.py`** + **`core/stream.py`** — one agent E2E.
4. Register **all** Appendix A routers with **real** handlers wired to package functions.
5. **`agent_system/`** + **`chat/`** + **`cli/`**.
6. Feature domains (lazy imports).
7. **`terminal/`** then **`extensions/`**.
8. **`tests/`** mirroring modules; **`initiater/`** audit.

---

### 15) Acceptance checklist (MUST)

- [ ] Top-level tree matches §1.
- [ ] Every Appendix A router registered; conditional OAuth respected.
- [ ] Completions + per-agent routes work; SSE + JSON paths.
- [ ] Agent loader + YAML expansion + per-agent env overrides.
- [ ] Middleware + error handlers per §4.
- [ ] §6 agents + `_shared` present with skills/autorun pattern.
- [ ] `.env.example` covers Appendix D groups.
- [ ] Representative **`pytest`** passes.

---

### 16) Prohibitions (MUST NOT)

- Replace domain packages with a single **`services/`** or **`lib/`** catch-all.
- Drop **`routers/`** split or move all routes into **`app.py`**.
- Omit **`agent_system`** orchestration, **rules**, **skills**, **scratchpad**, **multi-backend**.
- Ship agents as **only** Python without **YAML** loader.

---

### END SUPER SYSTEM PROMPT

---

## Appendix A — HTTP routers (40 modules, prefixes)

| Python module | `APIRouter` prefix (typical) | Notes |
|---------------|------------------------------|-------|
| `completions` | *(none)* | `/v1/chat/completions`, `/v1/agents/{agent}/chat/completions` |
| `agents_list` | *(none)* | Agent listing for clients |
| `redash` | `/redash` | Redash integration |
| `elasticsearch` | `/elasticsearch` | ES API |
| `atlassian_oauth_web` | `/oauth/atlassian` | If env client id set |
| `git_ops` | `/git` | Git operations on target repo |
| `testing` | `/testing` | Test execution helpers |
| `jenkins` | `/jenkins` | Jenkins |
| `argocd` | `/argocd` | Includes **`app_alias_router`** for app path aliases |
| `pipeline` | `/pipeline` | See Appendix F |
| `k8s` | `/k8s` | Kubernetes |
| `kibana` | `/kibana` | Logs |
| `grafana` | `/grafana` | Metrics |
| `github_actions` | `/github-actions` | GHA |
| `terraform` | `/terraform` | IaC |
| `jira` | `/jira` | Jira/Confluence |
| `mcp` | `/mcp` | Model Context Protocol |
| `telemetry` | `/telemetry` | Usage analytics |
| `knowledge_graph` | `/knowledge-graph` | Graph endpoints |
| `slack_bot` | `/slack` | Slack bridge |
| `db` | `/db` | Postgres/safe DB |
| `pr_review` | `/pr-review` | PR bot |
| `debug` | `/debug` | Debug engine |
| `review` | `/review` | Review engine |
| `benchmark` | `/benchmark` | Agent benchmarks |
| `pr_describe` | `/pr-describe` | Productivity |
| `postmortem` | `/postmortem` | |
| `dep_upgrade` | `/dep-upgrade` | |
| `review_buddy` | `/review-buddy` | |
| `migration_gen` | `/db-migrate` | |
| `oncall_summary` | `/oncall-summary` | |
| `test_impact` | `/test-impact` | |
| `runbook` | `/runbook` | |
| `sprint_dashboard` | `/sprint-dashboard` | |
| `codebase_qa` | `/explain` | |
| `code_nav` | `/code-nav` | |
| `debug_tools` | `/debug-tools` | |
| `test_tools` | `/test-tools` | |
| `api_tools` | `/api-tools` | |
| `db_tools` | `/db-tools` | |
| `webui` | *(mount `/ui`)* | Static chat UI |

**Plus:** **`domain.collaboration.create_collab_router()`** — WebSocket collaboration (not necessarily in `routers/` file list).

---

## Appendix B — `agent_system/` modules

| Module | Role |
|--------|------|
| `smart_orchestrator.py` | High-level multi-step agent orchestration |
| `skill_loader.py` | Load `[SKILL:]` markdown |
| `rules_loader.py` | Merge global + project rules each turn |
| `agent_memory.py` | Persistent memory files per agent |
| `session_scratchpad.py` | `/tmp/.../state.json` + `[REMEMBER:]` |
| `plan_manager.py` | Plan mode lifecycle |
| `questionnaire.py` / `question_parser.py` | `[QUESTION:]` wizard |
| `agent_replay.py` | Trace record/replay/fork |
| `subagent_dispatcher.py` | Delegate sub-agents |
| `agent_corrections.py` | User correction learning |
| `bash_tool.py` | Safe shell execution for agent loop |
| `requirement_confirm.py` | Spec confirmation gate |
| `context_capsule.py` | Context packaging |
| `prompt_evolver.py` | Prompt evolution experiments |
| `swarm_debugger.py` | Multi-agent debug |
| `decision_fatigue_reducer.py` / `scope_creep_guard.py` | UX guardrails |
| `skill_marketplace.py` | Skill discovery (if enabled) |

---

## Appendix C — `terminal/src/` layout

| Area | Key files |
|------|-----------|
| `client/` | `ApiClient.ts`, `AgentService.ts`, `Orchestrator.ts`, `TagParser.ts`, `SkillLoader.ts`, `ConfidenceScorer.ts`, `ServerMonitor.ts`, `ContextTrimmer.ts`, `BackgroundTasks.ts`, `ComplexityDetector.ts`, `types.ts` |
| `state/` | `store.ts`, `SessionHistory.ts`, `Scratchpad.ts`, `TokenTracker.ts`, `config.ts` |
| `chat/` | `ChatApp.tsx`, `ChatInput.tsx`, `ChatOutput.tsx`, `StreamingResponse.tsx`, `QueuedMessages.tsx`, `WelcomeMessage.tsx`, `StatusBar.tsx`, `PlanMode.tsx`, `Questionnaire.tsx`, `CommandPanel.tsx`, `CommandApproval.tsx`, `ResponseBox.tsx`, `MarkdownRenderer.tsx`, hooks: `useChat`, `useStreaming`, `useAgenticLoop`, `useMessageQueue`, `useKeyBindings`, `usePlan` |
| `slash/` | `index.ts`, `registry.ts`, `router.ts`, `handlers/agents.ts`, `session.ts`, `nav.ts`, `ops.ts`, `config.ts` |
| `commands/` | `chat.tsx`, `start.ts`, `stop.ts`, `status.ts`, `agents.ts`, `doctor.ts`, `init.ts` |
| `tui/` | `FullScreenApp.tsx`, `DiffView.tsx`, `FileTree.tsx`, `AgentSelector.tsx`, `TokenBudgetBar.tsx`, `ProgressDashboard.tsx`, `ThinkingIndicator.tsx`, `StatusBar.tsx` |

---

## Appendix D — Environment variables (grouped)

**Core / LLM:** `CURSOR_API_KEY`, `ANTHROPIC_API_KEY`, `CURSOR_API_URL`, `CODE_AGENTS_BACKEND`, `CODE_AGENTS_MODEL`, per-agent `CODE_AGENTS_BACKEND_*`, `CODE_AGENTS_MODEL_*`, `CODE_AGENTS_HTTP_ONLY`.

**Server:** `HOST`, `PORT`, `LOG_LEVEL`, `CODE_AGENTS_CORS_ORIGINS`, `CODE_AGENTS_PUBLIC_BASE_URL`, `AGENTS_DIR`.

**Safety / loop:** `CODE_AGENTS_AUTO_RUN`, `CODE_AGENTS_DRY_RUN`, `CODE_AGENTS_MAX_SESSION_TOKENS`, `CODE_AGENTS_CONTEXT_WINDOW`, `CODE_AGENTS_MAX_LOOPS`, `CODE_AGENTS_REQUIRE_CONFIRM`, `TARGET_REPO_PATH`, `CODE_AGENTS_BUILD_CMD`.

**Telemetry:** `OTEL_*`, `CODE_AGENTS_*` analytics flags as implemented.

**Integrations (placeholders in `.env.example`):** Jenkins (`JENKINS_URL`, `JENKINS_USERNAME`, `JENKINS_API_TOKEN`, job names), ArgoCD (`ARGOCD_URL`, `ARGOCD_AUTH_TOKEN`, app name), Jira, Kibana, Grafana, GitHub (`GITHUB_TOKEN`, `GITHUB_REPO`), Slack, Elasticsearch, DB (`DATABASE_URL` or `DB_*`), Terraform, K8s, Redash, Atlassian OAuth, etc.

---

## Appendix E — Chat slash commands & platform surface

The product exposes **on the order of ~55 CLI subcommands** and **many slash commands** in chat, including: `/help`, `/agents`, `/agent`, `/run`, `/exec`, `/rules`, `/skills`, `/tokens`, `/session`, `/clear`, `/history`, `/resume`, `/setup`, `/memory`, `/plan`, `/export`, `/mcp`, `/bg`, `/tasks`, `/review`, `/mindmap`, `/dep-impact`, `/dashboard`, `/changelog`, `/pair`, `/api-docs`, `/workspace`, productivity and domain tools (`/txn-flow`, `/pci-scan`, `/owasp-scan`, …). The builder MUST implement **registry-based** slash routing in Python (`chat/slash_registry.py` pattern) and mirror key commands in **`terminal/slash/`**.

---

## Appendix F — Pipeline API & CI/CD state

**Router:** `pipeline` → prefix **`/pipeline`**.

**Typical routes (conceptual):**

- `POST /pipeline/start` — body: branch, optional repo_path, build_job, deploy_job, argocd_app.
- `GET /pipeline/{run_id}/status`
- `POST /pipeline/{run_id}/advance`
- `POST /pipeline/{run_id}/rollback` (and related failure/step endpoints as in `pipeline.py`)

**State:** `code_agents/cicd/pipeline_state.py` — **`pipeline_manager`**, step enums, in-memory or pluggable store.

**Auto-pilot agent** references pipeline orchestration and multi-agent routing.

---

## Appendix G — Extensions & web UI

- **VS Code extension** — Webview sidebar, commands, SSE; consumes same API base.
- **IntelliJ** — JCEF tool window.
- **Chrome** — Side panel; GitHub/Jira context.
- **Shared webview** — `extensions/vscode/webview-ui/` single codebase for all three.
- **`webui/`** — Serves minimal HTML/CSS/JS chat at **`/ui`** without a separate frontend build step for the default web UI.

---

## Appendix H — Testing & quality gates

- **`tests/test_<module>.py`** maps to **`code_agents/<...>.py`**.
- **Strict asyncio** in pytest config.
- **No live network** in unit tests—mocks for HTTP, git remotes, cloud APIs.
- **`initiater/run_audit.py`** — multi-rule project audit (workflow sync, etc.).

---

## Appendix I — Graph / knowledge (optional)

- **`graphify-out/`** (repo root, not always inside `code_agents/`) — `GRAPH_REPORT.md`, `graph.json`, optional HTML; per-folder slices under `graphify-out/folders/`.
- **`.graphifyignore`** — corpus scope.
- **`KnowledgeGraph`** class under `knowledge/` — AST index of target repo; built async on server start in lifespan.

---

## Appendix J — Canonical `code_agents/` top-level packages (inventory)

The Python package root **`code_agents/`** MUST expose these **first-level subpackages** (names exact):

`agent_system`, `analysis`, `api`, `chat`, `cicd`, `cli`, `core`, `devops`, `domain`, `generators`, `git_ops`, `integrations`, `knowledge`, `observability`, `parsers`, `reporters`, `reviews`, `routers`, `security`, `setup`, `testing`, `tools`, `ui`, `webui`.

Optional/runtime: `logs/` (if used), `__pycache__/` (build artifact—never commit by convention).

**Scale expectation:** On the order of **500+** `*.py` files under `code_agents/` in a full implementation; **routers** alone ~**40** modules; **tests** ~**160+** files / **thousands** of cases at product maturity.

---

## Appendix K — Backend string values (`AgentConfig.backend`)

Support at minimum the **same backend labels** the loader and YAML use, including: **`cursor`**, **`claude`**, **`local`**, **`cursor_http`**, **`claude-cli`** (exact spellings as in `core/config.py` / agent YAML). Per-agent override env vars supersede YAML after expansion.

---

## Appendix L — Multi-message strategy (very large context)

| Message # | Content |
|-----------|---------|
| 1 | **Super system prompt** § Role–§16 + **Appendix A** (routers) |
| 2 | **Appendices B, C, D** (agent_system, terminal, env) |
| 3 | **Appendices E–L** (slash, pipeline, extensions, tests, graph, backends, multi-message) |
| 4 | **Appendices M–R** (CLI keys, YAML, skills paths, full `code_agents` / `tests` / `terminal` file lists) |
| 5 | **Appendix S** (what exhaustive means + how to regenerate lists) |

The agent should treat **all appendices** as **normative** when included in the same session.

---

## Appendix M — Complete `COMMAND_REGISTRY` CLI names (authoritative)

Source: `code_agents/cli/registry.py` → `_build_command_registry()`. **179** unique command keys (one key appears twice in source: `env-diff` — last definition wins).

```
acl-matrix
acquirer-health
add-types
adr
agent-pipeline
agents
api-changelog
api-check
api-docs
api-sync
apidoc
archaeology
audit
audit-idempotency
auto-review
batch
bench-compare
bench-trend
benchmark
bg
branches
browse
call-chain
changelog
changelog-gen
chat
ci-heal
ci-run
clones
comment-audit
commit
completions
complexity
compliance-report
config
config-diff
contract-test
cost
coverage
coverage-boost
curls
dashboard
db-migrate
dead-code-eliminate
deadcode
deadlock-scan
debug
dep-graph
dep-upgrade
diff
doctor
edge-cases
encryption-audit
endpoint-gen
env-diff
env-health
examples
explain
explain-code
export
flags
full-audit
gen-tests
git-story
help
hook-run
impact
imports
incident
index
init
input-audit
install-hooks
integration-scaffold
join
lang-migrate
leak-scan
license-audit
load-test
log-analyze
logs
migrate
migrate-tracing
mindmap
mock-build
morning
mutate-test
naming-audit
nav
onboard
onboard-tour
oncall-report
oncall-summary
orm-review
owasp-scan
ownership
pair
pci-scan
perf-baseline
perf-proof
pipeline
plugin
postmortem
postmortem-gen
pr-describe
pr-preview
pr-respond
pr-split
pre-push
preview
privacy-scan
profiler
prop-test
qa-suite
query-optimize
rate-limit-audit
readme
recon
release
release-notes
replay
repos
response-optimize
rest-to-grpc
restart
retry-audit
review
review-buddy
review-fix
rules
runbook
schema
schema-design
screenshot
secret-rotation
security
self-bench
session-audit
sessions
settlement
setup
share
shutdown
skill
slack
smell
snippet
spec-validate
sprint-dashboard
sprint-report
sprint-velocity
stack-decode
standup
start
status
tail
team-kb
tech-debt
techdebt
test
test-fix
test-impact
test-style
translate
txn-flow
undo
update
usage-trace
validate-config
validate-states
velocity-predict
version
version-bump
visual-test
voice
vuln-chain
watch
watchdog
workspace
```

---

## Appendix N — All agent `autorun` / `*.yaml` under `agents/`

**39** paths:

```
agents/_shared/autorun.yaml
agents/argocd_verify/argocd_verify.yaml
agents/argocd_verify/autorun.yaml
agents/auto_pilot/auto_pilot.yaml
agents/auto_pilot/autorun.yaml
agents/code_reasoning/autorun.yaml
agents/code_reasoning/code_reasoning.yaml
agents/code_reviewer/autorun.yaml
agents/code_reviewer/code_reviewer.yaml
agents/code_tester/autorun.yaml
agents/code_tester/code_tester.yaml
agents/code_writer/autorun.yaml
agents/code_writer/code_writer.yaml
agents/db_ops/autorun.yaml
agents/db_ops/db_ops.yaml
agents/debug_agent/autorun.yaml
agents/debug_agent/debug_agent.yaml
agents/git_ops/autorun.yaml
agents/git_ops/git_ops.yaml
agents/github_actions/autorun.yaml
agents/github_actions/github_actions.yaml
agents/grafana_ops/autorun.yaml
agents/grafana_ops/grafana_ops.yaml
agents/jenkins_cicd/autorun.yaml
agents/jenkins_cicd/jenkins_cicd.yaml
agents/jira_ops/autorun.yaml
agents/jira_ops/jira_ops.yaml
agents/pr_review/autorun.yaml
agents/pr_review/pr_review.yaml
agents/qa_regression/autorun.yaml
agents/qa_regression/qa_regression.yaml
agents/redash_query/autorun.yaml
agents/redash_query/redash_query.yaml
agents/security/autorun.yaml
agents/security/security.yaml
agents/terraform_ops/autorun.yaml
agents/terraform_ops/terraform_ops.yaml
agents/test_coverage/autorun.yaml
agents/test_coverage/test_coverage.yaml
```

---

## Appendix O — All `agents/**/skills/*.md` files

**207** skill markdown files:

```
agents/_shared/skills/architecture.md
agents/_shared/skills/code-review.md
agents/_shared/skills/debug.md
agents/_shared/skills/deploy-checklist.md
agents/_shared/skills/documentation.md
agents/_shared/skills/explore.md
agents/_shared/skills/grafana-metrics.md
agents/_shared/skills/incident-response.md
agents/_shared/skills/kibana-logs.md
agents/_shared/skills/standup.md
agents/_shared/skills/system-design.md
agents/_shared/skills/tech-debt.md
agents/_shared/skills/testing-strategy.md
agents/argocd_verify/skills/api-reference.md
agents/argocd_verify/skills/canary-analysis.md
agents/argocd_verify/skills/health-check.md
agents/argocd_verify/skills/incident-response.md
agents/argocd_verify/skills/k8s-pods.md
agents/argocd_verify/skills/kibana-logs.md
agents/argocd_verify/skills/log-scan.md
agents/argocd_verify/skills/multi-env-verify.md
agents/argocd_verify/skills/resource-monitor.md
agents/argocd_verify/skills/rollback.md
agents/argocd_verify/skills/sanity-check.md
agents/auto_pilot/skills/cicd-pipeline.md
agents/auto_pilot/skills/full-sdlc.md
agents/auto_pilot/skills/incident-manager.md
agents/auto_pilot/skills/investigate.md
agents/auto_pilot/skills/pipeline-advance.md
agents/auto_pilot/skills/pipeline-start-pipeline.md
agents/auto_pilot/skills/pipeline-status-report.md
agents/auto_pilot/skills/release.md
agents/auto_pilot/skills/review-fix.md
agents/auto_pilot/skills/router-multi-agent-plan.md
agents/auto_pilot/skills/router-smart-route.md
agents/auto_pilot/skills/workflow-planner.md
agents/code-reasoning/skills/call-chain.md
agents/code-reasoning/skills/code-examples.md
agents/code-reasoning/skills/codebase-nav.md
agents/code-reasoning/skills/dep-graph-viz.md
agents/code-reasoning/skills/explain-code.md
agents/code-reasoning/skills/git-story.md
agents/code-reasoning/skills/usage-trace.md
agents/code-writer/skills/mcp-server-generator.md
agents/code_reasoning/skills/architecture-review.md
agents/code_reasoning/skills/capacity-planning.md
agents/code_reasoning/skills/compare.md
agents/code_reasoning/skills/dependency-map.md
agents/code_reasoning/skills/explain.md
agents/code_reasoning/skills/explore-analyze-architecture.md
agents/code_reasoning/skills/explore-find-patterns.md
agents/code_reasoning/skills/explore-search-codebase.md
agents/code_reasoning/skills/explore-smart-search.md
agents/code_reasoning/skills/impact-analysis.md
agents/code_reasoning/skills/solution-design.md
agents/code_reasoning/skills/system-analysis.md
agents/code_reasoning/skills/tech-debt-assessment.md
agents/code_reasoning/skills/trace-flow.md
agents/code_reviewer/skills/bug-hunt.md
agents/code_reviewer/skills/design-review.md
agents/code_reviewer/skills/pr-review.md
agents/code_reviewer/skills/review-changes.md
agents/code_reviewer/skills/review-file.md
agents/code_reviewer/skills/review-summary.md
agents/code_reviewer/skills/security-review.md
agents/code_tester/skills/debug-failure.md
agents/code_tester/skills/debug.md
agents/code_tester/skills/edge-cases.md
agents/code_tester/skills/flaky-test-hunter.md
agents/code_tester/skills/generate-tests.md
agents/code_tester/skills/integration-scaffold.md
agents/code_tester/skills/integration-test.md
agents/code_tester/skills/mock-build.md
agents/code_tester/skills/test-and-report.md
agents/code_tester/skills/test-data-factory.md
agents/code_tester/skills/test-fix-loop.md
agents/code_tester/skills/test-fix.md
agents/code_tester/skills/test-infrastructure.md
agents/code_tester/skills/test-quality-audit.md
agents/code_tester/skills/unit-test.md
agents/code_writer/skills/api-sync.md
agents/code_writer/skills/dependency-upgrade.md
agents/code_writer/skills/endpoint-gen.md
agents/code_writer/skills/fix-bug.md
agents/code_writer/skills/generate-from-spec.md
agents/code_writer/skills/implement.md
agents/code_writer/skills/java-spring.md
agents/code_writer/skills/java-upgrade.md
agents/code_writer/skills/local-build.md
agents/code_writer/skills/performance-optimize.md
agents/code_writer/skills/refactoring.md
agents/code_writer/skills/response-optimize.md
agents/code_writer/skills/rest-to-grpc.md
agents/code_writer/skills/spring-upgrade.md
agents/code_writer/skills/write-and-test.md
agents/code_writer/skills/write-from-jira.md
agents/db_ops/skills/explain-plan.md
agents/db_ops/skills/generate-migration.md
agents/db_ops/skills/orm-review.md
agents/db_ops/skills/query-optimize.md
agents/db_ops/skills/safe-query.md
agents/db_ops/skills/schema-design.md
agents/db_ops/skills/schema-diff.md
agents/db_ops/skills/table-info.md
agents/debug_agent/skills/deadlock-scan.md
agents/debug_agent/skills/env-diff.md
agents/debug_agent/skills/fix-and-verify.md
agents/debug_agent/skills/leak-scan.md
agents/debug_agent/skills/log-analyze.md
agents/debug_agent/skills/reproduce-bug.md
agents/debug_agent/skills/stack-decode.md
agents/debug_agent/skills/trace-error.md
agents/git_ops/skills/branch-summary.md
agents/git_ops/skills/cherry-pick.md
agents/git_ops/skills/conflict-resolver.md
agents/git_ops/skills/diff-review.md
agents/git_ops/skills/git-history.md
agents/git_ops/skills/pre-push.md
agents/git_ops/skills/release-branch.md
agents/git_ops/skills/safe-checkout.md
agents/git_ops/skills/tag-release.md
agents/github_actions/skills/debug-failure.md
agents/github_actions/skills/list-workflows.md
agents/github_actions/skills/monitor-run.md
agents/github_actions/skills/retry-failed.md
agents/github_actions/skills/trigger-workflow.md
agents/grafana_ops/skills/correlate-deploy.md
agents/grafana_ops/skills/dashboard-search.md
agents/grafana_ops/skills/investigate-alert.md
agents/grafana_ops/skills/query-metrics.md
agents/jenkins_cicd/skills/api-reference.md
agents/jenkins_cicd/skills/argocd-verify.md
agents/jenkins_cicd/skills/build-troubleshoot.md
agents/jenkins_cicd/skills/build.md
agents/jenkins_cicd/skills/deploy.md
agents/jenkins_cicd/skills/git-precheck.md
agents/jenkins_cicd/skills/log-analysis.md
agents/jenkins_cicd/skills/multi-service-deploy.md
agents/jenkins_cicd/skills/pipeline-manager.md
agents/jira_ops/skills/create-ticket.md
agents/jira_ops/skills/dependency-map.md
agents/jira_ops/skills/post-deploy-update.md
agents/jira_ops/skills/progress-updater.md
agents/jira_ops/skills/read-ticket.md
agents/jira_ops/skills/read-wiki.md
agents/jira_ops/skills/release-notes.md
agents/jira_ops/skills/release-tracker.md
agents/jira_ops/skills/sprint-manager.md
agents/jira_ops/skills/standup-report.md
agents/jira_ops/skills/ticket-validate.md
agents/jira_ops/skills/update-status.md
agents/pr_review/skills/api-changelog.md
agents/pr_review/skills/auto-review.md
agents/pr_review/skills/post-comments.md
agents/pr_review/skills/review-checklist.md
agents/pr_review/skills/webhook-handler.md
agents/qa_regression/skills/api-testing.md
agents/qa_regression/skills/auto-coverage.md
agents/qa_regression/skills/baseline-manager.md
agents/qa_regression/skills/contract-validation.md
agents/qa_regression/skills/endpoint-discovery.md
agents/qa_regression/skills/full-regression.md
agents/qa_regression/skills/negative-testing.md
agents/qa_regression/skills/performance-regression.md
agents/qa_regression/skills/regression-orchestrator.md
agents/qa_regression/skills/regression-suite.md
agents/qa_regression/skills/run-endpoints.md
agents/qa_regression/skills/suite-generator.md
agents/qa_regression/skills/targeted-regression.md
agents/qa_regression/skills/test-plan.md
agents/qa_regression/skills/write-missing.md
agents/redash_query/skills/data-validation.md
agents/redash_query/skills/explore-schema.md
agents/redash_query/skills/incident-investigate.md
agents/redash_query/skills/migration-verify.md
agents/redash_query/skills/query-builder.md
agents/redash_query/skills/query-optimizer.md
agents/redash_query/skills/saved-queries.md
agents/redash_query/skills/schema-analysis.md
agents/redash_query/skills/write-query.md
agents/security/skills/api-security.md
agents/security/skills/attack-surface.md
agents/security/skills/code-injection.md
agents/security/skills/compliance-review.md
agents/security/skills/container-scan.md
agents/security/skills/dependency-audit.md
agents/security/skills/secrets-detection.md
agents/security/skills/security-report.md
agents/security/skills/supply-chain.md
agents/security/skills/vulnerability-scan.md
agents/terraform_ops/skills/apply.md
agents/terraform_ops/skills/drift-detect.md
agents/terraform_ops/skills/plan.md
agents/terraform_ops/skills/review-plan.md
agents/terraform_ops/skills/state-inspect.md
agents/test_coverage/skills/auto-coverage.md
agents/test_coverage/skills/autonomous-boost.md
agents/test_coverage/skills/coverage-diff.md
agents/test_coverage/skills/coverage-gate.md
agents/test_coverage/skills/coverage-plan.md
agents/test_coverage/skills/find-gaps.md
agents/test_coverage/skills/jacoco-report.md
agents/test_coverage/skills/run-coverage.md
agents/test_coverage/skills/write-e2e-tests.md
agents/test_coverage/skills/write-integration-tests.md
agents/test_coverage/skills/write-python-tests.md
agents/test_coverage/skills/write-unit-tests.md
```

**Note:** Some agents have **both** `code-reasoning/` and `code_reasoning/` style paths (hyphen vs underscore folders). A greenfield clone may normalize to one convention; parity with this tree may preserve both.

---

## Appendix P — Complete `code_agents/**/*.py` inventory

**526** Python modules (excluding `__pycache__`).

```
code_agents/__init__.py
code_agents/__version__.py
code_agents/agent_system/__init__.py
code_agents/agent_system/agent_corrections.py
code_agents/agent_system/agent_memory.py
code_agents/agent_system/agent_replay.py
code_agents/agent_system/bash_tool.py
code_agents/agent_system/context_capsule.py
code_agents/agent_system/decision_fatigue_reducer.py
code_agents/agent_system/plan_manager.py
code_agents/agent_system/prompt_evolver.py
code_agents/agent_system/question_parser.py
code_agents/agent_system/questionnaire.py
code_agents/agent_system/requirement_confirm.py
code_agents/agent_system/rules_loader.py
code_agents/agent_system/scope_creep_guard.py
code_agents/agent_system/session_scratchpad.py
code_agents/agent_system/skill_loader.py
code_agents/agent_system/skill_marketplace.py
code_agents/agent_system/smart_orchestrator.py
code_agents/agent_system/subagent_dispatcher.py
code_agents/agent_system/swarm_debugger.py
code_agents/analysis/__init__.py
code_agents/analysis/_ast_helpers.py
code_agents/analysis/arch_drift_detector.py
code_agents/analysis/bug_patterns.py
code_agents/analysis/clone_lineage.py
code_agents/analysis/codebase_sql.py
code_agents/analysis/compile_check.py
code_agents/analysis/complexity.py
code_agents/analysis/config_drift.py
code_agents/analysis/dead_code_reaper.py
code_agents/analysis/deadcode.py
code_agents/analysis/dependency_graph.py
code_agents/analysis/feature_flags.py
code_agents/analysis/impact_analysis.py
code_agents/analysis/impact_heatmap.py
code_agents/analysis/project_scanner.py
code_agents/analysis/security_scanner.py
code_agents/api/__init__.py
code_agents/api/api_changelog_gen.py
code_agents/api/api_compat.py
code_agents/api/api_design_checker.py
code_agents/api/api_docs.py
code_agents/api/api_sync.py
code_agents/api/endpoint_generator.py
code_agents/api/implicit_api_docs.py
code_agents/api/orm_reviewer.py
code_agents/api/query_optimizer.py
code_agents/api/rest_to_grpc.py
code_agents/api/schema_designer.py
code_agents/api/schema_evolution_sim.py
code_agents/api/schema_viz.py
code_agents/chat/__init__.py
code_agents/chat/chat.py
code_agents/chat/chat_async_repl.py
code_agents/chat/chat_background.py
code_agents/chat/chat_branch.py
code_agents/chat/chat_clipboard.py
code_agents/chat/chat_commands.py
code_agents/chat/chat_complexity.py
code_agents/chat/chat_context.py
code_agents/chat/chat_delegation.py
code_agents/chat/chat_history.py
code_agents/chat/chat_input.py
code_agents/chat/chat_repl.py
code_agents/chat/chat_response.py
code_agents/chat/chat_server.py
code_agents/chat/chat_skill_runner.py
code_agents/chat/chat_slash.py
code_agents/chat/chat_slash_agents.py
code_agents/chat/chat_slash_analysis.py
code_agents/chat/chat_slash_config.py
code_agents/chat/chat_slash_features.py
code_agents/chat/chat_slash_nav.py
code_agents/chat/chat_slash_ops.py
code_agents/chat/chat_slash_productivity.py
code_agents/chat/chat_slash_session.py
code_agents/chat/chat_slash_tools.py
code_agents/chat/chat_state.py
code_agents/chat/chat_streaming.py
code_agents/chat/chat_theme.py
code_agents/chat/chat_tui.py
code_agents/chat/chat_ui.py
code_agents/chat/chat_validation.py
code_agents/chat/chat_welcome.py
code_agents/chat/command_panel.py
code_agents/chat/command_panel_options.py
code_agents/chat/slash_registry.py
code_agents/chat/terminal_layout.py
code_agents/chat/tui/__init__.py
code_agents/chat/tui/app.py
code_agents/chat/tui/bridge.py
code_agents/chat/tui/css.py
code_agents/chat/tui/proxy.py
code_agents/chat/tui/widgets/__init__.py
code_agents/chat/tui/widgets/command_approval.py
code_agents/chat/tui/widgets/input_area.py
code_agents/chat/tui/widgets/output_log.py
code_agents/chat/tui/widgets/questionnaire.py
code_agents/chat/tui/widgets/spinner.py
code_agents/chat/tui/widgets/status_bar.py
code_agents/cicd/__init__.py
code_agents/cicd/argocd_client.py
code_agents/cicd/db_client.py
code_agents/cicd/endpoint_scanner.py
code_agents/cicd/git_client.py
code_agents/cicd/github_actions_client.py
code_agents/cicd/grafana_client.py
code_agents/cicd/jacoco_parser.py
code_agents/cicd/jenkins_client.py
code_agents/cicd/jira_client.py
code_agents/cicd/k8s_client.py
code_agents/cicd/kibana_client.py
code_agents/cicd/pipeline_state.py
code_agents/cicd/pr_review_client.py
code_agents/cicd/review_config.py
code_agents/cicd/sanity_checker.py
code_agents/cicd/terraform_client.py
code_agents/cicd/testing_client.py
code_agents/cli/__init__.py
code_agents/cli/cli.py
code_agents/cli/cli_acl_matrix.py
code_agents/cli/cli_acquirer.py
code_agents/cli/cli_adr.py
code_agents/cli/cli_analysis.py
code_agents/cli/cli_api_docs.py
code_agents/cli/cli_api_tools.py
code_agents/cli/cli_archaeology.py
code_agents/cli/cli_audit.py
code_agents/cli/cli_batch.py
code_agents/cli/cli_bg.py
code_agents/cli/cli_browse.py
code_agents/cli/cli_changelog.py
code_agents/cli/cli_ci_heal.py
code_agents/cli/cli_ci_run.py
code_agents/cli/cli_cicd.py
code_agents/cli/cli_clones.py
code_agents/cli/cli_code_nav.py
code_agents/cli/cli_comment_audit.py
code_agents/cli/cli_completions.py
code_agents/cli/cli_compliance.py
code_agents/cli/cli_config_validator.py
code_agents/cli/cli_contract_test.py
code_agents/cli/cli_cost.py
code_agents/cli/cli_curls.py
code_agents/cli/cli_dashboard.py
code_agents/cli/cli_db_tools.py
code_agents/cli/cli_dead_code.py
code_agents/cli/cli_debug_tools.py
code_agents/cli/cli_dep_impact.py
code_agents/cli/cli_doctor.py
code_agents/cli/cli_encryption_audit.py
code_agents/cli/cli_env_diff.py
code_agents/cli/cli_explain.py
code_agents/cli/cli_features.py
code_agents/cli/cli_git.py
code_agents/cli/cli_helpers.py
code_agents/cli/cli_hooks.py
code_agents/cli/cli_idempotency.py
code_agents/cli/cli_imports.py
code_agents/cli/cli_index.py
code_agents/cli/cli_input_audit.py
code_agents/cli/cli_lang_migrate.py
code_agents/cli/cli_license_audit.py
code_agents/cli/cli_load_test.py
code_agents/cli/cli_migrate_tracing.py
code_agents/cli/cli_mindmap.py
code_agents/cli/cli_mutate.py
code_agents/cli/cli_naming.py
code_agents/cli/cli_onboard_new.py
code_agents/cli/cli_owasp.py
code_agents/cli/cli_ownership.py
code_agents/cli/cli_pair.py
code_agents/cli/cli_pci.py
code_agents/cli/cli_perf_proof.py
code_agents/cli/cli_postmortem_gen.py
code_agents/cli/cli_pr_respond.py
code_agents/cli/cli_pr_split.py
code_agents/cli/cli_preview.py
code_agents/cli/cli_privacy_scan.py
code_agents/cli/cli_productivity.py
code_agents/cli/cli_profiler.py
code_agents/cli/cli_prop_test.py
code_agents/cli/cli_rate_limit_audit.py
code_agents/cli/cli_recon.py
code_agents/cli/cli_release_notes.py
code_agents/cli/cli_replay.py
code_agents/cli/cli_reports.py
code_agents/cli/cli_retry.py
code_agents/cli/cli_review.py
code_agents/cli/cli_schema.py
code_agents/cli/cli_screenshot.py
code_agents/cli/cli_secret_rotation.py
code_agents/cli/cli_self_bench.py
code_agents/cli/cli_server.py
code_agents/cli/cli_session_audit.py
code_agents/cli/cli_settlement.py
code_agents/cli/cli_skill.py
code_agents/cli/cli_slack.py
code_agents/cli/cli_smell.py
code_agents/cli/cli_snippet.py
code_agents/cli/cli_spec.py
code_agents/cli/cli_state_machine.py
code_agents/cli/cli_tail.py
code_agents/cli/cli_team_kb.py
code_agents/cli/cli_tech_debt.py
code_agents/cli/cli_test_style.py
code_agents/cli/cli_test_tools.py
code_agents/cli/cli_tools.py
code_agents/cli/cli_translate.py
code_agents/cli/cli_txn_flow.py
code_agents/cli/cli_type_adder.py
code_agents/cli/cli_undo.py
code_agents/cli/cli_velocity.py
code_agents/cli/cli_visual_test.py
code_agents/cli/cli_voice.py
code_agents/cli/cli_vuln_chain.py
code_agents/cli/registry.py
code_agents/core/__init__.py
code_agents/core/app.py
code_agents/core/backend.py
code_agents/core/confidence_scorer.py
code_agents/core/config.py
code_agents/core/context_manager.py
code_agents/core/cursor_cli.py
code_agents/core/env_loader.py
code_agents/core/logging_config.py
code_agents/core/main.py
code_agents/core/message_types.py
code_agents/core/models.py
code_agents/core/openai_errors.py
code_agents/core/public_urls.py
code_agents/core/rate_limiter.py
code_agents/core/response_optimizer.py
code_agents/core/response_verifier.py
code_agents/core/stream.py
code_agents/core/token_tracker.py
code_agents/devops/__init__.py
code_agents/devops/background_agent.py
code_agents/devops/batch_ops.py
code_agents/devops/ci_self_heal.py
code_agents/devops/config_validator.py
code_agents/devops/connection_validator.py
code_agents/devops/conversational_deploy.py
code_agents/devops/dockerfile_optimizer.py
code_agents/devops/env_cloner.py
code_agents/devops/env_diff.py
code_agents/devops/env_differ.py
code_agents/devops/headless_mode.py
code_agents/devops/helm_debugger.py
code_agents/devops/k8s_generator.py
code_agents/devops/outage_topology.py
code_agents/devops/pipeline.py
code_agents/devops/sandbox.py
code_agents/devops/self_tuning_ci.py
code_agents/devops/terraform_explainer.py
code_agents/domain/__init__.py
code_agents/domain/acquirer_health.py
code_agents/domain/atlassian_oauth.py
code_agents/domain/breaking_change_precog.py
code_agents/domain/collaboration.py
code_agents/domain/dep_decay_forecast.py
code_agents/domain/dep_impact.py
code_agents/domain/dep_upgrade.py
code_agents/domain/gita_shlokas.py
code_agents/domain/idempotency_audit.py
code_agents/domain/incident_timeline.py
code_agents/domain/load_test_gen.py
code_agents/domain/notifications.py
code_agents/domain/oncall_summary.py
code_agents/domain/pair_mode.py
code_agents/domain/postmortem.py
code_agents/domain/postmortem_gen.py
code_agents/domain/project_context.py
code_agents/domain/repo_manager.py
code_agents/domain/retry_analyzer.py
code_agents/domain/settlement_parser.py
code_agents/domain/sprint_dashboard.py
code_agents/domain/state_machine_validator.py
code_agents/domain/techdebt_interest.py
code_agents/domain/toil_predictor.py
code_agents/domain/txn_flow.py
code_agents/domain/usage_tracer.py
code_agents/domain/velocity_anomaly.py
code_agents/domain/velocity_predict.py
code_agents/generators/__init__.py
code_agents/generators/api_doc_generator.py
code_agents/generators/changelog_gen.py
code_agents/generators/mcp_gen.py
code_agents/generators/qa_suite_generator.py
code_agents/generators/test_data_generator.py
code_agents/generators/test_generator.py
code_agents/git_ops/__init__.py
code_agents/git_ops/action_log.py
code_agents/git_ops/blame_investigator.py
code_agents/git_ops/branch_cleanup.py
code_agents/git_ops/changelog.py
code_agents/git_ops/cherry_pick_advisor.py
code_agents/git_ops/commit_splitter.py
code_agents/git_ops/conflict_resolver.py
code_agents/git_ops/diff_preview.py
code_agents/git_ops/git_hooks.py
code_agents/git_ops/git_story.py
code_agents/git_ops/pr_describe.py
code_agents/git_ops/pr_split.py
code_agents/git_ops/pr_thread_agent.py
code_agents/git_ops/pr_writer.py
code_agents/git_ops/release_notes.py
code_agents/git_ops/semantic_merge.py
code_agents/integrations/__init__.py
code_agents/integrations/elasticsearch_client.py
code_agents/integrations/mcp_client.py
code_agents/integrations/redash_client.py
code_agents/integrations/slack_bot.py
code_agents/knowledge/__init__.py
code_agents/knowledge/adr_generator.py
code_agents/knowledge/claude_md_version.py
code_agents/knowledge/code_archaeology.py
code_agents/knowledge/code_example.py
code_agents/knowledge/code_explainer.py
code_agents/knowledge/code_ownership.py
code_agents/knowledge/code_translator.py
code_agents/knowledge/codebase_dialogue.py
code_agents/knowledge/codebase_nav.py
code_agents/knowledge/codebase_qa.py
code_agents/knowledge/cross_repo_linker.py
code_agents/knowledge/design_doc.py
code_agents/knowledge/explain_code.py
code_agents/knowledge/integration_scaffold.py
code_agents/knowledge/intent_compiler.py
code_agents/knowledge/inverse_coder.py
code_agents/knowledge/knowledge_base.py
code_agents/knowledge/knowledge_graph.py
code_agents/knowledge/lang_migration.py
code_agents/knowledge/meeting_compiler.py
code_agents/knowledge/migration_gen.py
code_agents/knowledge/onboarding_agent.py
code_agents/knowledge/pair_replay_coach.py
code_agents/knowledge/problem_solver.py
code_agents/knowledge/rag_context.py
code_agents/knowledge/runbook.py
code_agents/knowledge/spec_negotiator.py
code_agents/knowledge/teach_mode.py
code_agents/knowledge/team_knowledge.py
code_agents/knowledge/verbal_architect.py
code_agents/knowledge/workspace.py
code_agents/knowledge/workspace_graph.py
code_agents/knowledge/workspace_pr.py
code_agents/observability/__init__.py
code_agents/observability/auto_observability.py
code_agents/observability/batch_optimizer.py
code_agents/observability/cache_designer.py
code_agents/observability/call_chain.py
code_agents/observability/cognitive_monitor.py
code_agents/observability/concurrency_advisor.py
code_agents/observability/deadlock_detector.py
code_agents/observability/debug_engine.py
code_agents/observability/health_dashboard.py
code_agents/observability/incident_replay.py
code_agents/observability/leak_finder.py
code_agents/observability/live_tail.py
code_agents/observability/log_analyzer.py
code_agents/observability/log_investigator.py
code_agents/observability/log_to_code.py
code_agents/observability/nl_monitoring.py
code_agents/observability/otel.py
code_agents/observability/perf_pattern_checker.py
code_agents/observability/performance.py
code_agents/observability/pool_tuner.py
code_agents/observability/profiler.py
code_agents/observability/recon_debug.py
code_agents/observability/stack_decoder.py
code_agents/observability/telemetry.py
code_agents/observability/tracing_migration.py
code_agents/parsers/__init__.py
code_agents/parsers/generic_parser.py
code_agents/parsers/go_parser.py
code_agents/parsers/java_parser.py
code_agents/parsers/javascript_parser.py
code_agents/parsers/python_parser.py
code_agents/reporters/__init__.py
code_agents/reporters/env_health.py
code_agents/reporters/incident.py
code_agents/reporters/morning.py
code_agents/reporters/oncall.py
code_agents/reporters/sprint_reporter.py
code_agents/reporters/sprint_velocity.py
code_agents/reviews/__init__.py
code_agents/reviews/ai_review_personas.py
code_agents/reviews/arch_reviewer.py
code_agents/reviews/clone_detector.py
code_agents/reviews/code_audit.py
code_agents/reviews/code_review.py
code_agents/reviews/code_smell.py
code_agents/reviews/comment_audit.py
code_agents/reviews/comment_generator.py
code_agents/reviews/dead_code_eliminator.py
code_agents/reviews/import_optimizer.py
code_agents/reviews/naming_audit.py
code_agents/reviews/nl_refactor.py
code_agents/reviews/pattern_suggester.py
code_agents/reviews/review_autofix.py
code_agents/reviews/review_autopilot.py
code_agents/reviews/review_buddy.py
code_agents/reviews/review_checklist.py
code_agents/reviews/review_coach.py
code_agents/reviews/review_responder.py
code_agents/reviews/style_matcher.py
code_agents/reviews/tech_debt.py
code_agents/reviews/techdebt_scanner.py
code_agents/reviews/type_adder.py
code_agents/routers/__init__.py
code_agents/routers/agents_list.py
code_agents/routers/api_tools.py
code_agents/routers/argocd.py
code_agents/routers/atlassian_oauth_web.py
code_agents/routers/benchmark.py
code_agents/routers/code_nav.py
code_agents/routers/codebase_qa.py
code_agents/routers/completions.py
code_agents/routers/db.py
code_agents/routers/db_tools.py
code_agents/routers/debug.py
code_agents/routers/debug_tools.py
code_agents/routers/dep_upgrade.py
code_agents/routers/elasticsearch.py
code_agents/routers/git_ops.py
code_agents/routers/github_actions.py
code_agents/routers/grafana.py
code_agents/routers/jenkins.py
code_agents/routers/jira.py
code_agents/routers/k8s.py
code_agents/routers/kibana.py
code_agents/routers/knowledge_graph.py
code_agents/routers/mcp.py
code_agents/routers/migration_gen.py
code_agents/routers/oncall_summary.py
code_agents/routers/pipeline.py
code_agents/routers/postmortem.py
code_agents/routers/pr_describe.py
code_agents/routers/pr_review.py
code_agents/routers/redash.py
code_agents/routers/review.py
code_agents/routers/review_buddy.py
code_agents/routers/runbook.py
code_agents/routers/slack_bot.py
code_agents/routers/sprint_dashboard.py
code_agents/routers/telemetry.py
code_agents/routers/terraform.py
code_agents/routers/test_impact.py
code_agents/routers/test_tools.py
code_agents/routers/testing.py
code_agents/security/__init__.py
code_agents/security/acl_matrix.py
code_agents/security/audit_orchestrator.py
code_agents/security/compliance_report.py
code_agents/security/dependency_audit.py
code_agents/security/encryption_audit.py
code_agents/security/input_audit.py
code_agents/security/input_validator_gen.py
code_agents/security/license_audit.py
code_agents/security/owasp_checker.py
code_agents/security/owasp_scanner.py
code_agents/security/pci_scanner.py
code_agents/security/privacy_scanner.py
code_agents/security/rate_limit_audit.py
code_agents/security/secret_rotation.py
code_agents/security/secret_scanner.py
code_agents/security/session_audit.py
code_agents/security/vuln_chain.py
code_agents/security/vuln_fixer.py
code_agents/setup/__init__.py
code_agents/setup/setup.py
code_agents/setup/setup_env.py
code_agents/setup/setup_ui.py
code_agents/testing/__init__.py
code_agents/testing/benchmark.py
code_agents/testing/benchmark_regression.py
code_agents/testing/contract_testing.py
code_agents/testing/edge_case_suggester.py
code_agents/testing/error_immunizer.py
code_agents/testing/mock_builder.py
code_agents/testing/mutation_tester.py
code_agents/testing/mutation_testing.py
code_agents/testing/perf_proof.py
code_agents/testing/property_tests.py
code_agents/testing/regression_oracle.py
code_agents/testing/self_benchmark.py
code_agents/testing/spec_validator.py
code_agents/testing/test_darwinism.py
code_agents/testing/test_fixer.py
code_agents/testing/test_gap_finder.py
code_agents/testing/test_impact.py
code_agents/testing/test_style.py
code_agents/testing/visual_regression.py
code_agents/tools/__init__.py
code_agents/tools/_git_helpers.py
code_agents/tools/_pattern_matchers.py
code_agents/tools/auto_coverage.py
code_agents/tools/cursor_exporter.py
code_agents/tools/extension_repositories.py
code_agents/tools/onboarding.py
code_agents/tools/plugin_exporter.py
code_agents/tools/pr_preview.py
code_agents/tools/pre_push.py
code_agents/tools/refactor_planner.py
code_agents/tools/release.py
code_agents/tools/smart_commit.py
code_agents/tools/test_generator.py
code_agents/tools/vscode_extension.py
code_agents/tools/watch_mode.py
code_agents/tools/watchdog.py
code_agents/ui/__init__.py
code_agents/ui/browser_agent.py
code_agents/ui/command_advisor.py
code_agents/ui/live_preview.py
code_agents/ui/mindmap.py
code_agents/ui/screenshot_to_code.py
code_agents/ui/snippet_library.py
code_agents/ui/ui_frames.py
code_agents/ui/voice_input.py
code_agents/ui/voice_mode.py
code_agents/ui/voice_output.py
code_agents/webui/__init__.py
code_agents/webui/router.py
```

---

## Appendix Q — Complete `tests/**/*.py` inventory

**395** test modules.

```
tests/__init__.py
tests/cli/__init__.py
tests/cli/test_cli_analysis.py
tests/cli/test_cli_basics.py
tests/cli/test_cli_cicd.py
tests/cli/test_cli_completions_server.py
tests/cli/test_cli_config_curls.py
tests/cli/test_cli_dispatcher.py
tests/cli/test_cli_doctor.py
tests/cli/test_cli_git.py
tests/cli/test_cli_helpers.py
tests/cli/test_cli_init.py
tests/cli/test_cli_init_coverage.py
tests/cli/test_cli_reports.py
tests/cli/test_cli_tools_coverage_gaps.py
tests/cli/test_cli_tools_dispatch_imports.py
tests/cli/test_cli_tools_meta.py
tests/cli/test_cli_tools_rules_repos.py
tests/cli/test_cli_tools_sessions.py
tests/cli/test_cli_tools_sessions_extra.py
tests/test_acl_matrix.py
tests/test_acquirer_health.py
tests/test_action_log.py
tests/test_adr_generator.py
tests/test_agent_corrections.py
tests/test_agent_replay.py
tests/test_ai_review_personas.py
tests/test_api_changelog_gen.py
tests/test_api_compat.py
tests/test_api_design_checker.py
tests/test_api_doc_generator.py
tests/test_api_docs.py
tests/test_api_sync.py
tests/test_app_lifespan.py
tests/test_arch_drift_detector.py
tests/test_arch_reviewer.py
tests/test_argocd_client.py
tests/test_ast_helpers.py
tests/test_atlassian_oauth.py
tests/test_atlassian_oauth_extra.py
tests/test_atlassian_oauth_unit.py
tests/test_atlassian_oauth_web.py
tests/test_audit_orchestrator.py
tests/test_auto_coverage.py
tests/test_auto_observability.py
tests/test_autonomous_coverage.py
tests/test_backend.py
tests/test_backend_extra.py
tests/test_background_agent.py
tests/test_bash_tool.py
tests/test_batch_ops.py
tests/test_batch_optimizer.py
tests/test_benchmark.py
tests/test_benchmark_regression.py
tests/test_blame_investigator.py
tests/test_blame_unit.py
tests/test_branch_cleanup.py
tests/test_breaking_change_precog.py
tests/test_browser_agent.py
tests/test_bug_patterns.py
tests/test_cache_designer.py
tests/test_call_chain.py
tests/test_changelog.py
tests/test_changelog_gen.py
tests/test_chat.py
tests/test_chat_background.py
tests/test_chat_branch.py
tests/test_chat_clipboard.py
tests/test_chat_commands_cov.py
tests/test_chat_commands_extra.py
tests/test_chat_complexity.py
tests/test_chat_context_extra.py
tests/test_chat_history.py
tests/test_chat_history_extra.py
tests/test_chat_input.py
tests/test_chat_main.py
tests/test_chat_repl.py
tests/test_chat_response.py
tests/test_chat_response_cov.py
tests/test_chat_server.py
tests/test_chat_slash.py
tests/test_chat_slash_nav_cov.py
tests/test_chat_slash_ops_cov.py
tests/test_chat_slash_ops_unit.py
tests/test_chat_state.py
tests/test_chat_streaming.py
tests/test_chat_theme.py
tests/test_chat_tui_new.py
tests/test_chat_ui_cov.py
tests/test_chat_ui_extra.py
tests/test_chat_validation.py
tests/test_chat_welcome.py
tests/test_cherry_pick_advisor.py
tests/test_ci_self_heal.py
tests/test_claude_md_version.py
tests/test_cli_curls.py
tests/test_cli_doctor.py
tests/test_cli_doctor_extra.py
tests/test_cli_reports.py
tests/test_cli_server.py
tests/test_cli_server_git_cicd.py
tests/test_cli_skill.py
tests/test_cli_tools.py
tests/test_cli_undo.py
tests/test_cli_voice.py
tests/test_clone_detector.py
tests/test_clone_lineage.py
tests/test_code_archaeology.py
tests/test_code_audit.py
tests/test_code_example.py
tests/test_code_explainer.py
tests/test_code_ownership.py
tests/test_code_review.py
tests/test_code_smell.py
tests/test_code_translator.py
tests/test_codebase_dialogue.py
tests/test_codebase_nav.py
tests/test_codebase_qa.py
tests/test_codebase_sql.py
tests/test_cognitive_monitor.py
tests/test_collaboration.py
tests/test_command_advisor.py
tests/test_comment_audit.py
tests/test_comment_generator.py
tests/test_commit_splitter.py
tests/test_compile_check.py
tests/test_compile_check_unit.py
tests/test_complexity.py
tests/test_compliance_report.py
tests/test_concurrency_advisor.py
tests/test_confidence_scorer.py
tests/test_config_drift.py
tests/test_config_validator.py
tests/test_conflict_resolver.py
tests/test_connection_validator.py
tests/test_context_capsule.py
tests/test_context_manager.py
tests/test_contract_testing.py
tests/test_conversational_deploy.py
tests/test_cost_display.py
tests/test_coverage_100pct.py
tests/test_coverage_analysis.py
tests/test_coverage_boost.py
tests/test_coverage_cicd.py
tests/test_coverage_cmd.py
tests/test_coverage_final.py
tests/test_coverage_gaps.py
tests/test_coverage_reporters.py
tests/test_cross_repo_linker.py
tests/test_cursor_cli.py
tests/test_cursor_exporter.py
tests/test_db_client.py
tests/test_dead_code_eliminator.py
tests/test_dead_code_reaper.py
tests/test_deadcode.py
tests/test_deadlock_detector.py
tests/test_debug_engine.py
tests/test_decision_fatigue_reducer.py
tests/test_dep_decay_forecast.py
tests/test_dep_impact.py
tests/test_dep_upgrade.py
tests/test_dependency_audit.py
tests/test_dependency_graph.py
tests/test_design_doc.py
tests/test_diff_preview.py
tests/test_dockerfile_optimizer.py
tests/test_edge_case_suggester.py
tests/test_elasticsearch_client.py
tests/test_elasticsearch_client_full.py
tests/test_encryption_audit.py
tests/test_endpoint_generator.py
tests/test_endpoint_scanner.py
tests/test_env_cloner.py
tests/test_env_diff.py
tests/test_env_differ.py
tests/test_env_health.py
tests/test_env_loader.py
tests/test_error_immunizer.py
tests/test_es_client_unit.py
tests/test_explain_code.py
tests/test_extension_repositories.py
tests/test_feature_flags.py
tests/test_final_coverage.py
tests/test_git_client.py
tests/test_git_helpers.py
tests/test_git_hooks.py
tests/test_git_story.py
tests/test_gita_shlokas.py
tests/test_github_actions_client.py
tests/test_github_actions_router.py
tests/test_grafana_client.py
tests/test_headless_mode.py
tests/test_health_dashboard.py
tests/test_helm_debugger.py
tests/test_idempotency_audit.py
tests/test_impact_analysis.py
tests/test_impact_heatmap.py
tests/test_impact_unit.py
tests/test_implicit_api_docs.py
tests/test_import_optimizer.py
tests/test_incident.py
tests/test_incident_replay.py
tests/test_incident_timeline.py
tests/test_input_audit.py
tests/test_input_validator_gen.py
tests/test_integration_scaffold.py
tests/test_integration_wiring.py
tests/test_intent_compiler.py
tests/test_inverse_coder.py
tests/test_jacoco_parser.py
tests/test_jenkins_client.py
tests/test_jenkins_client_extra.py
tests/test_jira_client.py
tests/test_k8s_client.py
tests/test_k8s_generator.py
tests/test_kibana_client.py
tests/test_knowledge_base.py
tests/test_knowledge_graph.py
tests/test_lang_migration.py
tests/test_leak_finder.py
tests/test_license_audit.py
tests/test_live_preview.py
tests/test_live_tail.py
tests/test_load_test_gen.py
tests/test_log_analyzer.py
tests/test_log_investigator.py
tests/test_log_to_code.py
tests/test_logging_config.py
tests/test_mcp_client.py
tests/test_mcp_client_extra.py
tests/test_mcp_client_full.py
tests/test_mcp_gen.py
tests/test_meeting_compiler.py
tests/test_migration_gen.py
tests/test_mindmap.py
tests/test_mock_builder.py
tests/test_models.py
tests/test_morning.py
tests/test_mutation_tester.py
tests/test_mutation_testing.py
tests/test_naming_audit.py
tests/test_nl_monitoring.py
tests/test_nl_refactor.py
tests/test_notifications.py
tests/test_onboarding.py
tests/test_onboarding_agent.py
tests/test_oncall.py
tests/test_oncall_summary.py
tests/test_openai_errors.py
tests/test_orm_reviewer.py
tests/test_otel.py
tests/test_outage_topology.py
tests/test_owasp_checker.py
tests/test_owasp_scanner.py
tests/test_pair_mode.py
tests/test_pair_replay_coach.py
tests/test_parsers.py
tests/test_pattern_suggester.py
tests/test_pci_scanner.py
tests/test_perf_pattern_checker.py
tests/test_perf_proof.py
tests/test_performance.py
tests/test_pipeline.py
tests/test_plan_manager.py
tests/test_plugin_exporter.py
tests/test_pool_tuner.py
tests/test_postmortem.py
tests/test_postmortem_gen.py
tests/test_pr_describe.py
tests/test_pr_preview.py
tests/test_pr_review_client.py
tests/test_pr_split.py
tests/test_pr_thread_agent.py
tests/test_pr_writer.py
tests/test_pre_push.py
tests/test_privacy_scanner.py
tests/test_problem_solver.py
tests/test_profiler.py
tests/test_project_context.py
tests/test_project_scanner.py
tests/test_prompt_evolver.py
tests/test_property_tests.py
tests/test_qa_suite_generator.py
tests/test_query_optimizer.py
tests/test_question_parser.py
tests/test_questionnaire.py
tests/test_questionnaire_e2e.py
tests/test_rag_context.py
tests/test_rate_limit_audit.py
tests/test_rate_limiter.py
tests/test_recon_debug.py
tests/test_redash_client.py
tests/test_redash_client_full.py
tests/test_refactor_planner.py
tests/test_regression_oracle.py
tests/test_release.py
tests/test_release_notes.py
tests/test_repo_manager.py
tests/test_requirement_confirm.py
tests/test_response_optimizer.py
tests/test_response_verifier.py
tests/test_rest_to_grpc.py
tests/test_retry_analyzer.py
tests/test_review_autofix.py
tests/test_review_autopilot.py
tests/test_review_buddy.py
tests/test_review_checklist.py
tests/test_review_coach.py
tests/test_review_responder.py
tests/test_routers.py
tests/test_routers_coverage.py
tests/test_routers_extended.py
tests/test_routers_small.py
tests/test_rules_loader.py
tests/test_runbook.py
tests/test_sandbox.py
tests/test_sanity_checker.py
tests/test_schema_designer.py
tests/test_schema_evolution_sim.py
tests/test_schema_viz.py
tests/test_scope_creep_guard.py
tests/test_screenshot_to_code.py
tests/test_secret_rotation.py
tests/test_secret_scanner.py
tests/test_security_agent.py
tests/test_security_scanner.py
tests/test_self_benchmark.py
tests/test_self_tuning_ci.py
tests/test_semantic_merge.py
tests/test_session_audit.py
tests/test_session_scratchpad.py
tests/test_settlement_parser.py
tests/test_setup.py
tests/test_setup_extra.py
tests/test_setup_ui_extra.py
tests/test_skill_loader.py
tests/test_skill_marketplace.py
tests/test_slack_bot.py
tests/test_slack_bot_full.py
tests/test_slack_integration.py
tests/test_smart_commit.py
tests/test_smart_orchestrator.py
tests/test_snippet_library.py
tests/test_spec_negotiator.py
tests/test_spec_validator.py
tests/test_sprint_dashboard.py
tests/test_sprint_reporter.py
tests/test_sprint_velocity.py
tests/test_stack_decoder.py
tests/test_state_machine_validator.py
tests/test_stream.py
tests/test_structured_logging.py
tests/test_style_matcher.py
tests/test_subagent_dispatcher.py
tests/test_swarm_debugger.py
tests/test_teach_mode.py
tests/test_team_knowledge.py
tests/test_tech_debt.py
tests/test_techdebt_interest.py
tests/test_techdebt_scanner.py
tests/test_telemetry.py
tests/test_terminal_layout.py
tests/test_terraform_client.py
tests/test_terraform_explainer.py
tests/test_test_darwinism.py
tests/test_test_data_generator.py
tests/test_test_fixer.py
tests/test_test_gap_finder.py
tests/test_test_generator.py
tests/test_test_impact.py
tests/test_test_style.py
tests/test_testing_client.py
tests/test_testing_client_extra.py
tests/test_toil_predictor.py
tests/test_token_tracker.py
tests/test_tracing_migration.py
tests/test_txn_flow.py
tests/test_type_adder.py
tests/test_ui_frames.py
tests/test_usage_tracer.py
tests/test_velocity_anomaly.py
tests/test_velocity_predict.py
tests/test_verbal_architect.py
tests/test_visual_regression.py
tests/test_voice_input.py
tests/test_voice_mode.py
tests/test_voice_output.py
tests/test_vscode_extension.py
tests/test_vuln_chain.py
tests/test_vuln_fixer.py
tests/test_watch_mode.py
tests/test_watchdog.py
tests/test_wiring.py
tests/test_workspace.py
tests/test_workspace_graph.py
```

---

## Appendix R — `terminal/` TypeScript/TSX (no `node_modules`)

**90** files.

```
terminal/bin/chat.ts
terminal/bin/run.ts
terminal/dist/commands/agents.d.ts
terminal/dist/commands/chat.d.ts
terminal/dist/commands/doctor.d.ts
terminal/dist/commands/init.d.ts
terminal/dist/commands/start.d.ts
terminal/dist/commands/status.d.ts
terminal/dist/commands/stop.d.ts
terminal/dist/index.d.ts
terminal/src/chat/ChatApp.tsx
terminal/src/chat/ChatInput.tsx
terminal/src/chat/ChatOutput.tsx
terminal/src/chat/CommandApproval.tsx
terminal/src/chat/CommandPanel.tsx
terminal/src/chat/MarkdownRenderer.tsx
terminal/src/chat/ModeIndicator.tsx
terminal/src/chat/PlanMode.tsx
terminal/src/chat/Questionnaire.tsx
terminal/src/chat/QueuedMessages.tsx
terminal/src/chat/ResponseBox.tsx
terminal/src/chat/StatusBar.tsx
terminal/src/chat/StreamingResponse.tsx
terminal/src/chat/WelcomeMessage.tsx
terminal/src/chat/hooks/useAgenticLoop.ts
terminal/src/chat/hooks/useChat.ts
terminal/src/chat/hooks/useKeyBindings.ts
terminal/src/chat/hooks/useMessageQueue.ts
terminal/src/chat/hooks/useStreaming.ts
terminal/src/client/AgentService.ts
terminal/src/client/ApiClient.ts
terminal/src/client/BackgroundTasks.ts
terminal/src/client/ComplexityDetector.ts
terminal/src/client/ConfidenceScorer.ts
terminal/src/client/ContextTrimmer.ts
terminal/src/client/Orchestrator.ts
terminal/src/client/ServerMonitor.ts
terminal/src/client/SkillLoader.ts
terminal/src/client/SkillSuggester.ts
terminal/src/client/TagParser.ts
terminal/src/client/index.ts
terminal/src/client/types.ts
terminal/src/commands/agents.ts
terminal/src/commands/chat.tsx
terminal/src/commands/doctor.ts
terminal/src/commands/init.ts
terminal/src/commands/start.ts
terminal/src/commands/status.ts
terminal/src/commands/stop.ts
terminal/src/hooks/usePlan.ts
terminal/src/index.ts
terminal/src/slash/handlers/agents.ts
terminal/src/slash/handlers/config.ts
terminal/src/slash/handlers/nav.ts
terminal/src/slash/handlers/ops.ts
terminal/src/slash/handlers/session.ts
terminal/src/slash/index.ts
terminal/src/slash/registry.ts
terminal/src/slash/router.ts
terminal/src/state/Scratchpad.ts
terminal/src/state/SessionHistory.ts
terminal/src/state/TokenTracker.ts
terminal/src/state/config.ts
terminal/src/state/index.ts
terminal/src/state/store.ts
terminal/src/tui/AgentSelector.tsx
terminal/src/tui/DiffView.tsx
terminal/src/tui/FileTree.tsx
terminal/src/tui/FullScreenApp.tsx
terminal/src/tui/ProgressDashboard.tsx
terminal/src/tui/StatusBar.tsx
terminal/src/tui/ThinkingIndicator.tsx
terminal/src/tui/TokenBudgetBar.tsx
terminal/src/tui/index.ts
terminal/src/types/marked-terminal.d.ts
terminal/tests/background-tasks.test.ts
terminal/tests/client.test.ts
terminal/tests/commands.test.ts
terminal/tests/complexity.test.ts
terminal/tests/context-trimmer.test.ts
terminal/tests/hooks.test.ts
terminal/tests/orchestrator.test.ts
terminal/tests/skillsuggester.test.ts
terminal/tests/slash.test.ts
terminal/tests/state.test.ts
terminal/tests/tagparser.test.ts
terminal/tests/tui.test.ts
terminal/tests/welcome.test.ts
terminal/tsup.config.ts
terminal/vitest.config.ts
```

---

## Appendix S — What exhaustive inventories include (and exclude)

| Included in this document | *Not* included (cannot be a prompt—use source or `git clone`) |
|-----------------------------|----------------------------------------------------------------|
| Every **file path** in Appendices **M–R** (CLI keys, YAML, skills, `code_agents/**/*.py`, `tests/**/*.py`, `terminal` TS/TSX) | **Source code** inside those files |
| Architecture, routers, middleware, agent schema, build order | Every HTTP handler’s business logic and edge case |
| **179** CLI registry keys from `registry.py` | Aliases duplicated in prose (see `CommandEntry.aliases` in source) |

**Regenerate path lists** (e.g. after refactors) so this doc stays in sync:

```bash
cd /path/to/code-agents
find code_agents -name '*.py' -not -path '*/__pycache__/*' | sort > docs/_inv_code_agents_py.txt
find tests -name '*.py' -not -path '*/__pycache__/*' | sort > docs/_inv_tests_py.txt
find agents -name '*.md' -path '*/skills/*' | sort > docs/_inv_skills_md.txt
find terminal -type f \( -name '*.ts' -o -name '*.tsx' \) -not -path '*/node_modules/*' | sort > docs/_inv_terminal.txt
```

Then paste the contents of those `docs/_inv_*.txt` files into Appendices **P, Q, O, R** (or re-run the `docs/` maintenance script that updates `SUPER_PROMPT_CODE_AGENTS_ARCHITECTURE.md`).

---

## File path

`docs/SUPER_PROMPT_CODE_AGENTS_ARCHITECTURE.md`

**Approximate size:** ~2000+ lines (incl. full path inventories) — paste in **multiple** messages or use a **very large context** model; inventories alone are **~1,200** lines of paths.
