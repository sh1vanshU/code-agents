---
name: kibana-logs
description: Search Kibana/Elasticsearch logs — error search, pattern aggregation, before-vs-after comparison, FATAL detection. Use for any log investigation, incident triage, post-deploy verification, or debugging.
argument-hint: "<service-name> [time_range] [log_level]"
---

# /kibana-logs

Search and analyze application logs via Kibana. Works for any agent that needs log data — post-deploy checks, incident response, debugging, monitoring.

## Usage

```
/kibana-logs $ARGUMENTS
```

## Prerequisites

- `KIBANA_URL` configured (run `/setup kibana` if not)
- Know the service name as it appears in Kubernetes app labels

## Available Operations

### 1. Search Logs

Search logs by service, level, time range, or free-text query.

```bash
curl -sS -X POST "${BASE_URL}/kibana/search" \
  -H "Content-Type: application/json" \
  -d '{"service": "SERVICE", "log_level": "ERROR", "time_range": "15m", "size": 50}'
```

**Parameters:**
| Param | Type | Description | Default |
|-------|------|-------------|---------|
| `index` | string | Index pattern (e.g. `logs-*`) | auto |
| `query` | string | Lucene query on `message` field | `*` |
| `service` | string | Filter by `kubernetes.labels.app` | — |
| `log_level` | string | `ERROR`, `WARN`, `FATAL`, `INFO`, `DEBUG` | — |
| `time_range` | string | `5m`, `15m`, `30m`, `1h`, `3h`, `6h`, `12h`, `24h` | `15m` |
| `size` | int | Max results to return | `100` |

### 2. Error Summary (Top Patterns)

Aggregate top error patterns by frequency.

```bash
curl -sS -X POST "${BASE_URL}/kibana/errors" \
  -H "Content-Type: application/json" \
  -d '{"service": "SERVICE", "time_range": "1h", "top_n": 10}'
```

### 3. List Available Indices

```bash
curl -sS "${BASE_URL}/kibana/indices"
```

## Common Workflows

### A. Quick Error Check

Search recent errors for a service:
```bash
curl -sS -X POST "${BASE_URL}/kibana/search" \
  -H "Content-Type: application/json" \
  -d '{"service": "SERVICE", "log_level": "ERROR", "time_range": "15m", "size": 50}'
```

### B. FATAL/Panic Detection

Search for critical failures:
```bash
curl -sS -X POST "${BASE_URL}/kibana/search" \
  -H "Content-Type: application/json" \
  -d '{"service": "SERVICE", "query": "FATAL OR panic OR OOMKilled OR OutOfMemoryError", "time_range": "15m", "size": 20}'
```

### C. Before vs After Comparison

1. Get baseline (1h window before the event):
   ```bash
   curl -sS -X POST "${BASE_URL}/kibana/errors" \
     -H "Content-Type: application/json" \
     -d '{"service": "SERVICE", "time_range": "1h", "top_n": 10}'
   ```

2. Get post-event errors (15m window):
   ```bash
   curl -sS -X POST "${BASE_URL}/kibana/errors" \
     -H "Content-Type: application/json" \
     -d '{"service": "SERVICE", "time_range": "15m", "top_n": 10}'
   ```

3. Project 15m count to 1h (`count * 4`) for fair comparison.

### D. Free-Text Search

Search for specific keywords in log messages:
```bash
curl -sS -X POST "${BASE_URL}/kibana/search" \
  -H "Content-Type: application/json" \
  -d '{"service": "SERVICE", "query": "timeout OR connection refused", "time_range": "30m", "size": 50}'
```

## Interpreting Results

| Signal | Meaning | Action |
|--------|---------|--------|
| Same error patterns, similar count | Pre-existing (stable) | No action needed |
| New error patterns post-event | Likely caused by recent change | Investigate |
| Any FATAL or panic | Critical | Escalate / rollback |
| Error count 3x+ higher than baseline | Significant spike | Investigate / rollback |
| p99 latency spike + stable p50 | New slow code path | Profile specific inputs |

## Report Format

```
Kibana Log Analysis: {service}
Time Range: {time_range}

Errors Found: {total}
Top Patterns:
  1. {pattern} — {count} occurrences
  2. {pattern} — {count} occurrences

FATAL/Panic: {none | details}
Verdict: {Healthy | Investigate | Critical}
```

## Tips

- Use `time_range: "5m"` for real-time debugging, `"1h"` for baselines
- Combine with ArgoCD pod logs for full picture — Kibana shows app-level, pod logs show infra-level
- Small error spikes right after deploy may be normal (cache warm-up, connection pool init)
- For index-specific searches, list indices first and pick the right pattern
