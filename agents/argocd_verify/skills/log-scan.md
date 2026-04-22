---
name: log-scan
description: Scan ArgoCD pod logs for ERROR, FATAL, panic, OOM patterns — use for post-deploy verification
---

**When to use:** Default choice for post-deploy pod log verification. For application-level error rate analysis and latency comparison, use [SKILL:_shared:kibana-logs] instead.

## Workflow

1. **List all pods:**
   ```bash
   curl -sS "${BASE_URL}/argocd/apps/{app_name}/pods"
   ```

2. **Fetch logs for each pod:**
   ```bash
   curl -sS "${BASE_URL}/argocd/apps/{app_name}/pods/{pod_name}/logs?namespace=default&tail=200"
   ```

3. **Scan for critical patterns:**
   - **CRITICAL:** `FATAL`, `panic`, `OOMKilled`, `SIGKILL` -- immediate action
   - **ERROR:** `ERROR`, `Exception`, `Traceback` -- investigate, may need rollback
   - **WARNING:** `timeout`, `Connection refused` -- monitor, may be transient

4. **For each finding, extract context** (2 lines before + error + 2 lines after).

5. **Report summary:**
   - Total pods scanned
   - Errors per severity per pod
   - Specific error messages with timestamps
   - Recommendation: rollback, investigate, or all clear

6. **If critical errors found**, recommend [SKILL:rollback].

## Error Handling

| Situation | Action |
|-----------|--------|
| No critical patterns | All clear |
| ERROR patterns found | List with context, recommend investigation |
| FATAL/panic/OOM | Recommend immediate rollback |
| Logs unavailable | Flag pod, try previous container logs |
