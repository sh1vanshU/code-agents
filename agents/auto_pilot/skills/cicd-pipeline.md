---
name: cicd-pipeline
description: 7-step CI/CD pipeline with state tracking — connect, review, plan, build, deploy, verify, rollback
---

## Pipeline State API

- `POST ${BASE_URL}/pipeline/start` -- begin pipeline
- `GET ${BASE_URL}/pipeline/{run_id}/status` -- current state
- `POST ${BASE_URL}/pipeline/{run_id}/advance` -- mark step done
- `POST ${BASE_URL}/pipeline/{run_id}/fail` -- mark step failed
- `POST ${BASE_URL}/pipeline/{run_id}/rollback` -- trigger rollback

## Workflow

### Phase 1 -- Initialize

1. **Gather config from user:** branch, build job path, deploy job path, ArgoCD app name.

2. **Start pipeline run:**
   ```bash
   curl -sS -X POST ${BASE_URL}/pipeline/start -H "Content-Type: application/json" -d '{"branch": "BRANCH", "build_job": "BUILD_JOB", "deploy_job": "DEPLOY_JOB", "argocd_app": "APP"}'
   ```
   Save `run_id` for all subsequent calls.

### Phase 2 -- Step 1: Connect

3. **Verify repo and branch:**
   ```bash
   curl -sS "${BASE_URL}/git/current-branch" && curl -sS "${BASE_URL}/git/log?branch=BRANCH&limit=5"
   ```

4. **Advance:** `curl -sS -X POST "${BASE_URL}/pipeline/{run_id}/advance"`

### Phase 3 -- Step 2: Review & Test

5. **Run tests:** `curl -sS -X POST ${BASE_URL}/testing/run -H "Content-Type: application/json" -d '{"branch": "BRANCH"}'`
   Block if tests fail.

6. **Code review:** [DELEGATE:code-reviewer]

7. **Advance** once review passes and tests green.

### Phase 4 -- Step 3: Plan

8. **Generate execution plan** before build/deploy:
   - Summarize what will be built (branch, changes since last release)
   - List target environments (QA, staging, production)
   - Identify risks (breaking changes, migration steps, dependency updates)
   - Estimate blast radius (affected services, downstream consumers)
   - [DELEGATE:code-reasoning] Analyze changes for deployment risks

9. **Present plan to user** with options:
   - a) Approve and proceed to build
   - b) Modify plan (adjust targets, skip environments)
   - c) Abort pipeline

10. **Advance** once plan approved.

### Phase 5 -- Step 4: Build

11. **Trigger build:** [DELEGATE:jenkins-cicd] with [SKILL:build]
    Extract `build_version`. Advance on success.

### Phase 6 -- Step 5: Deploy

12. **Trigger deploy:** [DELEGATE:jenkins-cicd] with [SKILL:deploy]
    Deploy per plan (environments, order). Advance on success.

### Phase 7 -- Step 6: Verify

13. **Verify:** [DELEGATE:argocd-verify] with [SKILL:health-check]
    Advance once pods healthy and synced.

### Phase 8 -- Step 7: Rollback (if needed)

14. **If any post-deploy step fails:** [DELEGATE:argocd-verify] with [SKILL:rollback]

## Failure Handling

- If any step fails: `curl -sS -X POST "${BASE_URL}/pipeline/{run_id}/fail"`
- Do NOT proceed until current step succeeds.
- If past deploy step, recommend rollback.
- Report status after every transition: `curl -sS "${BASE_URL}/pipeline/{run_id}/status"`

## Pre-Conditions

| From | To | Requirement |
|------|----|-------------|
| Connect | Review | Repo accessible, branch exists |
| Review | Plan | Review passed, tests green |
| Plan | Build | Plan approved by user |
| Build | Deploy | build_version extracted |
| Deploy | Verify | Deploy succeeded |
| Verify | Done | Pods healthy, no errors |
