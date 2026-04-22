---
name: query-metrics
description: Query Grafana panel metrics for a service or dashboard
---

## Before Starting

Check [Session Memory] for dashboard_uid, panel_id, service name.

## Workflow

1. **Find the dashboard:**
   ```bash
   curl -sS -X POST ${BASE_URL}/grafana/dashboards/search -H "Content-Type: application/json" -d '{"query":"SERVICE_NAME","limit":10}'
   ```
   → Emit: `[REMEMBER:dashboard_uid=<uid>]`

2. **Get dashboard panels:**
   ```bash
   curl -sS "${BASE_URL}/grafana/dashboards/${dashboard_uid}"
   ```
   → Identify relevant panels (latency, error rate, throughput, etc.)
   → Emit: `[REMEMBER:panel_id=<id>]`

3. **Query panel data:**
   ```bash
   curl -sS -X POST ${BASE_URL}/grafana/panels/query -H "Content-Type: application/json" -d '{"dashboard_uid":"UID","panel_id":ID,"time_from":"now-1h","time_to":"now"}'
   ```

4. **Interpret results:** Summarize metric values, trends, anomalies.

## Definition of Done

- Metric data retrieved and summarized
- Anomalies or notable values highlighted
