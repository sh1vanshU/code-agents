---
name: multi-service-deploy
description: Deploy multiple services in dependency order with health checks and rollback on failure
---

## Prerequisites

- [ ] All services listed with their build_version / image_tag
- [ ] Dependency order known (which services depend on which)
- [ ] ALL builds are SUCCESS -- do not start with any failed build
- [ ] Target environment is non-prod
- [ ] ArgoCD is configured (`ARGOCD_URL` env var is set) -- if not, skip health checks and warn user
- [ ] Current deployed version of each service recorded (rollback targets)

## Workflow

1. **Collect the deployment manifest.** Confirm with the user:

   | Order | Service | Image Tag | Depends On |
   |-------|---------|-----------|------------|
   | 1 | shared-lib-svc | 2.1.0-abc | (none) |
   | 2 | auth-svc | 1.5.3-def | shared-lib-svc |
   | 3 | payment-svc | 3.2.1-ghi | auth-svc, shared-lib-svc |

2. **Validate all builds** before starting any deployment.
   ```bash
   curl -sS "${BASE_URL}/jenkins/build/BUILD_JOB_PATH/last"
   ```
   If ANY build is FAILURE or UNSTABLE, STOP the entire multi-service deploy.

3. **Check ArgoCD availability** before relying on health checks.
   ```bash
   curl -sS "${BASE_URL}/argocd/apps/" 2>/dev/null || echo "ARGOCD_NOT_CONFIGURED"
   ```
   If ArgoCD is not configured, warn user: "ArgoCD not available -- will deploy without automated health checks. Monitor pods manually."

4. **Record current state** of each service for rollback (if ArgoCD available).
   ```bash
   curl -sS "${BASE_URL}/argocd/apps/{app_name}/pods"
   ```
   Store the current image tag for each service -- this is the rollback target.

5. **Deploy services in dependency order.** For each service:

   a. **Deploy:**
   ```bash
   curl -sS -X POST ${BASE_URL}/jenkins/build-and-wait -H "Content-Type: application/json" -d '{"job_name": "DEPLOY_JOB_PATH", "parameters": {"image_tag": "VERSION", "service": "SVC", "env_name": "ENV"}}'
   ```

   b. **Verify health** (if ArgoCD available):
   ```bash
   curl -sS "${BASE_URL}/argocd/apps/{app_name}/status"
   ```
   Sync status must be `Synced`, health must be `Healthy`, pods Running with correct image.

   c. **Report status** before proceeding to next service.

   d. **If deployment fails or health check fails: STOP and ROLLBACK.**

6. **Rollback procedure** (if any service fails):
   - Rollback in REVERSE dependency order (last deployed first)
   - For each:
   ```bash
   curl -sS -X POST ${BASE_URL}/jenkins/build-and-wait -H "Content-Type: application/json" -d '{"job_name": "DEPLOY_JOB_PATH", "parameters": {"image_tag": "PREVIOUS_VERSION", "service": "SVC", "env_name": "ENV"}}'
   ```
   - Verify each rollback
   - Report: "Rolled back X, Y, Z due to failure in W"

7. **Final report:** Status per service (SUCCESS, FAILED, ROLLED_BACK) + current versions.
   Delegate full verification: `[DELEGATE:argocd-verify]`

## Error Handling

| Situation | Action |
|-----------|--------|
| Partial deployment | Always deploy all or rollback all -- no partial states |
| ArgoCD not configured | Deploy without health checks, warn user to monitor manually |
| Dependency incompatibility | Deploy in order, verify inter-service communication |
| Rollback cascade | Track full dependency chain; rollback in reverse |

## Definition of Done

- All builds validated before starting
- Services deployed in dependency order with health checks between each
- If any failure: all affected services rolled back to previous versions
