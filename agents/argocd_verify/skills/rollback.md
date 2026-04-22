---
name: rollback
description: Rollback to previous ArgoCD revision safely with user confirmation
---

## Prerequisites

- [ ] Confirmed deployment has issues warranting rollback
- [ ] Know the previous healthy revision number (from deployment history)

## Workflow

1. **Check current status** to confirm the issue:
   ```bash
   curl -sS "${BASE_URL}/argocd/apps/{app_name}/status"
   ```

2. **Fetch deployment history** to identify rollback target:
   ```bash
   curl -sS "${BASE_URL}/argocd/apps/{app_name}/history"
   ```
   Note current revision and previous healthy revision.

3. **Confirm with user** before proceeding. Show:
   - Current revision and its image tag
   - Target rollback revision and its image tag
   - Impact: pods will restart with the older image

4. **Trigger the rollback:**
   ```bash
   curl -sS -X POST "${BASE_URL}/argocd/apps/{app_name}/rollback" -H "Content-Type: application/json" -d '{"revision": "previous"}'
   ```
   Or with a specific revision:
   ```bash
   curl -sS -X POST "${BASE_URL}/argocd/apps/{app_name}/rollback" -H "Content-Type: application/json" -d '{"revision": 5}'
   ```

5. **Wait for sync:**
   ```bash
   curl -sS -X POST "${BASE_URL}/argocd/apps/{app_name}/wait-sync"
   ```

6. **Verify rollback succeeded:** Check status is Synced + Healthy, pods have correct (old) image tag, use [SKILL:log-scan] to verify no new errors.

7. **Report result:** Previous revision (from), current revision (to), pod health, any remaining issues.

## Error Handling

| Situation | Action |
|-----------|--------|
| Rollback succeeds, pods healthy | Report success |
| Rollback succeeds but pods still unhealthy | May need earlier revision |
| Rollback fails (sync error) | Check ArgoCD status, retry or escalate |
| No previous revision available | Cannot rollback -- fix forward |
