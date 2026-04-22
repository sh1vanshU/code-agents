---
name: branch-summary
description: Show current branch, recent commits, diff vs main, status
---

## Workflow

1. **Get the current branch name.**
   ```bash
   curl -sS "${BASE_URL}/git/current-branch"
   ```

2. **Check working tree status** for uncommitted changes.
   ```bash
   curl -sS "${BASE_URL}/git/status"
   ```
   Report: staged changes, unstaged changes, untracked files.

3. **Get recent commit log** for the current branch.
   ```bash
   curl -sS "${BASE_URL}/git/log?branch=current-branch&limit=10"
   ```
   Show: commit hash (short), author, date, and message for each.

4. **Get diff vs main** to see what has changed on this branch.
   ```bash
   curl -sS "${BASE_URL}/git/diff?base=main&head=current-branch"
   ```

5. **Summarize the diff:** count of files changed, lines added, lines removed. List the changed files grouped by type (source, tests, config, docs).

6. **Present a compact summary:**
   ```
   Branch:          feature/add-auth
   Commits ahead:   5
   Files changed:   8 (4 source, 3 tests, 1 config)
   Lines:           +142 / -37
   Uncommitted:     2 modified, 1 untracked
   ```

7. **Flag any concerns:** uncommitted changes that should be committed, large diffs that may need splitting, or merge conflicts with main.
