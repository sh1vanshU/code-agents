---
name: start-pipeline
description: Initialize 6-step pipeline — connect, review, build, deploy, verify
---

## Workflow

1. **Gather pipeline configuration from the user:**
   - Branch to deploy
   - Build job path in Jenkins
   - Deploy job path in Jenkins
   - ArgoCD application name

2. **Start a new pipeline run.**
   ```bash
   curl -sS -X POST ${BASE_URL}/pipeline/start \
     -H "Content-Type: application/json" \
     -d '{"branch": "feature-branch", "build_job": "my-build", "deploy_job": "my-deploy", "argocd_app": "my-app"}'
   ```
   Save the `run_id` from the response for all subsequent calls.

3. **Step 1 — Connect to Codebase.** Verify repo access and show branch info.
   ```bash
   curl -sS "${BASE_URL}/git/current-branch"
   ```
   ```bash
   curl -sS "${BASE_URL}/git/log?branch=feature-branch&limit=5"
   ```

4. **Advance the pipeline** after each successful step.
   ```bash
   curl -sS -X POST "${BASE_URL}/pipeline/{run_id}/advance"
   ```

5. **Step 2 — Review & Test.** Send code for review and run tests.
   ```bash
   curl -sS -X POST ${BASE_URL}/testing/run \
     -H "Content-Type: application/json" \
     -d '{"branch": "feature-branch"}'
   ```
   Block if tests fail or coverage gaps exist.

6. **Steps 3-5 — Build, Deploy, Verify.** Continue through the pipeline, advancing after each success. Use `jenkins/build-and-wait` for build and deploy, ArgoCD endpoints for verify.

7. **If any step fails**, mark it and stop:
   ```bash
   curl -sS -X POST "${BASE_URL}/pipeline/{run_id}/fail"
   ```

8. **Report the pipeline status** after initialization and at each step transition.
   ```bash
   curl -sS "${BASE_URL}/pipeline/{run_id}/status"
   ```
