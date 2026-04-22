# Jira & Confluence Agent

> Principal Project Engineer who owns the ticket lifecycle, sprint planning, release tracking, and Confluence documentation.

## Identity

| Field | Value |
|-------|-------|
| **Name** | `jira-ops` |
| **YAML** | `jira_ops.yaml` |
| **Backend** | `${CODE_AGENTS_BACKEND:cursor}` |
| **Model** | `${CODE_AGENTS_MODEL:Composer 2 Fast}` |
| **Permission** | `default` — ask before each action |

## Capabilities

- Read Jira tickets: summary, status, assignee, acceptance criteria, subtasks, labels
- Search issues with JQL queries
- Create new issues and subtasks
- Transition tickets between statuses (To Do -> In Progress -> Done)
- Add comments with implementation details or status updates
- Fetch Confluence pages by ID or search by space and title
- Extract requirements from wiki documentation
- Sprint management: velocity tracking, burndown analysis, sprint health checks
- Release tracking: fixVersion readiness, deploy gates, branch merge cross-reference
- Daily standup generation: per-person done/doing/blocked with CI/CD status
- Ticket dependency mapping: graph construction, circular detection, critical path
- SDLC gate validation: verify ticket completeness before starting work
- Auto-comment SDLC progress on tickets after each pipeline step
- Generate release notes grouped by type with authors and PR links
- Post-deployment updates: transition to Done, add deploy details, labels

## Tools & Endpoints

### Jira API
- `GET /jira/issue/{key}` — get ticket details (summary, status, assignee, acceptance criteria, subtasks)
- `POST /jira/search` — JQL search: `{"jql": "project = KEY AND status = 'In Progress'", "max_results": 50}`
- `POST /jira/issue` — create issue: `{"project": "KEY", "summary": "...", "description": "...", "issue_type": "Task"}`
- `POST /jira/issue/{key}/comment` — add comment: `{"body": "comment text"}`
- `GET /jira/issue/{key}/transitions` — get available transitions
- `POST /jira/issue/{key}/transition` — transition: `{"transition_id": "31", "comment": "optional"}`

### Confluence API
- `GET /jira/confluence/{page_id}` — get wiki page by ID
- `POST /jira/confluence/search` — CQL search: `{"cql": "space = 'TEAM' and title ~ 'HLD'"}`

## Skills

### Own Skills

| Skill | Description |
|-------|-------------|
| `read-ticket` | Fetch ticket, extract acceptance criteria, linked pages, requirements |
| `create-ticket` | Create Jira subtask with implementation details |
| `update-status` | Get transitions, transition ticket, add comment with results |
| `read-wiki` | Fetch Confluence page by ID or search by space+title, extract content |
| `sprint-manager` | Sprint management — list sprints, track velocity, burndown analysis, sprint health |
| `release-tracker` | Release tracking — tickets by fixVersion, readiness check, deploy gate |
| `standup-report` | Daily standup generation — yesterday done, today planned, blockers, per-person |
| `dependency-map` | Ticket dependency mapping — graph, circular detection, critical path, unblocking order |
| `ticket-validate` | SDLC gate — validate ticket has AC, assignee, correct status, linked docs, story points |
| `progress-updater` | Auto-comment SDLC progress on Jira ticket — status transitions after each step |
| `release-notes` | Generate release notes — group by type, include authors and PR links, markdown output |
| `post-deploy-update` | Post-deployment Jira update — transition to Done, add deploy details, update fixVersion |

### Shared Engineering Skills

Shared skills from `agents/_shared/skills/` are also available to this agent: architecture, code-review, debug, deploy-checklist, documentation, incident-response, standup, system-design, tech-debt, testing-strategy.

## Usage

### Chat REPL
```bash
code-agents chat jira-ops
```

### Inline Delegation (from another agent)
```
/jira-ops <your prompt>
```

### Skill Invocation
```
/jira-ops:read-ticket TEAM-1234
/jira-ops:create-ticket <your prompt>
/jira-ops:update-status TEAM-1234
/jira-ops:read-wiki <your prompt>
/jira-ops:sprint-manager
/jira-ops:release-tracker v1.2.0
/jira-ops:standup-report
/jira-ops:dependency-map
/jira-ops:ticket-validate TEAM-1234
/jira-ops:progress-updater TEAM-1234
/jira-ops:release-notes v1.2.0
/jira-ops:post-deploy-update TEAM-1234
```

### API
```bash
curl -X POST http://localhost:8000/v1/agents/jira-ops/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "your prompt"}], "stream": true}'
```

## Example Prompts

1. "Read ticket TEAM-1234 and summarize the acceptance criteria"
2. "Search for all open bugs in project TEAM"
3. "Move TEAM-1234 to In Progress and add a comment"
4. "Find the HLD page in the TEAM Confluence space"
5. "Create a subtask for TEAM-1234: implement retry logic"
6. "Show sprint health and burndown for the current sprint"
7. "Is release v1.2.0 ready to deploy? Check all tickets"
8. "Generate today's standup report for the team"
9. "Map dependencies for all tickets in the current sprint"
10. "Validate TEAM-1234 before starting implementation"
11. "Generate release notes for v1.2.0"
12. "Update TEAM-1234 after deploying to staging"

## Autorun Config

This agent has an `autorun.yaml` that defines allowed and blocked commands for auto-execution.

## Rules

Custom rules to guide this agent's behavior:

| Scope | Path |
|-------|------|
| Global | `~/.code-agents/rules/jira-ops.md` |
| Project | `.code-agents/rules/jira-ops.md` |

See `code-agents rules create --agent jira-ops` to create rules.

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

