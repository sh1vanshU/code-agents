---
name: correlate-deploy
description: Correlate a deployment with metric changes — before/after comparison
---

## Workflow

1. **Find recent deploy annotations:**
   ```bash
   curl -sS "${BASE_URL}/grafana/annotations?tags=deploy&limit=5"
   ```

2. **Find the service dashboard:**
   ```bash
   curl -sS -X POST ${BASE_URL}/grafana/dashboards/search -H "Content-Type: application/json" -d '{"query":"SERVICE_NAME","limit":5}'
   ```

3. **Query key metrics BEFORE deploy** (e.g. -2h to -1h before annotation time):
   ```bash
   curl -sS -X POST ${BASE_URL}/grafana/panels/query -H "Content-Type: application/json" -d '{"dashboard_uid":"UID","panel_id":ID,"time_from":"now-2h","time_to":"now-1h"}'
   ```

4. **Query same metrics AFTER deploy** (last 1 hour):
   ```bash
   curl -sS -X POST ${BASE_URL}/grafana/panels/query -H "Content-Type: application/json" -d '{"dashboard_uid":"UID","panel_id":ID,"time_from":"now-1h","time_to":"now"}'
   ```

5. **Compare:** Latency delta, error rate change, throughput change.

6. **Verdict:** Deploy is clean / Deploy introduced regression → suggest rollback.
