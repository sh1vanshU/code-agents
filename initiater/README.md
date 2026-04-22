# Initiater — Project Quality Audit System

Initiater is a rule-based audit system that checks the Code Agents project against a set of quality standards. It uses rule files (plain markdown checklists) and an LLM to evaluate compliance, producing actionable reports.

## Quick Start

```bash
# Audit all dimensions (requires the Code Agents server running on localhost:8000)
poetry run python initiater/run_audit.py

# Audit specific dimensions
poetry run python initiater/run_audit.py --rules documentation,workflow,testing

# Output as JSON
poetry run python initiater/run_audit.py --format json

# Use Anthropic API directly (no server needed)
ANTHROPIC_API_KEY=sk-ant-... poetry run python initiater/run_audit.py --backend anthropic

# No LLM — dimensions + repo snapshot only (CI-friendly when server is down)
poetry run python initiater/run_audit.py --skip-llm

# Fail the command if the LLM cannot be reached (default is to print offline summary and exit 0)
poetry run python initiater/run_audit.py --require-llm
```

## How It Works

1. **Rule files** (`rules/*.md`) define checklists for each quality dimension (testing, security, documentation sync, etc.)
2. **`run_audit.py`** reads the rules, scans the project for relevant files, and builds a structured prompt
3. An LLM evaluates the project state against each rule and returns pass/fail/warning per item (unless `--skip-llm` or the LLM is unreachable — then an **offline** summary is printed by default)
4. Results are printed as a markdown or JSON report

## Adding Rules

Create a new `.md` file in `rules/` following this format:

```markdown
---
dimension: my-dimension
severity: warning
---

# My Dimension

## Purpose
Why this matters.

## Rules
- [ ] Rule 1
- [ ] Rule 2

## Verification
How to check (commands, file patterns, etc.)

## References
Relevant project files.
```

Severity levels: `critical` (must fix), `warning` (should fix), `info` (nice to have).

## Rule Files

| File | What it checks |
|---|---|
| `workflow.md` | New agent checklist: YAML, router, README, Agents.md all in sync |
| `documentation.md` | README, Agents.md, and router list the same agents; API docs match endpoints |
| `testing.md` | Test files exist; pytest configured; CI runs tests |
| `security.md` | No hardcoded secrets; env vars validated |
| `environment.md` | .env.example covers required vars; defaults documented |
| `repo-map.md` | Project structure in README matches actual files |
| `code-style.md` | Formatting, type hints, imports |
| `logging.md` | Structured logging; appropriate levels |
| `debugging.md` | Diagnostics endpoint; verify script |
| `collaboration.md` | Contributing guide; PR process |
| `cross-platform.md` | Docker; OS-agnostic paths; shebangs |
| `decision.md` | Architecture decisions documented |
| `handoff.md` | Onboarding; session management |
| `vision.md` | Project goals and non-goals |

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

