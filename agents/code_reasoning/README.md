# Code Reasoning Agent

> Principal Architect who analyzes codebases, designs solutions, traces data flows, and documents architecture. READ-ONLY — never modifies code.

## Identity

| Field | Value |
|-------|-------|
| **Name** | `code-reasoning` |
| **Role** | Principal Architect |
| **YAML** | `code_reasoning.yaml` |
| **Backend** | `${CODE_AGENTS_BACKEND:cursor}` |
| **Model** | `${CODE_AGENTS_MODEL:Composer 2 Fast}` |
| **Permission** | `default` — read-only enforced in system prompt + `--mode ask` (not `bypassPermissions`, which maps to cursor-agent `--force`) |

## Capabilities

- Explain architecture, design patterns, and data flows
- Trace execution paths end-to-end ("what happens when X calls Y?")
- Compare approaches with pros/cons and complexity trade-offs
- Plan testing strategies and identify edge cases
- Map dependencies between modules, services, and APIs
- Analyze codebase for a requirement and output structured LLD
- Assess impact of proposed changes across modules and tests

## Boundaries

This agent will **not**:

- Modify any files (read-only by design)
- Write new code or tests (delegate to `code-writer` or `code-tester`)
- Execute builds, deployments, or CI/CD (delegate to `jenkins-cicd`)
- Run database queries (delegate to `redash-query`)
- Make git changes (delegate to `git-ops`)

## Tools & Endpoints

Uses the LLM directly — no API endpoints. This agent is read-only and works entirely through code reading and analysis.

## Skills

### Own Skills

| Skill | Description |
|-------|-------------|
| `explain` | Explain architecture, design patterns, and data flows in the codebase |
| `trace-flow` | Trace a request or data flow end-to-end through the system |
| `compare` | Compare two approaches, analyze trade-offs and complexity |
| `system-analysis` | Analyze codebase for a requirement — identify files, data flows, dependencies, and tests needed |
| `impact-analysis` | Trace a proposed change — affected modules, broken tests, API changes, downstream services, risk level |
| `architecture-review` | Review system architecture — layers, components, dependencies, API contracts, deployment topology |
| `dependency-map` | Map module/service dependencies — imports, API calls, shared state. Build dependency graph. Identify circular deps, tight coupling, SPOFs |
| `tech-debt-assessment` | Quantify tech debt — TODOs, deprecated APIs, duplication, complexity, missing tests. Prioritized list with effort estimates |
| `capacity-planning` | Analyze system capacity — load patterns, bottlenecks, scaling limits. Recommend scaling, caching, sharding, async processing |
| `solution-design` | Design solutions — evaluate approaches, compare trade-offs, recommend pattern, sequence diagrams, API design |

### Shared Engineering Skills

Shared skills from `agents/_shared/skills/` are also available to this agent: architecture, code-review, debug, deploy-checklist, documentation, incident-response, standup, system-design, tech-debt, testing-strategy.

## Usage

### Chat REPL
```bash
code-agents chat code-reasoning
```

### Inline Delegation (from another agent)
```
/code-reasoning <your prompt>
```

### Skill Invocation
```
/code-reasoning:explain <your prompt>
/code-reasoning:trace-flow <your prompt>
/code-reasoning:system-analysis <your prompt>
/code-reasoning:impact-analysis <your prompt>
/code-reasoning:architecture-review <your prompt>
/code-reasoning:dependency-map <your prompt>
/code-reasoning:tech-debt-assessment <your prompt>
/code-reasoning:capacity-planning <your prompt>
/code-reasoning:solution-design <your prompt>
```

### API
```bash
curl -X POST http://localhost:8000/v1/agents/code-reasoning/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "your prompt"}], "stream": true}'
```

## Example Prompts

1. "Explain the authentication flow in this project"
2. "How does the payment processing pipeline work?"
3. "What design patterns are used in the routers?"
4. "Analyze the codebase for adding a webhook feature — give me a structured LLD"
5. "What would break if I change the User model schema?"

## Autorun Config

This agent has an `autorun.yaml` that defines allowed and blocked commands for auto-execution.

## Rules

Custom rules to guide this agent's behavior:

| Scope | Path |
|-------|------|
| Global | `~/.code-agents/rules/code-reasoning.md` |
| Project | `.code-agents/rules/code-reasoning.md` |

See `code-agents rules create --agent code-reasoning` to create rules.

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

