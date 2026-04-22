---
name: sanity-check
description: Post-deploy sanity verification using Kibana logs and per-repo rules (.code-agents/sanity.yaml)
---

## Prerequisites

- [ ] Deployment complete (pods Running, ArgoCD Synced + Healthy)
- [ ] Know the service name (K8s app label)

## Workflow

1. **Load sanity rules** from `.code-agents/sanity.yaml`. Each rule has:
   - **name:** human-readable label
   - **query:** Kibana/Lucene query
   - **threshold:** max allowed matches (0 = zero tolerance)
   - **time_window:** how far back to search
   - **severity:** critical, warning, info

   If no `sanity.yaml` exists, use defaults:
   - No 5xx errors (`level:ERROR AND status:5*`, threshold=0, 5m, critical)
   - No OOM kills (`OOMKilled OR OutOfMemory`, threshold=0, 10m, critical)
   - No panic/fatal (`level:FATAL OR panic`, threshold=0, 5m, critical)
   - Startup complete (`Started Application`, threshold>=1, 5m, info)

2. **Query Kibana for each rule** (one at a time):
   ```bash
   curl -sS -X POST "${BASE_URL}/kibana/search" -H "Content-Type: application/json" -d '{"service": "SVC", "query": "RULE_QUERY", "time_range": "TIME_WINDOW", "size": 5}'
   ```

3. **Evaluate:** `match_count <= threshold` = PASS, otherwise FAIL. Collect up to 3 sample lines from failures.

4. **Generate report:**
   ```
   SANITY CHECK REPORT
   ===================
   PASS/FAIL  Rule Name        (count/threshold)
     sample log line (if failed)

   VERDICT: ALL PASSED / N FAILED
   ```

5. **Handle failures:**
   - **Critical fails:** Recommend [SKILL:rollback]. Include failing log samples.
   - **Warning fails:** Re-run in 10 minutes. Check if decreasing (cold cache) or increasing (regression).
   - **Info fails:** Note in report, no action needed.

## Example sanity.yaml

```yaml
rules:
  - name: "No 5xx errors"
    query: "level:ERROR AND status:5*"
    threshold: 0
    time_window: "5m"
    severity: critical

  - name: "Latency under 500ms"
    query: "response_time:>500"
    threshold: 10
    time_window: "5m"
    severity: warning

  - name: "No OOM kills"
    query: "OOMKilled OR OutOfMemory"
    threshold: 0
    time_window: "10m"
    severity: critical
```
