---
name: debug-failure
description: Debug a failed GitHub Actions workflow run — fetch jobs, logs, identify root cause
---

## Workflow

1. **Get run details:**
   ```bash
   curl -sS "${BASE_URL}/github-actions/runs/${run_id}"
   ```

2. **List jobs in the run:**
   ```bash
   curl -sS "${BASE_URL}/github-actions/runs/${run_id}/jobs"
   ```
   Identify which job(s) failed.

3. **Fetch failed job logs:**
   ```bash
   curl -sS "${BASE_URL}/github-actions/runs/${run_id}/jobs/${job_id}/logs"
   ```

4. **Analyze the failure:**
   - Look for error messages, stack traces, test failures
   - Identify root cause (compilation error, test failure, timeout, auth issue, etc.)
   - Suggest fix

5. **Offer retry if transient:**
   If the failure looks transient (network timeout, rate limit, flaky test):
   ```bash
   curl -sS -X POST ${BASE_URL}/github-actions/runs/${run_id}/retry
   ```

## Definition of Done

- Root cause identified and explained to user
- Fix suggested or retry triggered
