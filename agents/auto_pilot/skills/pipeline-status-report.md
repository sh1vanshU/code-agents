---
name: status-report
description: Full pipeline status report with all step results
---

## Workflow

1. **Fetch the current pipeline status.**
   ```bash
   curl -sS "${BASE_URL}/pipeline/{run_id}/status"
   ```

2. **Parse the pipeline state.** Extract:
   - Current step (connect, review, test, build, deploy, verify)
   - Status of each completed step (passed, failed, skipped)
   - Branch name, build job, deploy job, ArgoCD app
   - Build version (if build step completed)
   - Any error messages from failed steps

3. **Gather additional context** for completed steps:
   - Build step: build number, version, duration
   - Deploy step: target environment, deploy duration
   - Verify step: pod health, sync status

4. **Present a visual pipeline summary:**
   ```
   Pipeline Run: {run_id}
   Branch: feature/add-auth

   Step 1 — Connect:  DONE
   Step 2 — Review:   DONE
   Step 3 — Build:    DONE (build #854, version 1.2.3-abc)
   Step 4 — Deploy:   DONE (dev-stable)
   Step 5 — Verify:   IN PROGRESS
   Step 6 — Rollback: NOT NEEDED
   ```

5. **Highlight any blockers or failures.** If a step failed, show what went wrong and what options are available (retry, fix, rollback).

6. **Show timing information** if available: when each step started and how long it took.

7. **Recommend the next action:**
   - If in progress: what the next step is and what it requires
   - If blocked: what needs to be fixed
   - If complete: overall result and any post-pipeline actions

8. **If the pipeline is stuck**, suggest resolution steps or manual intervention options.
