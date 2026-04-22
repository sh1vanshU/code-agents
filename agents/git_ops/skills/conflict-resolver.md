---
name: conflict-resolver
description: Merge conflict detection, analysis, and resolution — auto-resolve simple, guide complex
---

## Before You Start

- Confirm which branches are being merged (source into target).
- Ensure working tree is clean — use [SKILL:safe-checkout] before starting.
- Fetch latest from remote so both branches are up to date.

## Workflow

1. **Fetch latest and switch to the target branch.**
   ```bash
   curl -sS -X POST "${CODE_AGENTS_PUBLIC_BASE_URL}/git/fetch"
   ```
   ```bash
   curl -sS -X POST "${CODE_AGENTS_PUBLIC_BASE_URL}/git/checkout" \
     -H "Content-Type: application/json" \
     -d '{"branch": "TARGET_BRANCH", "create": false}'
   ```

2. **Attempt the merge** to detect conflicts.
   ```bash
   curl -sS -X POST "${CODE_AGENTS_PUBLIC_BASE_URL}/git/merge" \
     -H "Content-Type: application/json" \
     -d '{"branch": "SOURCE_BRANCH", "no_ff": false}'
   ```

3. **If merge succeeds with no conflicts** — done. Report the merge result.

4. **If conflicts detected**, get the list of conflicting files.
   ```bash
   curl -sS "${CODE_AGENTS_PUBLIC_BASE_URL}/git/status"
   ```
   Identify files marked as "both modified" or "unmerged".

5. **For each conflicting file**, read the file content to see conflict markers:
   ```
   <<<<<<< HEAD (ours — target branch)
   ... our version ...
   =======
   ... their version ...
   >>>>>>> SOURCE_BRANCH (theirs — source branch)
   ```

6. **Classify each conflict:**
   - **Simple** (non-overlapping changes, imports, adjacent lines): auto-resolve by keeping both changes in correct order.
   - **Complex** (overlapping logic, semantic conflicts): show both versions side-by-side, explain what each side does, and suggest a resolution.

7. **For simple conflicts** — resolve automatically by editing the file to combine both changes. Remove conflict markers.

8. **For complex conflicts** — present to the user:
   - Show the conflicting section with context (5 lines above/below).
   - Explain what "ours" does vs what "theirs" does.
   - Suggest a resolution (keep ours, keep theirs, or a merged version).
   - Wait for user approval before applying.

9. **Stage resolved files.**
   ```bash
   curl -sS -X POST "${CODE_AGENTS_PUBLIC_BASE_URL}/git/add" \
     -H "Content-Type: application/json" \
     -d '{"files": ["resolved-file.py"]}'
   ```

10. **Commit the merge resolution.**
    ```bash
    curl -sS -X POST "${CODE_AGENTS_PUBLIC_BASE_URL}/git/commit" \
      -H "Content-Type: application/json" \
      -d '{"message": "merge: resolve conflicts merging SOURCE_BRANCH into TARGET_BRANCH"}'
    ```

11. **Verify the build passes** after resolution.
    ```bash
    curl -sS -X POST "${CODE_AGENTS_PUBLIC_BASE_URL}/testing/run"
    ```

## Definition of Done

- All conflict markers removed from every file.
- All resolved files staged and committed.
- Merge commit created with a descriptive message.
- Build and tests pass after resolution.
- No unresolved conflicts remain in working tree.
