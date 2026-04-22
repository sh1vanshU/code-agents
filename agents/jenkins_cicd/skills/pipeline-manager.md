---
name: pipeline-manager
description: Manage Jenkins pipelines -- list jobs, check health, trigger builds, monitor queue
---

## Prerequisites

- [ ] Jenkins credentials valid (`JENKINS_URL`, `JENKINS_USERNAME`, `JENKINS_API_TOKEN`)
- [ ] Know the Jenkins folder structure

## Workflow

1. **List jobs in a folder** to discover available pipelines.
   ```bash
   curl -sS "${BASE_URL}/jenkins/jobs?folder=FOLDER_PATH"
   ```
   Parse response: job names, types (freestyle, pipeline, multibranch), last build status.

2. **Check job health** for a specific pipeline.
   ```bash
   curl -sS "${BASE_URL}/jenkins/build/JOB_PATH/last"
   ```
   Evaluate:
   - Last build result (SUCCESS, FAILURE, UNSTABLE, ABORTED)
   - Build duration vs historical average
   - 3+ consecutive failures = broken pipeline

3. **Fetch job parameters** before triggering any build.
   ```bash
   curl -sS "${BASE_URL}/jenkins/jobs/JOB_PATH/parameters"
   ```
   - Note default values, choices, required vs optional
   - Confirm parameter values with user before triggering

4. **Trigger a parameterized build.**
   ```bash
   curl -sS -X POST ${BASE_URL}/jenkins/build-and-wait -H "Content-Type: application/json" -d '{"job_name": "JOB_PATH", "parameters": {"param1": "value1"}}'
   ```

5. **Monitor build status** for in-progress builds.
   ```bash
   curl -sS "${BASE_URL}/jenkins/build/JOB_PATH/BUILD_NUMBER/status"
   ```
   If queued or waiting for executor, inform user of the delay.

6. **Report pipeline summary:**
   - Total jobs with pass/fail breakdown
   - Jobs with consecutive failures (action items)
   - Jobs not run recently (stale pipelines)

## Error Handling

| Situation | Action |
|-----------|--------|
| Builds stuck in queue >5 min | Check Jenkins node count |
| Job not run in >7 days | May be abandoned -- investigate |
| Default parameters outdated | Review before each trigger |
| Multiple builds of same job running | Check if concurrent builds allowed |

## Definition of Done

- Jobs listed and health assessed
- Parameters fetched and confirmed before any trigger
- Build triggered and monitored to completion
