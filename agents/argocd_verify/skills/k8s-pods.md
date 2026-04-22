---
name: k8s-pods
description: Direct Kubernetes pod debugging via kubectl — use when ArgoCD is unavailable or need deeper K8s details
---

**When to use:** When ArgoCD is unavailable, or you need K8s-specific details (describe, events, previous container logs, deployment rollout status). For standard post-deploy verification, use [SKILL:health-check] instead.

## Workflow

1. **List pods:**
   ```bash
   curl -sS "${BASE_URL}/k8s/pods?namespace=NS&label=app=SVC"
   ```
   Check: all Running, ready count matches total, zero restarts, correct image tag.

2. **Check crash loops — get current logs:**
   ```bash
   curl -sS "${BASE_URL}/k8s/pods/POD_NAME/logs?namespace=NS&tail=100"
   ```

3. **Get previous container logs** if pod restarted:
   ```bash
   curl -sS "${BASE_URL}/k8s/pods/POD_NAME/logs?namespace=NS&tail=100&previous=true"
   ```

4. **Describe pod** for events and conditions:
   ```bash
   curl -sS "${BASE_URL}/k8s/pods/POD_NAME/describe?namespace=NS"
   ```
   Look for: ImagePullBackOff, CrashLoopBackOff, OOMKilled, Evicted.

5. **Check deployments** for rollout status:
   ```bash
   curl -sS "${BASE_URL}/k8s/deployments?namespace=NS"
   ```
   Verify: readyReplicas matches desired.

6. **Check recent events:**
   ```bash
   curl -sS "${BASE_URL}/k8s/events?namespace=NS&limit=20"
   ```
   Look for Warning events: FailedScheduling, FailedMount, Unhealthy.

7. **Report:** All Running + correct image = healthy. Any not Running = investigate logs and events.

## Error Handling

| Situation | Action |
|-----------|--------|
| CrashLoopBackOff | Check logs + previous container logs |
| ImagePullBackOff | Verify image tag and registry credentials |
| Pending | Check events for FailedScheduling |
| readyReplicas < desired | Rollout incomplete -- check pod events |
