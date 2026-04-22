---
name: retry-failed
description: Retry a failed GitHub Actions workflow run
---

## Workflow

1. **Check run status:**
   ```bash
   curl -sS "${BASE_URL}/github-actions/runs/${run_id}"
   ```
   Verify it actually failed (conclusion != success).

2. **Retry the run:**
   ```bash
   curl -sS -X POST ${BASE_URL}/github-actions/runs/${run_id}/retry
   ```

3. **Monitor the retried run** using [SKILL:monitor-run].
