---
name: deploy
description: Deploy image tag from build to environment — select env, trigger, verify, report tag
---

## Before Starting

Check [Session Memory] for already-known values (`image_tag`, `repo`, `build_job`, `deploy_env`).
- **Reusable facts** (repo, build_job, deploy_env): use directly, do NOT re-fetch.
- **image_tag**: use the latest one from memory — this is from the most recent build.
  Always confirm with user: "Deploy image tag X? [Y/n]" before proceeding.
Emit `[REMEMBER:key=value]` for any new discoveries.

## Prerequisites

- [ ] Build succeeded with known `image_tag` (from build step or user-provided)
- [ ] Know the repo/service name (from current directory or user input)

## Workflow

1. **Confirm inputs.** You need three things — check [Session Memory] first:
   - **image_tag**: from [Session Memory] `image_tag`, or build step (`build_version`), or user-provided
   - **service name**: from [Session Memory] `repo`, or current directory
   - **environment**: from [Session Memory] `deploy_env`, or ask user — use [QUESTION:deploy_environment_class]

   If user said "deploy to qa4", parse: env class=QA, sub-env=qa4.
   → Emit: `[REMEMBER:deploy_env=qa4]`

2. **Find the deploy job.** Check in this order:
   a. Check [Session Memory] for `deploy_job` — use directly if present.
   b. Check project rules for `JENKINS_DEPLOY_JOB_DEV` / `JENKINS_DEPLOY_JOB_QA`.
   c. Check [Session Memory] for `jenkins_folders` — this contains subfolder paths discovered
      during the build step. List jobs inside the deploy subfolder:
      ```bash
      curl -sS "${BASE_URL}/jenkins/jobs?folder=DEPLOY_SUBFOLDER_FROM_MEMORY"
      ```
      Pick the job matching the service or ask user if multiple match.
   d. If `jenkins_folders` is not in memory, list the build jobs folder and look for subfolders:
      ```bash
      curl -sS "${BASE_URL}/jenkins/jobs?folder=pg2/pg2-dev-build-jobs" | python3 -c "import sys,json; [print(j['name'],'|',j['full_name'],'|',j['type']) for j in json.load(sys.stdin)['jobs'] if j.get('type')=='folder' or 'deploy' in j['name'].lower()]"
      ```
   - **NEVER restart from scratch** on a 404. Try alternative paths first.
   - **NEVER re-fetch branch or build job** — those are already in [Session Memory].
   → Emit: `[REMEMBER:deploy_job=<full_deploy_job_path>]`

3. **Fetch the DEPLOY job parameters** (NOT the build job — use `deploy_job` from memory):
   ```bash
   curl -sS "${BASE_URL}/jenkins/jobs/DEPLOY_JOB_FROM_MEMORY/parameters"
   ```
   Use the `deploy_job` path from [Session Memory] — NOT `build_job`.
   The response will list ALL required parameters. Typical deploy params:
   - `image_tag` (String) — the build version to deploy
   - `service` (Choice) — the service name, pick the one matching the repo
   - `env_name` (Choice) — the target environment (dev, qa4, qa5, etc.)
   **ALL parameters returned by this endpoint are REQUIRED. Include every one in the trigger.**
   NEVER fetch build job parameters at this stage. The build is DONE.

   ⚠️ **MANDATORY: Extract `env_name` from this response.** The parameter list is NOT truncated.
   You MUST read the full JSON and find `env_name`. If you skip it, deploy goes to the WRONG environment.

4. **Resolve `env_name` — THIS IS MANDATORY, DO NOT SKIP:**
   - If user specified an environment (e.g. "deploy to qa4") → use that value exactly.
   - If [Session Memory] has `deploy_env` → use that value.
   - Otherwise → show the `env_name` choices from the parameters response and ask user to pick.
   - **NEVER use the default value from Jenkins.** Always set `env_name` explicitly.
   → Emit: `[REMEMBER:deploy_env=<chosen_env>]`

5. **Trigger the DEPLOY job** — `env_name` IS REQUIRED in the parameters:
   ```bash
   curl -sS -X POST ${BASE_URL}/jenkins/build-and-wait -H "Content-Type: application/json" -d '{"job_name": "DEPLOY_JOB", "parameters": {"image_tag": "TAG", "service": "SVC", "env_name": "ENV"}}'
   ```
   - `job_name` = `deploy_job` from [Session Memory]
   - `image_tag` = from [Session Memory] (e.g. `913-grv`)
   - `service` = match repo name from the choices list (e.g. `acquiring-biz`)
   - `env_name` = from step 4 (e.g. `qa4`) — **NEVER omit this parameter**
   - **If `env_name` is missing from your curl command, STOP and add it. Deploy without env_name goes to the WRONG environment.**
   - NEVER trigger the build job here. NEVER re-build.

7. **On SUCCESS — verify via ArgoCD immediately:**
   ```
   Deploy SUCCESS (1m 15s)
   Service: pg-acquiring-biz
   Environment: qa4
   Image tag deployed: 854-grv
   ```
   → Emit: `[REMEMBER:deploy_result=SUCCESS]` `[REMEMBER:deploy_env=qa4]`

   **Now run ArgoCD verification directly** using [SKILL:argocd-verify]:
   - App name: `{env}-project-bombay-{service}` (e.g. `qa4-project-bombay-pg-acquiring-biz`)
   - Check status, pods, and logs

   **Then check application logs** using [SKILL:_shared:kibana-logs]:
   - Search recent errors: `{"service": "SERVICE", "log_level": "ERROR", "time_range": "15m"}`
   - Check for FATAL/panic: `{"service": "SERVICE", "query": "FATAL OR panic OR OOMKilled", "time_range": "15m"}`
   - Show the full Build → Deploy → ArgoCD Verify → Kibana Logs summary table

8. **On FAILURE:** Show error from deploy logs. Do NOT retry automatically.

## Definition of Done

- Deploy completed with SUCCESS
- **Deployed image tag reported to user**
- ArgoCD verification completed (status=Synced, health=Healthy, pods running with correct tag)
- Kibana log check completed (no new error patterns, no FATAL/panic)
