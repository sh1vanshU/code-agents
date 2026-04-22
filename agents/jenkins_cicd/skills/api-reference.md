---
name: api-reference
description: Git and Jenkins API endpoint reference with request/response formats
---

## Git API Endpoints

All endpoints use the server base URL from your system prompt context.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/git/current-branch` | GET | Current branch name |
| `/git/status` | GET | Working tree status (staged, unstaged, untracked) |
| `/git/branches` | GET | List all local and remote branches |
| `/git/log?branch={branch}&limit=5` | GET | Recent commits on a branch |
| `/git/diff?base=main&head={branch}` | GET | Diff between two branches |

## Jenkins API Endpoints

### Discovery (read-only)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/jenkins/jobs?folder=FOLDER` | GET | List jobs in a Jenkins folder (name, type, color, URL) |
| `/jenkins/jobs/{FULL_JOB_PATH}/parameters` | GET | Get job parameter schema (names, defaults, choices) |

**CRITICAL:** `job_path` must be the FULL folder path:
- Correct: `pg2/pg2-dev-build-jobs/pg2-dev-pg-acquiring-biz`
- Wrong: `pg2-dev-pg-acquiring-biz` (missing folder prefix)
- Use the value from `JENKINS_BUILD_JOB` / `JENKINS_DEPLOY_JOB_*` env vars directly.

### Build & Deploy

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/jenkins/build-and-wait` | POST | Trigger build/deploy + poll until done + extract version |
| `/jenkins/build/{job_name}/{build_number}/status` | GET | Check build progress and result |
| `/jenkins/build/{job_name}/{build_number}/log` | GET | Full console output (truncated to 50KB) |
| `/jenkins/build/{job_name}/last` | GET | Latest build with version extraction |

### build-and-wait Request Format

**Build:**
```json
{
  "job_name": "FULL/PATH/TO/BUILD_JOB",
  "parameters": {
    "branch": "release",
    "java_version": "java21"
  }
}
```

**Deploy:**
```json
{
  "job_name": "FULL/PATH/TO/DEPLOY_JOB",
  "parameters": {
    "image_tag": "VERSION_FROM_BUILD",
    "service": "SERVICE_NAME",
    "env_name": "dev"
  }
}
```

**Response:**
```json
{
  "result": "SUCCESS",
  "build_number": 854,
  "build_version": "1.2.3-abc123",
  "duration": 156000,
  "log_tail": "... last 100 lines ..."
}
```

## Deploy Job Mapping

Separate deploy pipelines per environment class:

| Environment Class | Env Var | Fallback |
|------------------|---------|----------|
| **Dev** (dev, dev-stable) | `JENKINS_DEPLOY_JOB_DEV` | `JENKINS_DEPLOY_JOB` |
| **QA** (qa1-qa4, staging) | `JENKINS_DEPLOY_JOB_QA` | `JENKINS_DEPLOY_JOB` |

When deploying:
1. Determine environment class (Dev or QA) from user's request
2. Select the correct deploy job env var
3. Fetch parameters from that job to discover available sub-environments
4. NEVER hardcode environment lists -- always fetch from Jenkins

## Parameter Rules

- Parameter names are **CASE-SENSITIVE** -- always fetch before triggering
- `build_version` from build response = `image_tag` for deploy
- Always confirm parameter values with user before triggering
