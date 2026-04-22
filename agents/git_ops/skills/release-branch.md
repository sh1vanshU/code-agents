---
name: release-branch
description: Release branch management — create, cherry-pick, merge back (GitFlow + trunk-based)
---

## Before You Start

- Confirm the branching strategy with the user: **GitFlow** (main, develop, feature/*, release/*, hotfix/*) or **trunk-based** (main + short-lived feature branches).
- Ensure working tree is clean — use [SKILL:safe-checkout] before switching branches.
- Fetch latest from remote so branch creation starts from up-to-date refs.

## Workflow

1. **Fetch latest refs from remote.**
   ```bash
   curl -sS -X POST "${CODE_AGENTS_PUBLIC_BASE_URL}/git/fetch"
   ```

2. **Determine source branch.** Ask the user:
   - Release branch: typically from `develop` (GitFlow) or `main` (trunk-based).
   - Hotfix branch: typically from `main` or the current release branch.

3. **Switch to the source branch** using safe-checkout.
   ```bash
   curl -sS -X POST "${CODE_AGENTS_PUBLIC_BASE_URL}/git/checkout" \
     -H "Content-Type: application/json" \
     -d '{"branch": "SOURCE_BRANCH", "create": false}'
   ```

4. **Create the release or hotfix branch.**
   - Release: `release/vX.Y.Z` (e.g., `release/v1.2.0`)
   - Hotfix: `hotfix/SHORT_DESCRIPTION` (e.g., `hotfix/fix-payment-timeout`)
   ```bash
   curl -sS -X POST "${CODE_AGENTS_PUBLIC_BASE_URL}/git/checkout" \
     -H "Content-Type: application/json" \
     -d '{"branch": "release/v1.2.0", "create": true}'
   ```

5. **Cherry-pick specific commits** if needed (e.g., backporting fixes to the release branch).
   Use [SKILL:cherry-pick] for safe cherry-pick with conflict handling.

6. **Push the new branch to remote.**
   ```bash
   curl -sS -X POST "${CODE_AGENTS_PUBLIC_BASE_URL}/git/push" \
     -H "Content-Type: application/json" \
     -d '{"branch": "release/v1.2.0", "remote": "origin"}'
   ```

7. **After release — merge back to main.**
   ```bash
   curl -sS -X POST "${CODE_AGENTS_PUBLIC_BASE_URL}/git/checkout" \
     -H "Content-Type: application/json" \
     -d '{"branch": "main", "create": false}'
   ```
   ```bash
   curl -sS -X POST "${CODE_AGENTS_PUBLIC_BASE_URL}/git/merge" \
     -H "Content-Type: application/json" \
     -d '{"branch": "release/v1.2.0", "no_ff": true}'
   ```

8. **Merge back to develop** (GitFlow only).
   ```bash
   curl -sS -X POST "${CODE_AGENTS_PUBLIC_BASE_URL}/git/checkout" \
     -H "Content-Type: application/json" \
     -d '{"branch": "develop", "create": false}'
   ```
   ```bash
   curl -sS -X POST "${CODE_AGENTS_PUBLIC_BASE_URL}/git/merge" \
     -H "Content-Type: application/json" \
     -d '{"branch": "release/v1.2.0", "no_ff": true}'
   ```

9. **Tag the release** on main using [SKILL:tag-release].

10. **Push all branches and tags.**
    ```bash
    curl -sS -X POST "${CODE_AGENTS_PUBLIC_BASE_URL}/git/push" \
      -H "Content-Type: application/json" \
      -d '{"branch": "main", "remote": "origin"}'
    ```

## Definition of Done

- Release/hotfix branch created from the correct source branch.
- All required commits present on the release branch (cherry-picked if needed).
- Release branch merged back to main (and develop for GitFlow).
- Release tagged with semantic version on main.
- All branches and tags pushed to remote.
- No merge conflicts remain unresolved.
