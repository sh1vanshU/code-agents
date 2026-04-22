---
name: build-troubleshoot
description: Troubleshoot build failures -- parse console log, identify root cause, suggest fix
---

## Prerequisites

- [ ] Know the failed build job path and build number
- [ ] Know what changed since the last successful build

## Workflow

1. **Get the failed build status and log.**
   ```bash
   curl -sS "${BASE_URL}/jenkins/build/JOB_PATH/BUILD_NUMBER/status"
   ```
   Then fetch the full console log:
   ```bash
   curl -sS "${BASE_URL}/jenkins/build/JOB_PATH/BUILD_NUMBER/log"
   ```

2. **Classify the failure type.** Scan the console log:

   | Failure Type | Log Patterns | Priority |
   |-------------|-------------|----------|
   | Compilation error | `COMPILATION ERROR`, `cannot find symbol`, `error:` | P0 -- code fix |
   | Test failure | `Tests run:.*Failures: [1-9]`, `AssertionError` | P0 -- test/code fix |
   | Dependency resolution | `Could not resolve`, `Could not find artifact`, `404` | P1 -- check repo/nexus |
   | Timeout | `Build timed out`, `deadline exceeded`, `ABORTED` | P1 -- check agent/tests |
   | OOM | `OutOfMemoryError`, `Java heap space`, `GC overhead`, `Killed` | P1 -- increase memory |
   | Docker build | `docker build.*failed`, `COPY failed`, `layer does not exist` | P1 -- check Dockerfile |
   | Infrastructure | `Connection refused`, `Agent went offline`, `No space left` | P2 -- Jenkins infra |
   | Permission/Auth | `401 Unauthorized`, `403 Forbidden`, `permission denied` | P2 -- check credentials |

3. **Extract the root cause** for the identified failure type:
   - Compilation: exact file, line number, error message
   - Test failure: failing test class/method, assertion, expected vs actual
   - Dependency: missing artifact coordinates (group:artifact:version)
   - Timeout: build duration vs normal, which stage took longest
   - OOM: heap size settings, which stage consumed most memory
   - Docker: failing Dockerfile instruction, file paths
   - Infrastructure: failing connection target, transient vs persistent

4. **Suggest a fix:**

   | Root Cause | Suggested Fix |
   |-----------|--------------|
   | Compilation error | Fix the code at the reported file:line |
   | Missing import/symbol | Check if dependency was removed or class renamed |
   | Test assertion failure | Review test logic -- is test correct or code wrong? |
   | Test timeout | Check for infinite loops, slow calls, or missing mocks |
   | Dependency not found | Check artifact version in Nexus/Maven Central |
   | SNAPSHOT missing | Ensure upstream project published its SNAPSHOT |
   | Build OOM | Increase `-Xmx` in MAVEN_OPTS or GRADLE_OPTS |
   | Docker COPY failed | Verify file path relative to build context |
   | Agent offline | Retry -- if persistent, check Jenkins node health |
   | Disk full | Clean workspace, prune Docker images on build agent |

5. **Check if flaky.** Compare with recent build history:
   ```bash
   curl -sS "${BASE_URL}/jenkins/build/JOB_PATH/last"
   ```
   - Same test fails intermittently -- likely flaky, suggest quarantine
   - Failure is new and consistent -- real regression

6. **Recommend retry or fix:**
   - Transient (infra, timeout, flaky): Retry the build
   - Code failure (compilation, test): Fix the code first
   - Config failure (dependency, auth): Fix configuration first
   - NEVER retry a build that failed due to code errors
   - NEVER retry more than 2 times without investigating

## Definition of Done

- Failure classified, root cause identified, fix suggested
- Determination: retry (transient) or fix first (code/config)
- User informed of root cause and next steps
