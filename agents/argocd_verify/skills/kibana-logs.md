---
name: kibana-logs
description: Search Kibana for error rates, latency analysis, before-vs-after comparison — use for application-level log analysis
---

**When to use:** For error rate comparison (before vs after deploy), latency percentile analysis, and application-level log search. For raw pod log scanning, use [SKILL:log-scan] instead.

## Prerequisites

- [ ] Know the deployment timestamp (for before vs after comparison)
- [ ] Know the service name as it appears in Kubernetes app labels

## Workflow

1. **Search recent errors:**
   ```bash
   curl -sS -X POST "${BASE_URL}/kibana/search" -H "Content-Type: application/json" -d '{"service": "SVC", "log_level": "ERROR", "time_range": "15m", "size": 50}'
   ```

2. **Get error summary (top patterns):**
   ```bash
   curl -sS -X POST "${BASE_URL}/kibana/errors" -H "Content-Type: application/json" -d '{"service": "SVC", "time_range": "15m", "top_n": 10}'
   ```

3. **Check for FATAL/panic:**
   ```bash
   curl -sS -X POST "${BASE_URL}/kibana/search" -H "Content-Type: application/json" -d '{"service": "SVC", "query": "FATAL OR panic OR OOMKilled", "time_range": "15m", "size": 20}'
   ```

4. **Compare error rate before vs after.** Get 1-hour baseline:
   ```bash
   curl -sS -X POST "${BASE_URL}/kibana/errors" -H "Content-Type: application/json" -d '{"service": "SVC", "time_range": "1h", "top_n": 10}'
   ```
   Project 15-minute post-deploy count to 1 hour for fair comparison. Small spike immediately after deploy may be normal (cache warm-up).

5. **Report verdict:**
   - **Healthy:** No new error patterns, error count stable or decreasing
   - **Issues found:** New patterns, rate spiked, or FATAL/panic present -- recommend rollback

## Error Rate Thresholds

| Metric | Verdict |
|--------|---------|
| Same error patterns, similar count | Healthy (pre-existing) |
| New ERROR patterns post-deploy | Investigate |
| Any FATAL or panic | Critical -- recommend rollback |
| Error count 3x+ higher than baseline | Recommend rollback |
| p99 latency spike with stable p50 | New slow code path for specific inputs |

## Latency Analysis

If latency data available in logs:
- p50 change = affects all users
- p95/p99 change = affects complex requests
- p99 spike + stable p50 = new slow code path
