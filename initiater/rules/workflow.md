---
dimension: workflow
severity: critical
---

# Workflow — Agent Creation & Cross-File Sync

## Purpose
Every time a new agent is added, multiple files must be updated in lockstep. Missing one creates confusion for users who discover agents in one place but not another. This checklist ensures nothing is missed.

## Rules
- [ ] Every agent in `agents/*/` (excluding `_shared`) is listed in `auto-pilot.yaml` system prompt specialists
- [ ] Every agent is listed in README.md "Included Agents" table
- [ ] Every agent is listed in README.md "Project Structure" tree
- [ ] Every agent is documented in Agents.md with its own section
- [ ] `auto-pilot.yaml` specialists list matches actual agent directories
- [ ] Agents.md "Maintenance" section is up to date with the sync checklist
- [ ] New agent YAML follows the same field ordering as existing agents
- [ ] CLI tab-completions include the agent name (`cli_completions.py`)

## Verification
```bash
# List all active agent directories
ls -d agents/*/ | grep -v _shared | sed 's|agents/||;s|/||'

# Check auto-pilot system prompt mentions each agent
grep -oP '[a-z]+-[a-z]+' agents/auto_pilot/auto_pilot.yaml | sort -u

# Check README.md Included Agents table
grep '`code-\|auto-pilot\|jenkins\|argocd\|git-ops\|jira\|redash\|security\|test-coverage\|qa-regression' README.md

# Check Agents.md sections
grep '^## ' AGENTS.md
```

## References
- `agents/*/` (agent directories)
- `agents/auto_pilot/auto_pilot.yaml` (orchestrator with specialist list)
- `README.md` (Included Agents table, Project Structure)
- `AGENTS.md`
- `code_agents/cli/cli_completions.py`
