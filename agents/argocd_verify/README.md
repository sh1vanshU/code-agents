# ArgoCD Verification Agent

> Principal DevOps Engineer who owns deployment verification, pod health, and production safety

## Identity

| Field | Value |
|-------|-------|
| **Name** | `argocd-verify` |
| **YAML** | `argocd_verify.yaml` |
| **Role** | Principal DevOps Engineer (Deployment Verification) |
| **Backend** | `${CODE_AGENTS_BACKEND:cursor}` |
| **Model** | `${CODE_AGENTS_MODEL:Composer 2 Fast}` |
| **Permission** | `default` — ask before each action |

## Capabilities

- Check ArgoCD application sync status and health
- List pods and verify correct image tags
- Scan pod logs for errors (ERROR, FATAL, Exception, panic)
- Trigger rollback to a previous revision
- Check EKS pod status, logs, and deployments directly via kubectl (Kubernetes endpoints)
- Search Kibana/Elasticsearch logs for error patterns after deployment
- Canary deployment analysis: compare canary vs stable metrics, error rates, latency, auto-promote or rollback
- Monitor Kubernetes resources: CPU/memory per pod, HPA status, OOM risk detection
- Deployment incident response: detect unhealthy pods, collect logs, identify root cause, rollback, notify
- Multi-environment verification: check all envs, compare pod versions, ensure consistent state

## Tools & Endpoints

### ArgoCD API
- `GET /argocd/apps/{app_name}/status` — sync & health status
- `GET /argocd/apps/{app_name}/pods` — list pods with image tags
- `GET /argocd/apps/{app_name}/pods/{pod_name}/logs?namespace=default&tail=200` — pod logs
- `POST /argocd/apps/{app_name}/sync` — trigger sync: `{"revision": null}`
- `POST /argocd/apps/{app_name}/rollback` — rollback: `{"revision": "previous"}` or `{"revision": 5}`
- `GET /argocd/apps/{app_name}/history` — deployment history
- `POST /argocd/apps/{app_name}/wait-sync` — wait until synced & healthy

### Kubernetes API (direct kubectl access)
- `GET /k8s/pods?namespace=NS&label=app=SVC` — list pods with status, images, restarts
- `GET /k8s/pods/{pod}/logs?namespace=NS&tail=100` — pod logs
- `GET /k8s/pods/{pod}/describe?namespace=NS` — pod events and conditions
- `GET /k8s/deployments?namespace=NS` — deployment replicas and images
- `GET /k8s/events?namespace=NS&limit=20` — recent cluster events

### Kibana API (search application logs via Elasticsearch)
- `GET /kibana/indices` — list available index patterns
- `POST /kibana/search` — search logs: `{"index":"logs-*","query":"*","service":"SVC","log_level":"ERROR","time_range":"15m","size":100}`
- `POST /kibana/errors` — error aggregation: `{"index":"logs-*","service":"SVC","time_range":"1h","top_n":10}`

## Skills

### Own Skills

| Skill | Description |
|-------|-------------|
| `health-check` | Check app sync status, pod health, image tags — full verification |
| `log-scan` | Scan pod logs for ERROR, FATAL, panic, OOM patterns |
| `rollback` | Rollback to previous ArgoCD revision safely |
| `k8s-pods` | Check EKS pod status, logs, and deployments directly via kubectl |
| `kibana-logs` | Search Kibana logs after deployment, compare error patterns before/after |
| `sanity-check` | Post-deploy sanity verification using rules from .code-agents/sanity.yaml |
| `canary-analysis` | Canary deployment analysis: compare canary vs stable metrics, error rates, latency, auto-promote or rollback |
| `resource-monitor` | Monitor k8s resources: CPU/memory per pod, HPA status, node capacity, requests vs limits, OOM risk |
| `incident-response` | Deployment incident response: detect unhealthy pods, collect logs, identify root cause, rollback, notify |
| `multi-env-verify` | Verify deployment across environments: check all envs, compare pod versions, ensure consistent state |

### Shared Engineering Skills

Shared skills from `agents/_shared/skills/` are also available to this agent: architecture, code-review, debug, deploy-checklist, documentation, incident-response, standup, system-design, tech-debt, testing-strategy.

## ArgoCD App Naming

App names follow the pattern: `{env_name}-project-bombay-{app_name}`
Example: env=dev-stable, app=pg-acquiring-biz -> `dev-stable-project-bombay-pg-acquiring-biz`
If user gives only the service name, the agent asks for the environment to build the full app name.

## Usage

### Chat REPL
```bash
code-agents chat argocd-verify
```

### Inline Delegation (from another agent)
```
/argocd-verify <your prompt>
```

### Skill Invocation
```
/argocd-verify:health-check <your prompt>
/argocd-verify:k8s-pods <your prompt>
/argocd-verify:kibana-logs <your prompt>
/argocd-verify:canary-analysis <your prompt>
/argocd-verify:resource-monitor <your prompt>
/argocd-verify:incident-response <your prompt>
/argocd-verify:multi-env-verify <your prompt>
```

### API
```bash
curl -X POST http://localhost:8000/v1/agents/argocd-verify/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "your prompt"}], "stream": true}'
```

## Example Prompts

1. "Are all pods healthy after the latest deploy?"
2. "Check pod logs for any errors"
3. "Rollback to the previous deployment"
4. "Show me k8s pod status for namespace production"
5. "Search Kibana logs for errors in the last 15 minutes"
6. "Analyze the canary deployment — should we promote or rollback?"
7. "Check CPU and memory usage for payment-svc pods"
8. "Pods are crashing after deploy — what's wrong?"
9. "Verify payment-svc across all environments"

## Autorun Config

This agent has an `autorun.yaml` that defines allowed and blocked commands for auto-execution.

## Rules

Custom rules to guide this agent's behavior:

| Scope | Path |
|-------|------|
| Global | `~/.code-agents/rules/argocd-verify.md` |
| Project | `.code-agents/rules/argocd-verify.md` |

See `code-agents rules create --agent argocd-verify` to create rules.

---

### Codebase refactor (Phases 1–5) — COMPLETED

Package reorganization (`analysis/`, `generators/`, `reporters/`, `tools/`, `integrations/` + backward-compat re-exports); CLI and chat command registries (`cli/registry.py`, `chat/slash_registry.py`); Explore agent (15) + `SubagentDispatcher`; `BashTool` for shell execution; slimmer chat REPL (`chat_state.py`, `chat_delegation.py`, `chat_repl.py`, `chat_skill_runner.py`). Full detail: `ROADMAP.md` section **Major Refactor: Claude Code Architecture Alignment**.

