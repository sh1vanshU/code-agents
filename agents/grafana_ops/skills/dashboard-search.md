---
name: dashboard-search
description: Search and explore Grafana dashboards
---

## Workflow

1. **Search dashboards by keyword or tag:**
   ```bash
   curl -sS -X POST ${BASE_URL}/grafana/dashboards/search -H "Content-Type: application/json" -d '{"query":"KEYWORD","limit":20}'
   ```

2. **Get dashboard details and panels:**
   ```bash
   curl -sS "${BASE_URL}/grafana/dashboards/${uid}"
   ```

3. **List datasources if needed:**
   ```bash
   curl -sS "${BASE_URL}/grafana/datasources"
   ```

4. **Report:** Dashboard name, panels available, datasource types.
