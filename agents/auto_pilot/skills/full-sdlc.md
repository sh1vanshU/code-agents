---
name: full-sdlc
description: Master 13-step SDLC — from Jira ticket to production deploy with full verification
---

## Before You Start

- [ ] Confirm the Jira ticket key and verify ticket status
- [ ] Identify target branch and deployment environment
- [ ] Verify credentials: Jira, Jenkins, ArgoCD, git remote
- [ ] Check for deployment freezes or ongoing incidents
- [ ] Confirm with user: full automation or approval gates at each step?

## Workflow

1. **Validate Jira ticket.**
   [DELEGATE:jira-ops] -- validate ticket has acceptance criteria, assignee, correct status.
   Gate: if FAIL, STOP and report missing items.
   Then fetch ticket details:
   ```bash
   curl -sS "${BASE_URL}/jira/issue/KEY-123"
   ```

2. **System analysis.**
   [DELEGATE:code-reasoning] -- analyze codebase, identify files to change, dependencies, tests needed.
   Output: structured LLD with file list.

3. **Design review.**
   [DELEGATE:code-reviewer] -- review the LLD.
   Gate: if NEEDS-CHANGES, send back to code-reasoning (max 3 attempts, then STOP).

4. **Implement.**
   [DELEGATE:code-writer] -- implement feature per approved LLD.

5. **Run tests.**
   [DELEGATE:code-tester] -- run all tests, classify failures.

5.5. **Security review.**
   [DELEGATE:code-reviewer] -- review for OWASP top 10, injection, auth issues.
   Gate: if CRITICAL finding, delegate fix to code-writer before proceeding.

6. **Code review.**
   [DELEGATE:code-reviewer] -- review changes for bugs, security, LLD adherence.
   Gate: if REQUEST_CHANGES, fix and re-review (max 3 attempts, then STOP).

7. **Local build.**
   [SKILL:code-writer:local-build]
   Gate: if build fails after 3 cycles, STOP.

8. **Git push.**
   [DELEGATE:git-ops] -- push changes to remote branch. Confirm with user first.

9. **Jenkins build.**
   [DELEGATE:jenkins-cicd] with [SKILL:build]
   Extract build_version. Gate: if fails, analyze logs and fix.

10. **Jenkins deploy.**
    [DELEGATE:jenkins-cicd] with [SKILL:deploy]
    Confirm with user. Non-prod only.

11. **Verify deployment.**
    [DELEGATE:argocd-verify] with [SKILL:health-check]
    Then: [DELEGATE:redash-query] for data validation if applicable.

12. **QA regression.**
    [DELEGATE:qa-regression] -- full regression: functional, API, performance, contract tests.

13. **Mark Jira done.**
    [DELEGATE:jira-ops] -- transition to Done, add deployment comment with env, version, URLs.

## Gate Criteria

| Step | Gate | Pass | Fail Action | Rollback |
|------|------|------|-------------|----------|
| 3 | Design Review | APPROVED | Redesign (max 3) | N/A |
| 5 | Tests | All pass | Fix + re-test | Revert code |
| 5.5 | Security | No CRITICAL | Fix + re-review | Revert code |
| 6 | Code Review | APPROVED | Fix + re-review (max 3) | Revert code |
| 7 | Local Build | Exit 0 | Fix (max 3) | Revert code |
| 9 | Jenkins Build | SUCCESS | Analyze + fix | Safe |
| 11 | Deploy Verify | Pods healthy | ArgoCD rollback | Previous revision |

## Rollback Points

1. **Pre-push (1-7):** Discard local changes.
2. **Post-push (8):** Revert commit.
3. **Post-build (9):** Artifact exists but undeployed. Safe.
4. **Post-deploy (10-11):** ArgoCD rollback to previous revision. CRITICAL.
5. **Post-QA (12):** Rollback deploy AND revert code.

## Progress Reporting

After each step, update:
```
SDLC Progress: KEY-123
| Step | Status | Details |
|------|--------|---------|
| 1. Jira | DONE | ticket summary |
| 2. Analysis | DONE | N files identified |
| 3. Design | IN PROGRESS | ... |
```

## Rules

- Each gate must pass before proceeding
- 3 failures at any gate = STOP and escalate to user
- Always confirm destructive actions (deploy, push)
- Never skip design review or code review
- If workflow exceeds 30 minutes, pause and check with user
