---
name: log-analysis
description: Read build/deploy console logs, extract errors, test results, version tags
---

## Prerequisites

- [ ] Know the build/deploy job path and build number
- [ ] Know whether this is a build log or deploy log (patterns differ)

## Workflow

1. **Fetch the logs.**
   ```bash
   curl -sS "${BASE_URL}/jenkins/build/JOB_PATH/BUILD_NUMBER/log"
   ```
   Or get the last build:
   ```bash
   curl -sS "${BASE_URL}/jenkins/build/JOB_PATH/last"
   ```

2. **Scan for build result markers:**
   - `BUILD SUCCESS` / `BUILD FAILURE` / `BUILD UNSTABLE`
   - Exit codes and return status

3. **Extract Docker image version/tag** (check in this order):
   - `pushing manifest for <registry>/<service>:<TAG>@sha256:...` — **most reliable, use this first**
   - `Successfully tagged <service>:<version>`
   - `IMAGE_TAG=<version>` in environment output
   Tag format: `{build_number}-grv` (dev/feature) or `{build_number}-grv-prod` (release branches).

4. **Extract test results:**
   - pytest: `X passed, Y failed, Z skipped`
   - JUnit/Maven: `Tests run: X, Failures: Y, Errors: Z, Skipped: W`
   - Jest: `Tests: X passed, Y failed, Z total`

5. **Extract error messages** if build failed:
   - Compilation: file, line, error description
   - Test failures: which tests failed, assertion messages
   - Docker: which layer failed and why
   - Dependency: missing packages, version conflicts

6. **Check build status.**
   ```bash
   curl -sS "${BASE_URL}/jenkins/build/JOB_PATH/BUILD_NUMBER/status"
   ```

7. **Report a structured summary:**
   ```
   Build: #854
   Result: SUCCESS
   Duration: 2m 34s
   Version: 1.2.3-abc123
   Tests: 150 passed, 0 failed, 2 skipped
   ```

8. **If errors found**, provide actionable analysis: what failed, likely root cause, suggested fix.

## Common Log Patterns

| Log Pattern | Root Cause | Fix |
|-------------|-----------|-----|
| `OutOfMemoryError: Java heap space` | JVM heap too small | Increase `-Xmx` |
| `npm ERR! ERESOLVE` | Conflicting deps | `npm install --legacy-peer-deps` or fix versions |
| `Cannot find module '...'` | Missing dependency | Check package.json / requirements.txt |
| `Connection refused` (in tests) | External service not running in CI | Mock the dependency |
| `FATAL: Unable to find credentials` | Credential ID mismatch | Verify credential ID in Jenkinsfile |
| `Dockerfile: COPY failed` | File not in build context | Check `.dockerignore` and COPY paths |
| `context deadline exceeded` | Operation timed out | Increase timeout or investigate slowness |

## Definition of Done

- Build result confirmed from both status API and log markers
- Image version/tag extracted (or confirmed absent with explanation)
- Test results parsed and errors analyzed with root cause
