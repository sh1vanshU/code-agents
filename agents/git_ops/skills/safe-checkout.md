---
name: safe-checkout
description: Safe branch switch — show dirty files + diff, ask user to stash/commit/discard before checkout
---

## Workflow

1. **Check working tree status:**
   ```bash
   curl -sS "${BASE_URL}/git/status"
   ```
   If `clean: true` → skip to step 5 (checkout directly).

2. **Show what changed in each file:**
   ```bash
   curl -sS "${BASE_URL}/git/diff?base=HEAD&head=HEAD"
   ```
   Summarize: file name, status (M/A/D/?), lines added/removed.

3. **Present options to user:**
   ```
   You have N uncommitted changes:
     - src/Payment.java (M) +12/-3
     - src/Config.java (M) +5/-0
     - test/PaymentTest.java (?) untracked

   What would you like to do?
     a) Stash all changes (I'll ask for a name)
     b) Commit these changes first (I'll help with message)
     c) Discard all changes (WARNING: irreversible)
     d) Cancel — stay on current branch
   ```
   Use [QUESTION:branch] template if available, otherwise ask directly.

4. **Execute user's choice:**

   **If stash (a):**
   - Ask for a stash name: "Name for this stash? (e.g. 'wip-before-foundry-release')"
   ```bash
   curl -sS -X POST "${BASE_URL}/git/stash" -H "Content-Type: application/json" -d '{"action":"push","message":"USER_STASH_NAME"}'
   ```
   - Confirm: "Stashed N files as 'USER_STASH_NAME'. You can restore with /git/stash pop."

   **If commit (b):**
   - Suggest a commit message based on the diff summary
   - Stage all files:
   ```bash
   curl -sS -X POST "${BASE_URL}/git/add" -H "Content-Type: application/json" -d '{"files":null}'
   ```
   - Commit:
   ```bash
   curl -sS -X POST "${BASE_URL}/git/commit" -H "Content-Type: application/json" -d '{"message":"COMMIT_MESSAGE"}'
   ```

   **If discard (c):**
   - Warn: "This will permanently discard all uncommitted changes. Are you sure?"
   - Only proceed if user confirms explicitly.
   ```bash
   git checkout -- . && git clean -fd
   ```

   **If cancel (d):**
   - Stop. Do not checkout.

5. **Checkout the target branch:**
   ```bash
   curl -sS -X POST "${BASE_URL}/git/checkout" -H "Content-Type: application/json" -d '{"branch":"TARGET_BRANCH","create":false}'
   ```

6. **Fetch latest and update:**
   ```bash
   curl -sS -X POST "${BASE_URL}/git/fetch"
   ```
   Then merge remote into local:
   ```bash
   curl -sS -X POST "${BASE_URL}/git/merge" -H "Content-Type: application/json" -d '{"branch":"origin/TARGET_BRANCH"}'
   ```

7. **Confirm:** Report current branch, latest commit, and whether the branch is up to date.

## Rules

- NEVER auto-stash or auto-discard without user choosing
- NEVER skip showing dirty files — user must see what will be affected
- Always ask for a descriptive stash name (not just "stash@{0}")
- If checkout fails after stash, pop the stash back automatically
