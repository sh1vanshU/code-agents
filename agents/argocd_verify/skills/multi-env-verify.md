---
name: multi-env-verify
description: Cross-environment deployment verification — compare versions, detect drift
---

## Prerequisites

- [ ] Know the service/application name
- [ ] Know which environments to verify

## Workflow

1. **Build app names** using pattern `{env}-project-bombay-{app}`:

   | Environment | ArgoCD App Name |
   |-------------|----------------|
   | dev | `dev-project-bombay-{app}` |
   | dev-stable | `dev-stable-project-bombay-{app}` |
   | staging | `staging-project-bombay-{app}` |
   | qa | `qa-project-bombay-{app}` |
   | uat | `uat-project-bombay-{app}` |

   Confirm list with user before proceeding.

2. **Check each environment:**
   ```bash
   curl -sS "${BASE_URL}/argocd/apps/{env_app_name}/status"
   ```
   ```bash
   curl -sS "${BASE_URL}/argocd/apps/{env_app_name}/pods"
   ```
   Record: sync, health, pod count, image tags, restarts.

3. **Build comparison table** and identify: version drift, health mismatches, OutOfSync, restart anomalies.

4. **For unhealthy environments**, dig deeper with pod logs and Kibana errors.

5. **Check history** for environments with unexpected versions:
   ```bash
   curl -sS "${BASE_URL}/argocd/apps/{env_app_name}/history"
   ```

6. **Verify promotion readiness:**

   | Promotion | Requirement |
   |-----------|-------------|
   | dev -> dev-stable | Healthy in dev, no errors |
   | dev-stable -> staging | Healthy for >1 hour |
   | staging -> uat | QA sign-off |
   | uat -> production | Full test pass, change approval |

7. **Generate summary** with overall status, issues by severity, recommendations.
