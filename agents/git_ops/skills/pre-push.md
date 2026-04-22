---
name: pre-push
description: Pre-push checklist — status, diff, test results, then push
---

## Workflow

1. **Check working tree status.** Ensure there are no uncommitted changes.
   ```bash
   curl -sS "${BASE_URL}/git/status"
   ```
   If there are uncommitted changes, warn the user and ask if they want to commit first.

2. **Get the current branch.**
   ```bash
   curl -sS "${BASE_URL}/git/current-branch"
   ```

3. **Show the diff vs main** so the user can review what will be pushed.
   ```bash
   curl -sS "${BASE_URL}/git/diff?base=main&head=current-branch"
   ```
   Summarize: files changed, lines added/removed.

4. **Show recent commits** that will be pushed.
   ```bash
   curl -sS "${BASE_URL}/git/log?branch=current-branch&limit=10"
   ```

5. **Confirm with the user** before pushing. Show:
   - Branch name
   - Number of commits to push
   - Summary of changes
   - Any warnings (large files, sensitive data, force-push risk)

6. **Fetch latest from remote** to check for conflicts.
   ```bash
   curl -sS -X POST "${BASE_URL}/git/fetch"
   ```

7. **Push the branch.**
   ```bash
   curl -sS -X POST "${BASE_URL}/git/push" \
     -H "Content-Type: application/json" \
     -d '{"branch": "current-branch", "remote": "origin"}'
   ```

8. **Report the push result:** success or failure, remote URL, and any warnings from git.
