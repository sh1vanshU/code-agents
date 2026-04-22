---
name: api-reference
description: ArgoCD, Kubernetes, and Kibana API endpoint reference
---

## ArgoCD Endpoints

All endpoints use the server base URL from your system prompt context.
ArgoCD Web UI: `https://argocd.pgnonprod.example.com/applications/argocd/{app_name}`

### Application Status & Discovery

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/argocd/apps` | GET | List all applications (filter: `?project=X&selector=label=value`) |
| `/argocd/apps/{app_name}/status` | GET | Sync status + health status |
| `/argocd/apps/{app_name}/pods` | GET | List pods with image tags, status, restarts |
| `/argocd/apps/{app_name}/pods/{pod_name}/logs?namespace=NS&tail=200` | GET | Pod logs |
| `/argocd/apps/{app_name}/history` | GET | Deployment history with revisions |
| `/argocd/apps/{app_name}/events` | GET | Kubernetes events for the app (deploy errors, scheduling failures) |
| `/argocd/apps/{app_name}/managed-resources` | GET | All K8s resources managed by this app (Deployments, Services, ConfigMaps, etc.) |
| `/argocd/apps/{app_name}/resource?name=N&kind=K&namespace=NS` | GET | Single resource detail (e.g. a specific Deployment or Pod) |
| `/argocd/apps/{app_name}/manifests` | GET | Rendered manifests (what ArgoCD will apply) |
| `/argocd/apps/{app_name}/revisions/{revision}/metadata` | GET | Git commit metadata for a revision |

### Actions & Operations

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/argocd/apps/{app_name}/sync` | POST | Trigger sync (body: `{}` or `{"revision": "sha"}`) |
| `/argocd/apps/{app_name}/rollback` | POST | Rollback (body: `{"revision": "previous"}` or `{"revision": 5}`) |
| `/argocd/apps/{app_name}/wait-sync` | POST | Block until synced + healthy (long-poll) |
| `/argocd/apps/{app_name}/operation` | DELETE | Cancel a stuck/running sync operation |
| `/argocd/apps/{app_name}/resource/actions` | GET | List available actions on a resource (e.g. restart) |
| `/argocd/apps/{app_name}/resource/actions` | POST | Execute resource action (body: `{"name": "restart", "resource": ...}`) |

## Kubernetes Endpoints (direct kubectl)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/k8s/pods?namespace=NS&label=app=SVC` | GET | List pods with status, images, restarts |
| `/k8s/pods/{pod}/logs?namespace=NS&tail=100` | GET | Pod logs (add `&previous=true` for crashed containers) |
| `/k8s/pods/{pod}/describe?namespace=NS` | GET | Pod events, conditions, resource requests/limits |
| `/k8s/deployments?namespace=NS` | GET | Deployment replicas and images |
| `/k8s/events?namespace=NS&limit=20` | GET | Recent cluster events |

## Kibana Endpoints (log search via Elasticsearch)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/kibana/indices` | GET | List available index patterns |
| `/kibana/search` | POST | Search logs |
| `/kibana/errors` | POST | Error aggregation (top N patterns) |

### Kibana search body

```json
{
  "index": "logs-*",
  "query": "*",
  "service": "SERVICE_NAME",
  "log_level": "ERROR",
  "time_range": "15m",
  "size": 100
}
```

### Kibana errors body

```json
{
  "index": "logs-*",
  "service": "SERVICE_NAME",
  "time_range": "1h",
  "top_n": 10
}
```

## ArgoCD Tested Examples

**IMPORTANT:** Always use `/argocd/apps/` (plural, with trailing s). Never use `/argocd/app/` (singular).

### Working examples (verified):

```bash
# List all apps matching a service name
curl -sS "${BASE_URL}/argocd/apps" | python3 -c "import sys,json; apps=json.load(sys.stdin); [print(a['name']) for a in apps.get('apps',[]) if 'acquiring' in a.get('name','').lower()]"

# Get app status (sync + health + images)
curl -sS "${BASE_URL}/argocd/apps/dev2-project-bombay-pg-acquiring-biz/status"

# List pods with image tags
curl -sS "${BASE_URL}/argocd/apps/dev2-project-bombay-pg-acquiring-biz/pods"

# Get deployment history
curl -sS "${BASE_URL}/argocd/apps/dev2-project-bombay-pg-acquiring-biz/history"

# Get events (deploy errors, scheduling failures)
curl -sS "${BASE_URL}/argocd/apps/dev2-project-bombay-pg-acquiring-biz/events"

# Get managed resources (Deployments, Services, ConfigMaps)
curl -sS "${BASE_URL}/argocd/apps/dev2-project-bombay-pg-acquiring-biz/managed-resources"

# Trigger sync
curl -sS -X POST "${BASE_URL}/argocd/apps/dev2-project-bombay-pg-acquiring-biz/sync" -H "Content-Type: application/json" -d '{}'

# Wait until synced + healthy
curl -sS -X POST "${BASE_URL}/argocd/apps/dev2-project-bombay-pg-acquiring-biz/wait-sync"
```

### WRONG URLs (will return 404):

```
/argocd/app/...     ← WRONG (singular, missing 's')
/argocd/status      ← WRONG (no app name)
/argocd/apps/status ← WRONG (missing app name in path)
```

## ArgoCD App Naming Convention

Pattern: `{env_name}-project-bombay-{app_name}`

| Environment | Example App Name |
|-------------|-----------------|
| dev | `dev-project-bombay-pg-acquiring-biz` |
| dev-stable | `dev-stable-project-bombay-pg-acquiring-biz` |
| staging | `staging-project-bombay-pg-acquiring-biz` |
| qa / qa2 / qa4 | `qa2-project-bombay-pg-acquiring-biz` |
| uat | `uat-project-bombay-pg-acquiring-biz` |

If user gives only the service name, ask for the environment to build the full app name.
