<!-- version: 1.5.0 -->
# CLAUDE.md — Project Context for Claude Code

## What This Project Is

Code Agents is an AI-powered code agent platform with interactive chat and a CI/CD pipeline. 18 agents (19 subfolders incl. `_shared`) exposed as OpenAI-compatible endpoints. CLI-first: `code-agents init` per repo, `code-agents chat` for interactive use, `code-agents export` for Claude Code/Cursor integration.

## Dev Quickstart

```bash
# Install & run
git clone git@github.com:code-agents-org/code-agents.git ~/.code-agents && bash ~/.code-agents/install.sh
cd /path/to/your-project && code-agents init && code-agents start && code-agents chat

# Tests & audit
poetry run pytest                            # 3759 tests, 163 files
poetry run pytest tests/test_foo.py -x -v    # single file, stop on first fail
poetry run python initiater/run_audit.py     # project quality audit (14 rules)

# Useful during dev
code-agents help          # full CLI reference (~55 commands)
code-agents doctor        # diagnose env, integrations, git, build
code-agents status        # health + config
code-agents agents        # list all 18 agents
code-agents export        # export CLAUDE.md / .cursorrules for external editors
```

## Architecture Overview

```
code_agents/
  # --- Core infrastructure ---
  core/           — App, config, backend, streaming, models, env, logging, rate limiting
  agent_system/   — Agent memory, skills, orchestration, planning, questionnaire
  routers/        — FastAPI route handlers (17 routers, OpenAI-compatible)

  # --- Feature modules ---
  security/       — OWASP, PCI, encryption, compliance, vulnerability scanning (14 modules)
  reviews/        — Code review, smell, tech debt, style, imports, dead code (15 modules)
  testing/        — Mutation testing, benchmarks, property tests, mocks (14 modules)
  observability/  — Tracing, profiling, debugging, log analysis, health (15 modules)
  git_ops/        — Git hooks, PR management, changelogs, blame, diffs (10 modules)
  knowledge/      — Code intelligence, docs, migration, RAG, onboarding (23 modules)
  api/            — API docs, compatibility, schema tools, ORM review (10 modules)
  devops/         — CI self-heal, pipelines, environments, background agents (10 modules)
  ui/             — Voice, browser, screenshots, mindmaps, snippets (10 modules)
  domain/         — Payments, sprint mgmt, collaboration, notifications (22 modules)

  # --- Pre-existing packages ---
  cli/            — CLI entry point (~55 subcommands), helpers, shell completions
  chat/           — Chat REPL: input, streaming, slash commands, history, context, UI
    tui/          — Textual TUI (Claude Code-style interface)
  setup/          — Interactive setup wizard (7 steps)
  cicd/           — Integration clients: Jenkins, ArgoCD, Jira, Kibana, K8s, git, testing
  parsers/        — Multi-language AST parsers (Python/JS/TS/Java/Go)
  webui/          — Browser chat (vanilla HTML/CSS/JS, no build step)
  analysis/       — Static analysis: security, complexity, deadcode, bugs (12 modules)
  generators/     — Code generators: API docs, changelog, tests, data (5 modules)
  integrations/   — External clients: Elasticsearch, MCP, Redash, Slack (4 modules)
  reporters/      — Reports: env health, incidents, morning, oncall, sprint (6 modules)
  tools/          — Dev tools: coverage, commit, release, refactor, watch (12 modules)

agents/<name>/    — 19 subfolders (18 agents + _shared)
  <name>.yaml       Agent config (lean system prompt + skill index)
  skills/*.md       Reusable workflows (154 total, loaded on demand)
  autorun.yaml      Per-agent command allowlist/blocklist

tests/            — 3759 tests (163 files), pytest
initiater/        — Project quality audit system (14 rules)
```

**Import paths**: All imports use the subdirectory path directly (e.g. `from code_agents.core.backend import run_agent`). No backward-compat stubs — the flat `code_agents/*.py` files were removed.

### TypeScript Terminal (`terminal/`)
```
terminal/                         # Hybrid TS client consuming Python server over HTTP/SSE
├── bin/run.ts                    # oclif CLI entry (tsx)
├── src/
│   ├── client/                   # ApiClient (SSE async generator), AgentService, ServerMonitor
│   ├── state/                    # Zustand store, SessionHistory, TokenTracker, Scratchpad, config
│   ├── chat/                     # Ink components: ChatApp, Input, Output, StreamingResponse
│   │   └── hooks/                # useChat, useStreaming, useKeyBindings, useAgenticLoop
│   ├── slash/                    # Slash command registry + handlers (nav, session, agents, ops, config)
│   ├── commands/                 # oclif commands: chat, start, stop, status, agents, doctor, init
│   └── tui/                      # Rich TUI: FullScreenApp, StatusBar, DiffView, FileTree
└── tests/                        # 79 tests (vitest)
```

**Architecture**: Two processes — Python server on localhost:8000, TypeScript terminal as HTTP/SSE client.
**Launch**: `npx tsx terminal/bin/run.ts chat` or `code-agents chat --ts`
**Session interop**: Both Python and TS read/write `~/.code-agents/chat_history/*.json` (same format).

## Key Patterns

### Backend & Routing
- **3 backends**: `cursor` (default), `claude` (API), `claude-cli` (subscription). Per-agent override via `CODE_AGENTS_BACKEND_<AGENT>`.
- **Multi-model routing**: Global `CODE_AGENTS_MODEL` + per-agent `CODE_AGENTS_MODEL_<AGENT>`.
- **OpenAI-compatible API**: All agents exposed as `/v1/chat/completions` endpoints.

### Agent System
- **Skills**: 154 skills in `agents/<name>/skills/*.md`. Lean system prompts (~500 tokens) + on-demand `[SKILL:name]` loading. Cross-agent: `[SKILL:jenkins-cicd:build]`.
- **Agent chaining**: `[DELEGATE:agent-name]` tag for auto-delegation.
- **Agent memory**: Persistent learnings at `~/.code-agents/memory/<agent>.md`, injected into system prompt.
- **Auto-run**: Safe commands auto-execute in agentic loop. Per-agent `autorun.yaml`. `CODE_AGENTS_AUTO_RUN=false` to disable.
- **Confidence scoring**: Rates response confidence 1-5, auto-suggests delegation to specialist on low scores.
- **Session scratchpad**: `/tmp/code-agents/<session>/state.json` persists discovered facts across turns. Agents write via `[REMEMBER:key=value]` tags, read via `[Session Memory]` block injected into system prompt. Auto-cleanup after 1 hour.
- **Upfront questionnaire**: Agents emit multiple `[QUESTION:key]` tags for ambiguous requests → shown as tabbed wizard with Enter-to-submit. Answers injected back for execution.
- **Knowledge graph**: Async-built AST index of project structure, blast radius calculation, injected as context for informed code changes.
- **Requirement confirmation**: Spec-before-execution gate (`requirement_confirm.py`) prevents hallucination on ambiguous tasks. Toggle with `CODE_AGENTS_REQUIRE_CONFIRM`.

### Chat REPL
- **prompt_toolkit input**: Fixed bottom bar, dropdown autocomplete, graceful fallback to `input()`.
- **Mode cycling**: Shift+Tab cycles Chat / Plan / Accept-edits. `/plan` for full plan lifecycle.
- **Message queue**: Type while agent processes — FIFO queue, auto-processed on finish.
- **Slash commands**: `/agent` switches, `/<agent> <prompt>` delegates, `/<agent>:<skill>` invokes skills.
- **Session persistence**: Auto-save to `~/.code-agents/chat_history/`. Resume with `/resume`.

### Safety & Limits
- **Dry-run mode**: `CODE_AGENTS_DRY_RUN=true` shows commands without executing.
- **Token guard**: `CODE_AGENTS_MAX_SESSION_TOKENS` stops loop when exceeded.
- **Smart context trimming**: `CODE_AGENTS_CONTEXT_WINDOW` (default 5) auto-trims conversation, preserves system prompt + code blocks.
- **Rate limiting**: Per-user RPM + daily token budgets.

### Integrations
- **CI/CD**: Jenkins (build/deploy), ArgoCD (sync/rollback), 6-step pipeline state machine.
- **Jira/Confluence**: Issue management, transitions, Confluence pages via jira-ops agent.
- **Slack**: Webhook notifications + Bot Bridge (DMs/mentions -> agent delegation -> thread reply).
- **MCP**: Model Context Protocol plugin system (stdio + SSE transport, JSON-RPC).
- **Kibana/Elasticsearch**: Log search, filtering, tail across services.

### IDE Extensions (`extensions/`)
- **VS Code**: WebviewViewProvider sidebar, 10 commands, SSE streaming, theme-aware. `extensions/vscode/`
- **IntelliJ**: JCEF tool window, Kotlin, works in all JetBrains IDEs. `extensions/intellij/`
- **Chrome**: Side panel chat, GitHub/Jira context extraction. `extensions/chrome/`
- All three share the same webview UI codebase (`extensions/vscode/webview-ui/`).
- Build all: `cd extensions && make all`. Test: `make test`. Package: `make package`.

## Development Guidelines

### Code Conventions
- **Python 3.10+**, managed with Poetry.
- **FastAPI** for all HTTP endpoints; Pydantic models for request/response.
- **Lazy loading**: Heavy modules (security scanner, QA suite, voice, pair mode, etc.) only import when invoked. Follow this pattern for new features.
- **Two-tier config**: Global (`~/.code-agents/`) + per-repo (`.code-agents/` or `.env.code-agents`). `env_loader.py` handles merge order.
- **Two-tier rules**: Global + project rules in `rules_loader.py`, auto-refresh every message.

### When Adding Code
- New CLI commands go in `code_agents/cli/cli.py` as subcommands.
- New slash commands go in `chat/chat_slash.py` (handler registry pattern).
- New API endpoints go in `code_agents/routers/` as a new or existing router, registered in `app.py`.
- New agent tools/analysis modules: create in `code_agents/`, keep lazy-loaded.
- Tests go in `tests/test_<module>.py` — match the module name.

### When Adding a New Agent
1. Create `agents/<name>/` with `<name>.yaml` and `README.md`
2. Create `agents/<name>/skills/` with skill `.md` files (YAML frontmatter + workflow body)
3. Add to `agents/auto-pilot/auto-pilot.yaml` system prompt (agent routing)
4. Add to `AGENTS.md` and `README.md` agents table
5. Add role to `AGENT_ROLES` and welcome to `AGENT_WELCOME` in `code_agents/chat/chat.py`

### Testing
- Run all: `poetry run pytest`
- Run one file: `poetry run pytest tests/test_backend.py -x -v`
- Tests are pure unit tests with mocks — no external services needed.
- Every module should have a corresponding test file.
- Test files follow `test_<module>.py` naming.

## Environment Variables (Key Ones)

| Variable | Purpose | Default |
|---|---|---|
| `CURSOR_API_KEY` / `ANTHROPIC_API_KEY` | Backend API keys | — |
| `CODE_AGENTS_BACKEND` | Global backend | `cursor` |
| `CODE_AGENTS_MODEL` | Global model | `Composer 2 Fast` |
| `CODE_AGENTS_CONTEXT_WINDOW` | Conversation pairs to keep | `5` |
| `CODE_AGENTS_MAX_LOOPS` | Max agentic loop rounds | `10` |
| `CODE_AGENTS_AUTO_RUN` | Auto-execute safe commands | `true` |
| `CODE_AGENTS_DRY_RUN` | Show commands without executing | `false` |
| `HOST` / `PORT` | Server bind | `0.0.0.0:8000` |
| `CODE_AGENTS_TUI` | Enable Textual TUI interface | `false` |
| `CODE_AGENTS_REQUIRE_CONFIRM` | Require spec confirmation before execution | `true` |
| `TARGET_REPO_PATH` | Repo path (auto-detected from cwd) | — |

Per-agent overrides: `CODE_AGENTS_BACKEND_<AGENT>`, `CODE_AGENTS_MODEL_<AGENT>`. Full list in `.env.example`.

Integration vars (Jenkins, ArgoCD, Jira, Kibana, Slack, K8s, Redash, Elasticsearch) configured via `code-agents init --<integration>`.

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"` to keep the graph current
