---
name: health-check
description: Check app sync status, pod health, image tags — full post-deploy verification
---

## Prerequisites

- [ ] Know the expected image tag/version
- [ ] Know the ArgoCD app name (`{env}-project-bombay-{app}`)

## Workflow

1. **Capture current revision** (needed for rollback reference):
   ```bash
   curl -sS "${BASE_URL}/argocd/apps/{app_name}/history"
   ```

2. **Trigger an explicit ArgoCD sync** then wait for completion:
   ```bash
   curl -sS -X POST "${BASE_URL}/argocd/apps/{app_name}/sync" -H "Content-Type: application/json" -d '{}'
   ```
   ```bash
   curl -sS -X POST "${BASE_URL}/argocd/apps/{app_name}/wait-sync"
   ```
   If sync fails or times out, report immediately -- do not proceed.

3. **Check application status:**
   ```bash
   curl -sS "${BASE_URL}/argocd/apps/{app_name}/status"
   ```
   Verify: `sync_status` = `Synced`, `health_status` = `Healthy`.

4. **List pods and verify image tags:**
   ```bash
   curl -sS "${BASE_URL}/argocd/apps/{app_name}/pods"
   ```
   For each pod check: Running, correct image tag, no CrashLoopBackOff/ImagePullBackOff, restart count = 0.

5. **Fetch logs for each pod and scan for errors:**
   ```bash
   curl -sS "${BASE_URL}/argocd/apps/{app_name}/pods/{pod_name}/logs?namespace=default&tail=200"
   ```
   Scan for: `ERROR`, `FATAL`, `Exception`, `panic`, `OOM`, `killed`.

6. **Dependency health check (Redis, DB, Kafka, etc.):**
   **Step A — Parse startup logs** from step 5 for connection status:
   - Look for: `Connected to`, `Connection refused`, `Timeout`, `redis`, `kafka`, `datasource`, `hikari`, `pool`
   - Spring Boot logs connection success/failure on startup for each dependency

   **Step B — Hit actuator health endpoint** (if service exposes it):
   ```bash
   curl -sS "${BASE_URL}/k8s/pods/{pod_name}/exec?namespace={namespace}&command=curl+-s+http://localhost:8080/actuator/health"
   ```
   If exec is not available, try via the pod logs for actuator output, or skip if not reachable.

   **Report dependency health summary:**
   ```
   ┌────────────┬────────┬──────────────────────────────┐
   │ Dependency │ Status │ Details                      │
   ├────────────┼────────┼──────────────────────────────┤
   │ Database   │ ✅/❌  │ HikariPool connected / refused│
   │ Redis      │ ✅/❌  │ Connected / timeout           │
   │ Kafka      │ ✅/❌  │ Consumer group joined / error │
   │ Others     │ ✅/❌  │ Any other deps from logs      │
   └────────────┴────────┴──────────────────────────────┘
   ```
   Only include dependencies that appear in the logs or actuator response. If a dependency is not found, skip it.

7. **Trace verification — extract a traceId and list the full request flow:**
   From the pod logs fetched in step 5, extract one recent traceId (look for fields like `traceId`, `trace_id`, `X-Request-Id`, or similar patterns in the log output).
   Then fetch logs with a higher tail count and filter by that traceId:
   ```bash
   curl -sS "${BASE_URL}/argocd/apps/{app_name}/pods/{pod_name}/logs?namespace={namespace}&tail=1000" | python3 -c "import sys,json; data=json.load(sys.stdin); [print(l) for l in data['logs'].split('\n') if 'TRACE_ID_VALUE' in l]"
   ```
   Note: response is JSON with `logs` field (string). Use the correct namespace from step 4 pods response (NOT "default").
   List the matching log lines in **ascending chronological order** to show the full request flow through the service.

   **Analyse the trace logs and generate a summary:**
   - TraceId used
   - Number of log entries found
   - Request flow: entry point → each processing step → response (in order)
   - Any errors, exceptions, or warnings in the trace
   - Response status and latency if visible in logs
   - Verdict: **TRACE OK** (complete flow, no errors) or **TRACE INCOMPLETE** (missing steps / errors found)

8. **Report results as a pipeline summary table** using values from [Session Memory] + verification:
   ```
   ┌──────────────┬────────┬──────────────────────────────┐
   │ Step         │ Status │ Details                      │
   ├──────────────┼────────┼──────────────────────────────┤
   │ Build        │ ✅/❌  │ #{build_number} · {image_tag} │
   │ Deploy       │ ✅/❌  │ {deploy_env} · {repo}         │
   │ ArgoCD Sync  │ ✅/❌  │ {sync_status}, {health_status}│
   │ Pod Rollout  │ ✅/❌  │ {image_tag} ready / issues    │
   │ Log Sanity   │ ✅/⚠️  │ No errors / errors found     │
   │ Deps Health  │ ✅/⚠️  │ DB, Redis, Kafka status      │
   │ Trace Check  │ ✅/⚠️  │ traceId={id}, {n} entries    │
   └──────────────┴────────┴──────────────────────────────┘
   ```
   Use values from [Session Memory] for Build and Deploy rows (build_number, image_tag, deploy_env, repo).
   Fill ArgoCD Sync, Pod Rollout, and Log Sanity from verification results.
   Overall verdict: **HEALTHY** or **ISSUES FOUND**

9. **If issues found**, recommend [SKILL:rollback] with the previous revision number.

For deeper analysis: [SKILL:log-scan] for pod logs, [SKILL:_shared:kibana-logs] for app-level error rates, [SKILL:resource-monitor] for CPU/memory pressure.

## Error Handling

| Situation | Action |
|-----------|--------|
| All pods Running, correct image, 0 restarts | Healthy -- proceed |
| Pods Running but wrong image tag | Deploy may not have rolled out -- investigate |
| CrashLoopBackOff | Recommend immediate rollback |
| Pending pods | Check cluster resources via [SKILL:k8s-pods] |
| ImagePullBackOff | Check image tag, registry credentials |
| Restart count > 0 on fresh deploy | Check logs before proceeding |
| Sync OutOfSync | May resolve automatically -- wait and recheck |
| Health Degraded | Investigate before proceeding |
