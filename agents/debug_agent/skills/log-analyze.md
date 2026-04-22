---
name: log-analyze
description: Log analyzer — correlate entries, build timeline, find root cause
tags: [debug, logs, timeline, correlation]
---

# Log Analyzer

## Workflow

1. **Ingest logs** — Accept raw log text, file paths, or Kibana query results.
2. **Parse entries** — Extract timestamp, level, service, request-id, and message from each line.
3. **Correlate** — Group entries by request-id or trace-id; link related events across services.
4. **Build timeline** — Order correlated entries chronologically; highlight latency gaps and level escalations.
5. **Detect anomalies** — Flag: repeated errors, sudden rate spikes, timeout cascades, missing expected events.
6. **Root cause** — Identify the earliest error or anomaly that triggered downstream failures.
7. **Report** — Return: timeline summary, root cause, affected services, and recommended next steps.

## Notes

- Support common formats: JSON structured logs, syslog, log4j, Python logging.
- For large log volumes, ask the user to filter by time window or service first.
