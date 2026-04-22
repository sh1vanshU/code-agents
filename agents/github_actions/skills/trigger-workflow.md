---
name: trigger-workflow
description: Trigger a GitHub Actions workflow and monitor until completion
---

## Before Starting

Check [Session Memory] for already-known values.
- **Reusable facts** (repo, workflow_id, branch): skip re-fetching if already in memory.
After each discovery, emit `[REMEMBER:key=value]` so it persists for future turns.

## Workflow

1. **List available workflows:**
   If [Session Memory] has `workflow_id`, skip this step.
   ```bash
   curl -sS "${BASE_URL}/github-actions/workflows"
   ```
   → Emit: `[REMEMBER:workflow_id=<id>]` `[REMEMBER:workflow_name=<name>]`

2. **Check recent runs** to avoid duplicates:
   ```bash
   curl -sS "${BASE_URL}/github-actions/workflows/${workflow_id}/runs?per_page=5"
   ```
   If an in-progress run exists for the same branch, report it instead of re-triggering.

3. **Trigger the workflow:**
   ```bash
   curl -sS -X POST ${BASE_URL}/github-actions/workflows/${workflow_id}/dispatch -H "Content-Type: application/json" -d '{"ref":"BRANCH","inputs":{}}'
   ```

4. **Poll for completion** (wait 10s, then check):
   ```bash
   curl -sS "${BASE_URL}/github-actions/workflows/${workflow_id}/runs?per_page=1"
   ```
   → Get the latest run_id, then poll:
   ```bash
   curl -sS "${BASE_URL}/github-actions/runs/${run_id}"
   ```
   Repeat until `status` is `completed`.

5. **On success:** Report conclusion, duration.
   → Emit: `[REMEMBER:run_id=<id>]` `[REMEMBER:run_status=completed]` `[REMEMBER:run_conclusion=success]`

6. **On failure:** Load [SKILL:debug-failure] for analysis.

## Definition of Done

- Workflow triggered and completed
- Status and conclusion reported to user
