---
name: cherry-pick
description: Cherry-pick commits between branches — preview, apply, resolve conflicts, verify build
---

## Before You Start

- Identify the commit hash(es) to cherry-pick and the target branch.
- Ensure working tree is clean — use [SKILL:safe-checkout] before switching branches.
- Fetch latest from remote so all commits are available locally.

## Workflow

1. **Fetch latest from remote.**
   ```bash
   curl -sS -X POST "${CODE_AGENTS_PUBLIC_BASE_URL}/git/fetch"
   ```

2. **Show what the commit(s) will change** before picking.
   ```bash
   cd ${TARGET_REPO_PATH} && git show --stat COMMIT_HASH
   ```
   Display: author, date, message, files changed, lines added/removed.

3. **Show the full diff** of the commit for user review.
   ```bash
   cd ${TARGET_REPO_PATH} && git show COMMIT_HASH
   ```

4. **Switch to the target branch** using safe-checkout.
   ```bash
   curl -sS -X POST "${CODE_AGENTS_PUBLIC_BASE_URL}/git/checkout" \
     -H "Content-Type: application/json" \
     -d '{"branch": "TARGET_BRANCH", "create": false}'
   ```

5. **Confirm with the user** before applying. Show:
   - Commit(s) to pick: hash, message, author.
   - Target branch name.
   - Files that will be affected.

6. **Apply the cherry-pick.**
   ```bash
   cd ${TARGET_REPO_PATH} && git cherry-pick COMMIT_HASH
   ```
   For multiple commits, pick them in chronological order:
   ```bash
   cd ${TARGET_REPO_PATH} && git cherry-pick COMMIT1 COMMIT2 COMMIT3
   ```

7. **If conflicts occur**, delegate to [SKILL:conflict-resolver] for resolution.
   After resolution, continue the cherry-pick:
   ```bash
   cd ${TARGET_REPO_PATH} && git cherry-pick --continue
   ```

8. **Verify the build passes** after cherry-pick.
   ```bash
   curl -sS -X POST "${CODE_AGENTS_PUBLIC_BASE_URL}/testing/run"
   ```

9. **Push the target branch** with the cherry-picked commits.
   ```bash
   curl -sS -X POST "${CODE_AGENTS_PUBLIC_BASE_URL}/git/push" \
     -H "Content-Type: application/json" \
     -d '{"branch": "TARGET_BRANCH", "remote": "origin"}'
   ```

10. **Report the result:**
    - Commits successfully cherry-picked.
    - Any conflicts that were resolved.
    - Build/test status.
    - Push confirmation.

## Definition of Done

- All specified commits cherry-picked onto the target branch.
- Any merge conflicts resolved (build verified after resolution).
- Build and tests pass on the target branch.
- Target branch pushed to remote.
- User confirmed the changes before and after picking.
