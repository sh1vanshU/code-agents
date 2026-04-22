---
name: incident-manager
description: Incident management — detect, assess severity, investigate across agents, fix or rollback, postmortem
---

## Workflow

### Phase 1 -- Detection & Triage

1. **Identify the incident source:** user report, Kibana alerts, ArgoCD health failure.

2. **Gather initial signals:**
   ```bash
   curl -sS "${BASE_URL}/argocd/apps/{app}/status" && curl -sS "${BASE_URL}/argocd/apps/{app}/pods"
   ```
   ```bash
   curl -sS -X POST "${BASE_URL}/kibana/search" -H "Content-Type: application/json" -d '{"service": "SVC", "log_level": "ERROR", "time_range": "15m", "size": 50}'
   ```

3. **Assess severity:**
   - **P0 -- Critical:** Service fully down, data loss risk, all users affected
   - **P1 -- High:** Major feature broken, significant error rate
   - **P2 -- Medium:** Partial degradation, workaround exists
   - **P3 -- Low:** Minor issue, few users, cosmetic

### Phase 2 -- Investigation

4. **Check pod health:** [DELEGATE:argocd-verify] with [SKILL:health-check]
   Look for: CrashLoopBackOff, OOMKilled, ImagePullBackOff, restarts.

5. **Search logs:** [SKILL:_shared:kibana-logs]
   Look for: stack traces, timeouts, connection refused, null pointer.

6. **Check recent deployments:**
   ```bash
   curl -sS "${BASE_URL}/git/log?limit=10"
   ```
   Was there a deploy before the incident?

7. **Query data if needed:** [DELEGATE:redash-query] for database state, metrics.

8. **Analyze code changes:** [DELEGATE:code-reasoning] if recent deploy is suspected.

### Phase 3 -- Remediation

9. **Decide on action:**

   | Finding | Action |
   |---------|--------|
   | Bad deploy | [DELEGATE:argocd-verify] with [SKILL:rollback] |
   | Code bug | [DELEGATE:code-writer] hotfix, then [SKILL:cicd-pipeline] |
   | Infrastructure | Report to ops |
   | Flaky/transient | Monitor, add retry logic |
   | Config issue | Fix config, redeploy |

10. **Escalation rules:**
    - P0: Rollback immediately unless clearly not deploy-related
    - P1: Investigate up to 15 min before recommending rollback
    - P2/P3: Fix forward preferred

### Phase 4 -- Resolution & Postmortem

11. **Verify fix:** Error rates normal (Kibana), pods healthy (ArgoCD), service responding.

12. **Create incident ticket:** [DELEGATE:jira-ops] with findings, timeline, root cause.

13. **Document:**
    ```
    INCIDENT REPORT
    Severity: P{N}
    Duration: {start} to {end}
    Impact: {who/what affected}
    Root cause: {what went wrong}
    Resolution: {what fixed it}
    Follow-up: {preventive actions}
    ```

14. **Recommend preventive measures:** additional tests, monitoring, canary deploys, feature flags.
