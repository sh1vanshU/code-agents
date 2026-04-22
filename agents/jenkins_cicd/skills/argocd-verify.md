---
name: argocd-verify
description: Basic post-deploy ArgoCD verification — status, pods, logs (3 API calls)
---

## Prerequisites

- [ ] Deploy completed with SUCCESS
- [ ] Know the service name and environment (from [Session Memory])
- [ ] ArgoCD app name follows: `{env}-project-bombay-{service}`

## Workflow

1. **Check application sync and health status:**
   ```bash
   curl -sS "${BASE_URL}/argocd/apps/{app_name}/status"
   ```
   Verify: `sync_status` = `Synced`, `health_status` = `Healthy`.
   If NOT synced or NOT healthy → report issue immediately.

2. **List pods and verify image tags:**
   ```bash
   curl -sS "${BASE_URL}/argocd/apps/{app_name}/pods"
   ```
   For each pod check:
   - Status = `Running`
   - Image tag matches the deployed version
   - No `CrashLoopBackOff`, `ImagePullBackOff`, or `Error`
   - Restart count = 0 (or low)

3. **Tail pod logs and scan for errors:**
   ```bash
   curl -sS "${BASE_URL}/argocd/apps/{app_name}/pods/{pod_name}/logs?namespace=default&tail=80"
   ```
   Scan for: `ERROR`, `FATAL`, `Exception`, `panic`, `OOM`, `killed`.
   If clean → report healthy. If errors → report with log snippets.

## App Naming Convention

| Environment | ArgoCD App Name |
|-------------|-----------------|
| dev2 | `dev2-project-bombay-{service}` |
| qa4 | `qa4-project-bombay-{service}` |
| staging | `staging-project-bombay-{service}` |

## Report Format

```
┌─────────────────────┬─────────────┬──────────────────────────────┐
│ Step                │ Status      │ Details                      │
├─────────────────────┼─────────────┼──────────────────────────────┤
│ Build               │ ✅ SUCCESS  │ #1234 · tag · 4m 51s         │
│ Deploy              │ ✅ SUCCESS  │ #5678 · svc → env · 1m 16s   │
│ ArgoCD Verify       │ ✅ HEALTHY  │ app synced, pods running      │
│ Kibana Logs         │ ✅ CLEAN    │ no new errors, no FATAL       │
└─────────────────────┴─────────────┴──────────────────────────────┘
```

4. **Check application logs via Kibana** using [SKILL:_shared:kibana-logs]:
   ```bash
   curl -sS -X POST "${BASE_URL}/kibana/search" -H "Content-Type: application/json" -d '{"service": "SERVICE", "log_level": "ERROR", "time_range": "15m", "size": 50}'
   ```
   Check for new error patterns and FATAL/panic. Include in the summary table above.

## When to Delegate

For advanced operations, tell the user to switch to argocd-verify agent:
- Rollback to previous version
- Canary analysis and traffic comparison
- Incident response and root cause analysis
- Multi-environment consistency checks
- Resource monitoring (CPU, memory, HPA)

Example: "For rollback, switch to argocd-verify: `/argocd-verify rollback {app_name}`"

## Definition of Done

- App sync status = Synced
- App health status = Healthy
- All pods Running with correct image tag
- No ERROR/FATAL in recent logs
- Summary table shown to user
