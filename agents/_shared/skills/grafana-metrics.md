---
name: grafana-metrics
description: Query Grafana dashboards, panel metrics, alerts, and deploy annotations. Use for monitoring, post-deploy metric checks, incident triage, and performance analysis.
argument-hint: "<service-name or dashboard-name> [time_range]"
---

# /grafana-metrics

Query Grafana for dashboards, metrics, alerts, and annotations. Works for any agent that needs monitoring data — post-deploy checks, incident response, performance analysis, capacity planning.

## Usage

```
/grafana-metrics $ARGUMENTS
```

## Prerequisites

- `GRAFANA_URL` configured (run `/setup grafana` if not)
- `GRAFANA_USERNAME` / `GRAFANA_PASSWORD` — read-only service account credentials

## Available Operations

### 1. Search Dashboards

Find dashboards by service name or tag.

```bash
curl -sS -X POST "${BASE_URL}/grafana/dashboards/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "SERVICE_NAME", "limit": 10}'
```

Filter by tag:
```bash
curl -sS -X POST "${BASE_URL}/grafana/dashboards/search" \
  -H "Content-Type: application/json" \
  -d '{"tag": "production", "limit": 10}'
```

### 2. Get Dashboard Details

List all panels in a dashboard (after finding the UID from search).

```bash
curl -sS "${BASE_URL}/grafana/dashboards/{DASHBOARD_UID}"
```

Returns panel IDs, titles, types, and datasources.

### 3. Query Panel Data

Fetch actual metric data from a specific panel.

```bash
curl -sS -X POST "${BASE_URL}/grafana/panels/query" \
  -H "Content-Type: application/json" \
  -d '{"dashboard_uid": "UID", "panel_id": 1, "time_from": "now-1h", "time_to": "now"}'
```

**Time range examples:** `now-5m`, `now-15m`, `now-1h`, `now-6h`, `now-24h`, `now-7d`

### 4. Check Alerts

List all alerts:
```bash
curl -sS -X POST "${BASE_URL}/grafana/alerts" \
  -H "Content-Type: application/json" \
  -d '{"limit": 50}'
```

Get currently **firing** alerts only:
```bash
curl -sS "${BASE_URL}/grafana/alerts/firing"
```

### 5. Deploy Annotations

Mark a deployment on dashboards (useful for before/after correlation).

**Create annotation:**
```bash
curl -sS -X POST "${BASE_URL}/grafana/annotations" \
  -H "Content-Type: application/json" \
  -d '{"text": "Deploy v1.2.3 to qa4", "tags": ["deploy", "SERVICE"]}'
```

**List recent deploy annotations:**
```bash
curl -sS "${BASE_URL}/grafana/annotations?tags=deploy&limit=10"
```

### 6. List Datasources

Check which data sources (Prometheus, InfluxDB, etc.) are available.

```bash
curl -sS "${BASE_URL}/grafana/datasources"
```

### 7. Health Check

Verify Grafana connectivity:
```bash
curl -sS "${BASE_URL}/grafana/health"
```

## Common Workflows

### A. Post-Deploy Metric Check

1. Search for the service dashboard:
   ```bash
   curl -sS -X POST "${BASE_URL}/grafana/dashboards/search" -H "Content-Type: application/json" -d '{"query": "SERVICE"}'
   ```

2. Get dashboard panels:
   ```bash
   curl -sS "${BASE_URL}/grafana/dashboards/{UID}"
   ```

3. Query key panels (error rate, latency, throughput):
   ```bash
   curl -sS -X POST "${BASE_URL}/grafana/panels/query" -H "Content-Type: application/json" -d '{"dashboard_uid": "UID", "panel_id": PANEL_ID, "time_from": "now-1h"}'
   ```

4. Check for firing alerts:
   ```bash
   curl -sS "${BASE_URL}/grafana/alerts/firing"
   ```

5. Add deploy annotation for visibility:
   ```bash
   curl -sS -X POST "${BASE_URL}/grafana/annotations" -H "Content-Type: application/json" -d '{"text": "Deploy SERVICE v1.2.3", "tags": ["deploy"]}'
   ```

### B. Incident Triage

1. Check firing alerts → identify affected dashboards
2. Search dashboards by service name
3. Query error rate and latency panels for the affected time window
4. Correlate with deploy annotations to identify recent changes

### C. Before vs After Comparison

Query the same panel with two time ranges:
- **Before:** `"time_from": "now-2h", "time_to": "now-1h"`
- **After:** `"time_from": "now-1h", "time_to": "now"`

Compare values to detect regressions.

## Interpreting Results

| Signal | Meaning | Action |
|--------|---------|--------|
| No firing alerts | Metrics within thresholds | Likely healthy |
| Alert firing post-deploy | Metric crossed threshold | Investigate panel data |
| Error rate panel spike | More errors after change | Correlate with Kibana logs |
| Latency p99 spike | Slow requests increased | Profile specific endpoints |
| Throughput drop | Fewer requests being processed | Check if pods are healthy |

## Tips

- Use dashboard UIDs (not names) for API calls — get from search results
- Panel IDs are integers visible in the dashboard JSON — get from dashboard details
- Annotations with `deploy` tag show as vertical lines on all dashboards
- Combine with [SKILL:_shared:kibana-logs] for full observability: Grafana for metrics, Kibana for logs
