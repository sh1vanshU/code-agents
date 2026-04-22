# Git Operations Agent

> Principal Release Engineer — branching strategy, release management, merge workflows, conflict resolution, and git history analysis

## Identity

| Field | Value |
|-------|-------|
| **Name** | `git-ops` |
| **YAML** | `git_ops.yaml` |
| **Backend** | `${CODE_AGENTS_BACKEND:cursor}` |
| **Model** | `${CODE_AGENTS_MODEL:Composer 2 Fast}` |
| **Permission** | `default` — ask before each action |

## Capabilities

- List branches and show current branch
- Show diff between branches (new commits on a feature branch vs main)
- Show commit log for a branch
- Check working tree status
- Push branches to remote origin
- Fetch latest from remote
- Release branch management (GitFlow + trunk-based workflows)
- Merge conflict detection, analysis, and resolution
- Git history analysis (blame, bisect, churn, contributor stats)
- Version tagging with semantic versioning and changelog generation
- Cherry-pick commits between branches with conflict handling

## Tools & Endpoints

- `GET /git/branches` — list all branches
- `GET /git/current-branch` — current branch name
- `GET /git/diff?base=main&head=feature-branch` — diff between branches
- `GET /git/log?branch=feature-branch&limit=20` — commit log
- `GET /git/status` — working tree status
- `POST /git/push` — push branch to remote: `{"branch": "feature-branch", "remote": "origin"}`
- `POST /git/fetch` — fetch latest from remote

## Skills

### Own Skills

| Skill | Description |
|-------|-------------|
| `branch-summary` | Show current branch, recent commits, diff vs main, status |
| `pre-push` | Pre-push checklist — status, diff, test results, then push |
| `diff-review` | Show diff between two branches with summary of changes |
| `safe-checkout` | Safe branch switch: show dirty files + diff, ask stash/commit/discard, then checkout |
| `release-branch` | Release branch management — create, cherry-pick, merge back (GitFlow + trunk-based) |
| `conflict-resolver` | Merge conflict detection, analysis, and resolution (auto-resolve simple, guide complex) |
| `git-history` | Git history analysis — blame, bisect, churn, contributor stats, timelines |
| `tag-release` | Version tagging with semantic versioning and changelog from conventional commits |
| `cherry-pick` | Cherry-pick commits between branches — preview, apply, resolve conflicts, verify build |

### Shared Engineering Skills

Shared skills from `agents/_shared/skills/` are also available to this agent: architecture, code-review, debug, deploy-checklist, documentation, incident-response, standup, system-design, tech-debt, testing-strategy.

## Usage

### Chat REPL
```bash
code-agents chat git-ops
```

### Inline Delegation (from another agent)
```
/git-ops <your prompt>
```

### Skill Invocation
```
/git-ops:branch-summary
/git-ops:pre-push
/git-ops:diff-review main feature-branch
/git-ops:release-branch
/git-ops:conflict-resolver
/git-ops:git-history
/git-ops:tag-release
/git-ops:cherry-pick
```

### API
```bash
curl -X POST http://localhost:8000/v1/agents/git-ops/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "your prompt"}], "stream": true}'
```

## Example Prompts

1. "Show the last 10 commits"
2. "What changed between main and this branch?"
3. "List all branches with their last commit date"
4. "Push this branch to origin after checking status"
5. "Create a release branch release/v1.2.0 from develop"
6. "Resolve merge conflicts between feature-auth and main"
7. "Who last changed each line of app.py? Run git blame"
8. "Tag this release as v2.0.0 with a changelog"
9. "Cherry-pick commit abc1234 from main to release/v1.1.x"

## Autorun Config

This agent has an `autorun.yaml` that defines allowed and blocked commands for auto-execution.

## Rules

Custom rules to guide this agent's behavior:

| Scope | Path |
|-------|------|
| Global | `~/.code-agents/rules/git-ops.md` |
| Project | `.code-agents/rules/git-ops.md` |

See `code-agents rules create --agent git-ops` to create rules.

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

