---
name: monitor-run
description: Monitor a running GitHub Actions workflow — poll status, show progress
---

## Workflow

1. **Get current run status:**
   ```bash
   curl -sS "${BASE_URL}/github-actions/runs/${run_id}"
   ```

2. **List jobs and their statuses:**
   ```bash
   curl -sS "${BASE_URL}/github-actions/runs/${run_id}/jobs"
   ```

3. **Report progress:** Show which jobs completed, which are in progress, which are queued.

4. **If still running:** Wait and re-check. Report updates.

5. **On completion:** Report final status, duration, and any failures.
   → Emit: `[REMEMBER:run_status=<status>]` `[REMEMBER:run_conclusion=<conclusion>]`
