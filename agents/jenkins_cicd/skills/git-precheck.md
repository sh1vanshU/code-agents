---
name: git-precheck
description: Git preflight check before build — branch, status, commits, remote sync, readiness
---

## Workflow

1. **Get current branch and repo name:**
   ```bash
   git rev-parse --abbrev-ref HEAD && basename $(git rev-parse --show-toplevel)
   ```
   Record both — branch determines what Jenkins builds, repo name maps to the build job.

2. **Check working tree status:**
   ```bash
   git status --porcelain
   ```
   - **Clean:** Good to go.
   - **Staged but uncommitted:** Warn — "You have staged changes not yet committed. Jenkins builds from remote, these won't be included."
   - **Unstaged modifications:** Warn — "Modified files not staged. These won't be in the build."
   - **Untracked files:** Note but don't block.

3. **If uncommitted changes exist**, ask the user:
   - "Commit these changes before building? Jenkins builds from remote — local changes won't be included."
   - If yes: help commit (suggest message from diff). If no: proceed with warning.

4. **Check if branch is pushed to remote:**
   ```bash
   git log origin/$(git rev-parse --abbrev-ref HEAD)..HEAD --oneline 2>/dev/null
   ```
   - Empty = branch is up to date with remote. Good.
   - Shows commits = **local commits not pushed**. Warn: "You have N local commits not pushed. Jenkins won't see them."
   - Error = branch doesn't exist on remote. Warn: "Branch not pushed to remote yet."

5. **Show recent commits** on this branch:
   ```bash
   git log --oneline -5
   ```

6. **Check if branch is behind main** (merge conflict risk):
   ```bash
   git rev-list --count HEAD..origin/main 2>/dev/null
   ```
   - 0 = up to date. Good.
   - 1-19 = slightly behind, usually fine.
   - 20+ = "Your branch is N commits behind main. Consider rebasing to avoid CI conflicts."

7. **Report preflight summary:**
   ```
   Git Preflight Check
   ====================
   Repo:           pg-acquiring-biz
   Branch:         dev_integration_foundry_v2_qa4
   Status:         Clean (no uncommitted changes)
   Remote sync:    Up to date (all commits pushed)
   Behind main:    3 commits (OK)
   Last commit:    abc1234 — "feat: add payment retry" (2h ago)
   Ready for:      Build ✓
   ```

   Or if issues found:
   ```
   Git Preflight Check
   ====================
   Repo:           pg-acquiring-biz
   Branch:         dev_integration_foundry_v2_qa4
   Status:         2 modified files (NOT committed)
   Remote sync:    3 commits NOT pushed
   Behind main:    25 commits (recommend rebase)
   Last commit:    abc1234 — "feat: add payment retry" (2h ago)
   Ready for:      Build ✗ (push changes first)
   ```

8. **If not ready**, recommend actions:
   - Uncommitted changes → commit or stash
   - Not pushed → `git push origin BRANCH`
   - Far behind main → `git rebase origin/main`

## Definition of Done

- Branch identified and confirmed
- Remote sync verified (all commits pushed)
- Working tree clean or user acknowledged dirty state
- User has clear go/no-go for build
