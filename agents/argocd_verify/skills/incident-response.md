---
name: incident-response
description: Deployment incident response — assess, diagnose, rollback, notify
---

## Prerequisites

- [ ] Know the affected app name and environment
- [ ] Determine severity: fully down, degraded, or intermittent

## Workflow

1. **Assess current state** immediately -- speed is critical:
   ```bash
   curl -sS "${BASE_URL}/argocd/apps/{app_name}/status"
   ```
   Classify: Healthy+Synced (check app logs), Degraded (investigate), Missing/Unknown (critical), OutOfSync (deploy in progress or failed).

2. **List pods and identify unhealthy ones:**
   ```bash
   curl -sS "${BASE_URL}/argocd/apps/{app_name}/pods"
   ```
   Flag: CrashLoopBackOff, ImagePullBackOff, Pending, Error, restarts > 0.

3. **Collect logs from unhealthy pods:**
   ```bash
   curl -sS "${BASE_URL}/argocd/apps/{app_name}/pods/{pod_name}/logs?namespace=default&tail=500"
   ```
   Look for: OutOfMemoryError, Connection refused, ConfigurationException, panic, startup traces.

4. **Check K8s events** for cluster-level issues:
   ```bash
   curl -sS "${BASE_URL}/k8s/events?namespace=NS&limit=30"
   ```
   Look for: FailedScheduling, FailedMount, Unhealthy, BackOff.

5. **Check Kibana** for application-level errors:
   ```bash
   curl -sS -X POST "${BASE_URL}/kibana/errors" -H "Content-Type: application/json" -d '{"service": "SVC", "time_range": "30m", "top_n": 10}'
   ```

6. **Classify and determine root cause:**

   | Symptom | Likely Cause | Resolution |
   |---------|-------------|------------|
   | All pods CrashLoopBackOff | Startup failure | Check logs -- config or dependency issue |
   | Running but errors in logs | Runtime bug | Rollback |
   | ImagePullBackOff | Wrong tag or registry down | Verify image |
   | Pending | Insufficient resources | Scale cluster |
   | Intermittent 5xx | Resource pressure | Check CPU/memory via [SKILL:resource-monitor] |
   | Slow responses | CPU throttling | Check limits and downstream health |

7. **Execute rollback** if warranted (confirm with user):
   ```bash
   curl -sS -X POST "${BASE_URL}/argocd/apps/{app_name}/rollback" -H "Content-Type: application/json" -d '{"revision": "previous"}'
   ```
   Then wait and verify:
   ```bash
   curl -sS -X POST "${BASE_URL}/argocd/apps/{app_name}/wait-sync"
   ```

8. **Verify recovery:** Synced, Healthy, all pods Running with previous version, error rate returning to baseline.

9. **Create incident ticket:** [DELEGATE:jira-ops] with findings, timeline, root cause, and resolution.

## Error Handling

| Severity | Action |
|----------|--------|
| Fully down | Rollback immediately, notify team |
| Degraded | Investigate, rollback if no fix within 5 min |
| Intermittent | Monitor, rollback if worsening within 15 min |
| Warning signs only | Monitor, plan fix for next deploy |
