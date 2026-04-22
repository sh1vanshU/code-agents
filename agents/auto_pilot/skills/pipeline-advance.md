---
name: advance
description: Advance pipeline to next step with pre-conditions check
---

## Workflow

1. **Get current pipeline status** to know which step we are on.
   ```bash
   curl -sS "${BASE_URL}/pipeline/{run_id}/status"
   ```

2. **Verify pre-conditions for the next step:**
   - **Connect --> Review:** Repo is accessible, branch exists
   - **Review --> Build:** Code review passed, tests pass, coverage adequate
   - **Build --> Deploy:** Build succeeded, build_version extracted
   - **Deploy --> Verify:** Deploy succeeded, ArgoCD app name is known
   - **Verify --> Done:** All pods healthy, no errors in logs

3. **If pre-conditions are not met**, report what is missing and do not advance. Suggest actions to resolve the blockers.

4. **Execute the current step's work** by calling the appropriate API:
   - Review: `/v1/agents/code-reviewer/chat/completions` and `/testing/run`
   - Build: `/jenkins/build-and-wait`
   - Deploy: `/jenkins/build-and-wait` with deploy job
   - Verify: `/argocd/apps/{app}/status`, `/argocd/apps/{app}/pods`

5. **Advance the pipeline** once the step completes successfully.
   ```bash
   curl -sS -X POST "${BASE_URL}/pipeline/{run_id}/advance"
   ```

6. **Get updated status** to confirm the transition.
   ```bash
   curl -sS "${BASE_URL}/pipeline/{run_id}/status"
   ```

7. **Report the transition:** which step completed, what the result was, and what the next step is.

8. **If the step fails**, mark the pipeline as failed:
   ```bash
   curl -sS -X POST "${BASE_URL}/pipeline/{run_id}/fail"
   ```
   Recommend rollback if we are past the deploy step.
