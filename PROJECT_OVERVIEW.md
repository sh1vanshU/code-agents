# Code Agents — Project Overview

## What It Is

AI-powered code agent platform with 13 specialist agents exposed as OpenAI-compatible API endpoints. CLI-first (`code-agents init`, `code-agents chat`, `code-agents export`). Interactive chat REPL with agentic loop, CI/CD pipeline orchestration, and multi-backend support (Cursor, Claude API, Claude CLI). Includes 28 platform modules spanning intelligence, productivity, payment domain, migration, and observability layers.

**Stack:** Python 3.10+, FastAPI, Poetry, Textual (TUI), prompt-toolkit (REPL), Pydantic, httpx, PyYAML

---

## Agents (13)

| Agent | Purpose |
|-------|---------|
| Auto-Pilot | Full SDLC orchestration, pipeline orchestration, agent routing |
| Code Reasoning | Read-only code analysis, explanation, and codebase exploration |
| Code Writer | File generation and modification |
| Code Reviewer | Critical code review |
| Code Tester | Testing, debugging, test generation |
| Test Coverage | Coverage analysis with autonomous boost loop |
| Git Operations | Git workflows (branch, merge, rebase, diff) |
| Jenkins CI/CD | Build, deploy, AND ArgoCD verification orchestrator |
| ArgoCD Verify | Deployment verification and rollback |
| QA Regression | Full QA testing suite |
| Jira Ops | Ticket lifecycle, transitions, release tracking |
| Redash Query | Database queries via Redash |
| Security | Vulnerability scanning and compliance |

Each agent: YAML config + skill `.md` files (154 total skills). Lean system prompts (~500 tokens) with on-demand `[SKILL:name]` loading.

---

## Architecture

```
code_agents/
  cli/           — 45 CLI subcommands, shell completions
  chat/          — Chat REPL: input, streaming, slash commands, history, UI
    tui/         — Textual TUI (Claude Code-style interface)
  routers/       — 17 FastAPI routers (OpenAI-compatible /v1/chat/completions)
  setup/         — Interactive setup wizard (7 steps)
  cicd/          — Jenkins, ArgoCD, Jira, Kibana, K8s clients
  parsers/       — Multi-language AST parsers (Python/JS/TS/Java/Go)
  tools/         — Smart commit, release, refactor planner
  app.py         — FastAPI app, CORS, lifespan
  config.py      — AgentConfig, Settings, YAML + ${VAR} expansion
  backend.py     — Backend dispatcher (cursor CLI/HTTP, claude SDK, claude CLI)
  stream.py      — SSE streaming, build_prompt() for multi-turn
  knowledge_graph.py — Project structure index for AI context
  requirement_confirm.py — Spec-before-execution gate
  command_panel.py — Rich command panels for setup/config flows
  claude_md_version.py — CLAUDE.md version tracking and sync
  # Platform Intelligence
  mindmap.py, code_review.py, dep_impact.py, agent_corrections.py
  workspace_graph.py, workspace_pr.py, git_hooks.py, agent_replay.py
  rag_context.py, live_tail.py, pair_mode.py, background_agent.py
  # Developer Productivity
  api_docs.py, code_translator.py, profiler.py, schema_viz.py
  changelog.py, health_dashboard.py
  # Payment Gateway Domain
  txn_flow.py, recon_debug.py, pci_scanner.py, idempotency_audit.py
  state_machine_validator.py, acquirer_health.py, retry_analyzer.py
  load_test_gen.py, postmortem_gen.py, settlement_parser.py
  # Migration & Observability
  tracing_migration.py, otel.py, logging_config.py

agents/<name>/   — 13 agent folders + _shared
  <name>.yaml    — Agent config
  skills/*.md    — Reusable workflows (154 total)
  autorun.yaml   — Per-agent command allowlist/blocklist

extensions/      — IDE plugins & browser extensions
  vscode/        — VS Code extension (chat sidebar, 10 commands, SSE streaming)
  intellij/      — IntelliJ plugin (JCEF, Kotlin, all JetBrains IDEs)
  chrome/        — Chrome extension (side panel chat, GitHub/Jira context)
tests/           — 163 test files, 3759+ tests
```

---

## Key Features

- **3 Backends:** cursor (default), claude (API), claude-cli (subscription)
- **Multi-model routing:** Global + per-agent model override
- **Agent chaining:** `[DELEGATE:agent-name]` for auto-delegation
- **Skill system:** 154 `.md` workflows loaded on demand
- **Auto-run:** Safe commands execute without asking; per-agent allowlist/blocklist
- **Knowledge Graph:** Async-built AST index, blast radius calculation, context injection
- **Requirement Confirmation:** Spec-before-execution gate to prevent hallucination
- **Session scratchpad:** `[REMEMBER:key=value]` persists facts across turns
- **Confidence scoring:** 1-5 rating, auto-suggests delegation on low scores
- **Chat modes:** Chat / Plan / Edit (Shift+Tab cycling)
- **Message queue:** Type while agent processes (FIFO, auto-processed)
- **MCP integration:** Model Context Protocol plugin system (stdio + SSE)
- **Integrations:** Jenkins, ArgoCD, Jira, Confluence, Slack, Kibana, K8s, Redash, Elasticsearch
- **Platform Intelligence:** Mindmap, code review, dependency impact, agent corrections, workspace graph, agent replay, RAG context, live tail, pair mode, background agents
- **Developer Productivity:** API docs generation, code translation, profiling, schema visualization, changelog, health dashboard
- **Payment Domain:** Transaction flow tracing, reconciliation debugging, PCI scanning, idempotency audit, state machine validation, acquirer health, retry analysis, load test generation, postmortem generation, settlement parsing
- **Observability:** OpenTelemetry distributed tracing (`otel.py`), structured JSON logging (`logging_config.py`)
- **Migration Tooling:** Tracing migration from legacy to OpenTelemetry (`tracing_migration.py`)

---

## CLI Commands (45)

```
agents       audit        changelog    commit       completions  config
coverage     coverage_boost  curls     deadcode     diff         doctor
env_health   export       flags        help         incident     init         logs
migrate      morning      onboard      oncall_report  perf_baseline  pipeline
pr_preview   pre_push     qa_suite     release      repos        restart
review       rules        security     sessions     shutdown     sprint_report
sprint_velocity  standup  start        status       techdebt     test
update       version      version_bump watchdog
```

---

## Chat Slash Commands (57)

**Navigation:** /quit, /restart, /help, /open, /setup (command panel)
**Session:** /clear, /history, /resume, /delete-chat, /export
**Agent:** /agent, /agents, /rules, /skills, /tokens, /stats, /memory
**Operations:** /run, /bash, /btw, /repo, /superpower, /permissions, /plan, /confirm (requirement gate), /mcp
**Config:** /model, /backend, /theme
**Analysis:** /investigate, /blame, /generate-tests, /refactor, /deps, /pr-preview, /impact, /solve, /review-reply, /qa-suite, /kb
**Tools:** /pair, /coverage-boost, /mutate, /testdata, /profile, /compile, /verify, /style

---

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `CURSOR_API_KEY` / `ANTHROPIC_API_KEY` | Backend API keys | — |
| `CODE_AGENTS_BACKEND` | Global backend | cursor |
| `CODE_AGENTS_MODEL` | Global model | Composer 2 Fast |
| `CODE_AGENTS_CONTEXT_WINDOW` | Conversation pairs to keep | 5 |
| `CODE_AGENTS_MAX_LOOPS` | Max agentic loop rounds | 10 |
| `CODE_AGENTS_AUTO_RUN` | Auto-execute safe commands | true |
| `CODE_AGENTS_DRY_RUN` | Show commands without executing | false |
| `CODE_AGENTS_TUI` | Enable Textual TUI | false |
| `CODE_AGENTS_REQUIRE_CONFIRM` | Require spec before execution | true |
| `TARGET_REPO_PATH` | Repo path (auto-detected from cwd) | — |
| `JENKINS_URL` / `ARGOCD_URL` / `JIRA_URL` | Integration endpoints | — |

Per-agent overrides: `CODE_AGENTS_BACKEND_<AGENT>`, `CODE_AGENTS_MODEL_<AGENT>`

---

## Config Tiers

1. **Global:** `~/.code-agents/config.env` — API keys, server settings
2. **Per-repo:** `~/.code-agents/repos/{repo}/config.env` — Jenkins, ArgoCD, Jira
3. **Runtime:** Environment variables override both

---

## How It Works (Flow)

```
User types message
    → Smart Orchestrator suggests best agent
    → System context built (repo + rules + skills + memory + knowledge graph)
    → Requirement confirmation gate (spec-before-execution)
    → LLM call via backend (cursor/claude/claude-cli)
    → Response streamed with activity indicators
    → Post-response: confidence scoring, skill loading, delegation, questionnaire
    → Agentic loop: extract bash commands → auto-run or ask → feed output back
    → Repeat until no more commands
```

---

## Testing

```bash
poetry run pytest                          # 3759+ tests, 162 files
poetry run pytest tests/test_foo.py -x -v  # single file
poetry run python initiater/run_audit.py   # project quality audit (14 rules)
```

---

## Install

```bash
git clone git@github.com:code-agents-org/code-agents.git ~/.code-agents
bash ~/.code-agents/install.sh
cd /path/to/your-project && code-agents init && code-agents chat
code-agents export    # optional: generate CLAUDE.md/.cursorrules for external editors
```
