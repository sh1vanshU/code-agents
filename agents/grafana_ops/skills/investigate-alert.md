---
name: investigate-alert
description: Investigate a firing Grafana alert — find root cause, check related metrics
---

## Workflow

1. **Check firing alerts:**
   ```bash
   curl -sS "${BASE_URL}/grafana/alerts/firing"
   ```

2. **For each firing alert, get the dashboard context:**
   ```bash
   curl -sS "${BASE_URL}/grafana/dashboards/${dashboard_uid}"
   ```

3. **Query the alert's panel data over multiple time ranges:**
   - Last 5 minutes (immediate): `time_from=now-5m`
   - Last 1 hour (trend): `time_from=now-1h`
   - Last 24 hours (baseline): `time_from=now-24h`

4. **Check for recent deploys** that may have caused the alert:
   ```bash
   curl -sS "${BASE_URL}/grafana/annotations?tags=deploy&limit=5"
   ```

5. **Correlate:** Compare metric change timing with deploy annotations.

6. **Report findings:** Alert details, when it started, possible root cause, whether a deploy correlates.

## Definition of Done

- Alert context understood
- Root cause hypothesis formed
- Recommended action (rollback, fix, acknowledge)
