---
name: diff-review
description: Show diff between two branches with summary of changes
---

## Workflow

1. **Identify the two branches to compare.** Ask the user or use defaults: base = `main`, head = current branch.

2. **Fetch the diff.**
   ```bash
   curl -sS "${BASE_URL}/git/diff?base=main&head=feature-branch"
   ```

3. **Parse the diff output.** Group changes by:
   - New files added
   - Modified files
   - Deleted files
   - Renamed files

4. **Summarize each changed file:**
   - File path
   - Lines added / removed
   - Brief description of what changed (new function, modified logic, config update)

5. **Highlight significant changes:**
   - New API endpoints or routes
   - Database schema changes
   - Configuration changes
   - Security-sensitive changes (auth, permissions, secrets)
   - Test additions or removals

6. **Show the commit log** between the two branches for context.
   ```bash
   curl -sS "${BASE_URL}/git/log?branch=feature-branch&limit=20"
   ```

7. **Present the summary:**
   ```
   Diff: main...feature-branch
   Commits: 7
   Files changed: 12
   Lines: +287 / -54

   Source files:  6 changed
   Test files:    4 changed
   Config files:  2 changed
   ```

8. **Flag any concerns:** missing test files for new source files, large single-file diffs, or potentially breaking changes.
