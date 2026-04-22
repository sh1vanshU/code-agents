---
name: canary-analysis
description: Canary deployment analysis — compare canary vs stable metrics, promote or rollback
---

## Prerequisites

- [ ] Know the canary image tag and stable image tag
- [ ] Verify canary pods are running alongside stable pods

## Workflow

1. **Identify canary and stable pods:**
   ```bash
   curl -sS "${BASE_URL}/argocd/apps/{app_name}/pods"
   ```
   Separate by image tag. If all pods have same tag, canary is not active.

2. **Compare error rates** (canary vs stable via Kibana):
   ```bash
   curl -sS -X POST "${BASE_URL}/kibana/search" -H "Content-Type: application/json" -d '{"query": "CANARY_POD AND ERROR", "service": "SVC", "time_range": "15m", "size": 50}'
   ```
   Compare: canary error count vs stable (normalized by pod count), new error types.

3. **Compare latency:**
   ```bash
   curl -sS -X POST "${BASE_URL}/kibana/search" -H "Content-Type: application/json" -d '{"query": "CANARY_POD AND (latency OR duration OR response_time)", "service": "SVC", "time_range": "15m", "size": 50}'
   ```

4. **Check canary pod health:**
   ```bash
   curl -sS "${BASE_URL}/k8s/pods/{canary_pod}/describe?namespace=NS"
   ```
   Verify: Running, 0 restarts, readiness passing, no OOMKill.

5. **Scan canary pod logs:**
   ```bash
   curl -sS "${BASE_URL}/argocd/apps/{app_name}/pods/{canary_pod}/logs?namespace=default&tail=200"
   ```

6. **Decision thresholds:**
   - **PROMOTE:** error rate <= stable + 1%, latency p95 <= stable + 10%, 0 restarts, no new error types
   - **WATCH (extend):** error rate +1-5% with latency ok, OR latency +10-25% with errors ok
   - **ROLLBACK:** error rate > stable + 5%, OR latency > +25%, OR any restarts/OOM, OR new error types

7. **If promoting:** recommend full rollout via ArgoCD sync.

8. **If rolling back:**
   ```bash
   curl -sS -X POST "${BASE_URL}/argocd/apps/{app_name}/rollback" -H "Content-Type: application/json" -d '{"revision": "previous"}'
   ```
   Report the specific metrics that triggered rollback.

9. **If inconclusive:** extend canary by 15 minutes, re-analyze.
