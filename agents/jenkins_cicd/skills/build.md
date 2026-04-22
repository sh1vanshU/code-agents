---
name: build
description: Build current repo — find job, trigger, poll, extract image tag
---

## Before Starting

Check [Session Memory] for already-known values.
- **Reusable facts** (branch, repo, build_job, build_params): skip re-fetching if already in memory.
- **Build results** (build_number, build_result, image_tag): these are from a PREVIOUS build. **NEVER skip triggering a new build** just because a previous build succeeded. Users re-build the same branch when new code is pushed.
After each discovery, emit `[REMEMBER:key=value]` so it persists for future turns.

## Workflow

1. **Detect the current repo and branch:**
   If [Session Memory] has `branch` and `repo`, skip this step — use those values.
   Otherwise:
   ```bash
   curl -sS "${BASE_URL}/git/current-branch" && basename $(pwd)
   ```
   → Emit: `[REMEMBER:branch=<value>]` `[REMEMBER:repo=<value>]`

2. **Find the build job.** Check project rules first — they may specify `JENKINS_BUILD_JOB`.
   If [Session Memory] has `build_job`, skip this step.
   Otherwise, list Jenkins folders and find the job matching the repo name:
   ```bash
   curl -sS "${BASE_URL}/jenkins/jobs?folder=FOLDER"
   ```
   Look for a job containing the repo name (e.g. `pg2-dev-pg-acquiring-biz`).
   If multiple folders/jobs match, ask the user: [QUESTION:jenkins_folder]
   → Emit: `[REMEMBER:build_job=<full_job_path>]`

   **IMPORTANT — Learn the folder structure:** When listing jobs, also note ALL subfolders
   (entries with `"type":"folder"`). These often contain deploy jobs, perf-deploy jobs, etc.
   Save the full folder map so you don't need to guess paths later:
   → Emit: `[REMEMBER:jenkins_folders=<comma-separated list of subfolder full_names>]`
   Example: `[REMEMBER:jenkins_folders=pg2/pg2-dev-build-jobs/deploy,pg2/pg2-dev-build-jobs/perf-deploy]`

3. **Fetch build parameters** (never guess — case-sensitive):
   If [Session Memory] has `build_params`, skip this step.
   Otherwise:
   ```bash
   curl -sS "${BASE_URL}/jenkins/jobs/FULL_JOB_PATH/parameters"
   ```
   Note exact parameter names (branch, java_version, etc.) and defaults.
   → Emit: `[REMEMBER:build_params=<param_summary>]`

4. **Confirm with user:** Show repo name, branch, build job, parameters. Proceed?

5. **Trigger build and poll until completion:**
   ```bash
   curl -sS -X POST ${BASE_URL}/jenkins/build-and-wait -H "Content-Type: application/json" -d '{"job_name": "FULL_JOB_PATH", "parameters": {"branch": "BRANCH", "java_version": "java21"}}'
   ```
   This triggers, polls every 5s, and returns when done.

6. **Parse the response:**
   - `result`: SUCCESS or FAILURE
   - `build_number`: Jenkins build # (e.g. #854)
   - `build_version`: the **image tag** extracted from console logs — THIS IS THE KEY OUTPUT
   - `duration`: how long the build took
   - `log_tail`: last 100 lines

7. **Extract image tag — use `build_version` or scan logs:**
   If `build_version` is null, scan `log_tail` for the tag. **Primary pattern** (most reliable):
   - `pushing manifest for <registry>/<service>:<TAG>@sha256:...` → extract TAG
   Fallback patterns:
   - `Successfully tagged <service>:<tag>`
   - `IMAGE_TAG=<tag>` or `BUILD_VERSION=<tag>`

   **Tag format by branch:**
   - Non-release branches (dev, feature, hotfix, etc.) → tag = `{build_number}-grv`
   - Release branches (`release*`) → tag = `{build_number}-grv-prod`

   Validate the extracted tag matches the expected format for the branch. If it doesn't match, prefer the tag from the `pushing manifest for` log line — that is the actual pushed image.

8. **On SUCCESS — report and prompt for deploy:**
   ```
   Build #854 SUCCESS (2m 34s)
   Image tag: 854-grv
   ```
   → Emit: `[REMEMBER:build_number=#854]` `[REMEMBER:build_result=SUCCESS]` `[REMEMBER:image_tag=854-grv]`
   Then ask: "Deploy this tag? If yes, which environment?" Use [QUESTION:deploy_environment_class] if not specified.
   The `build_version` IS the `image_tag` for the deploy step.

9. **On FAILURE:** Show error from `log_tail`. STOP — never deploy a failed build.
   Load [SKILL:build-troubleshoot] for detailed failure analysis.

## Definition of Done

- Build completed with SUCCESS
- **Image tag extracted and reported to user**
- User asked about deployment with the extracted tag
