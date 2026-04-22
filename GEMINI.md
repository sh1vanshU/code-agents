# Gemini Context — Project Context for Google Gemini

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
  cli/          — CLI entry point (~55 subcommands), helpers, shell completions
  chat/         — Chat REPL: input, streaming, slash commands, history, context, UI
    tui/        — Textual TUI (Claude Code-style interface)
  setup/        — Interactive setup wizard (7 steps)
  cicd/         — Integration clients: Jenkins, ArgoCD, Jira, Kibana, K8s, git, testing
  routers/      — FastAPI route handlers (17 routers, OpenAI-compatible)
  parsers/      — Multi-language AST parsers (Python/JS/TS/Java/Go)
  webui/        — Browser chat (vanilla HTML/CSS/JS, no build step)
  core/         — App, backend, config, env_loader, models, stream, logging, rate limiting
  agent_system/ — Memory, replay, corrections, skills, rules, orchestrator, scratchpad
  security/     — OWASP, PCI, encryption, ACL, compliance, privacy, secrets, vulns
  reviews/      — Code review, smell detection, dead code, imports, naming, tech debt
  testing/      — Mutation, contract, property, visual regression, benchmarks, specs
  observability/ — OTel, profiler, health dashboard, live tail, log analysis, tracing
  git_ops/      — Changelog, PR describe/split, hooks, blame, conflict resolver
  knowledge/    — Knowledge graph, RAG, code explainer, translator, onboarding, QA
  api/          — API docs, schema viz, endpoint generator, ORM reviewer
  devops/       — Background agents, batch ops, CI self-heal, config validator, env diff
  ui/           — Mindmap, voice, browser agent, screenshot-to-code, live preview
  domain/       — Payment tools, pair mode, sprint dashboard, dep impact, incidents

agents/<name>/  — 19 subfolders (18 agents + _shared)
  <name>.yaml     Agent config (lean system prompt + skill index)
  skills/*.md     Reusable workflows (154 total, loaded on demand)
  autorun.yaml    Per-agent command allowlist/blocklist

terminal/       — TypeScript terminal client (oclif + Ink)
  src/client/     API client, SSE streaming, server monitor
  src/state/      Zustand store, session history, token tracker
  src/chat/       Ink React components (ChatApp, StreamingResponse, CommandApproval)
  src/slash/      Slash command registry and handlers
  src/commands/   oclif CLI commands (chat, start, stop, status, agents, doctor)
  src/tui/        Full-screen TUI components (StatusBar, DiffView, SyntaxHighlight)
  tests/          79 tests (vitest + ink-testing-library)

tests/          — 3759 tests (163 files), pytest
initiater/      — Project quality audit system (14 rules)
```

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
- New agent tools/analysis modules: create in the appropriate `code_agents/<subdir>/`, keep lazy-loaded.
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
| `CODE_AGENTS_MAX_SESSION_TOKENS` | Stop agentic loop when exceeded | — |
| `TARGET_REPO_PATH` | Repo path (auto-detected from cwd) | — |

Per-agent overrides: `CODE_AGENTS_BACKEND_<AGENT>`, `CODE_AGENTS_MODEL_<AGENT>`. Full list in `.env.example`.

Integration vars (Jenkins, ArgoCD, Jira, Kibana, Slack, K8s, Redash, Elasticsearch) configured via `code-agents init --<integration>`.
