---
name: run-endpoints
description: Run discovered endpoints and diagnose failures
trigger: "[SKILL:run-endpoints]"
agent: qa_regression
tags: [endpoints, testing, smoke-test, api]
---

# Run Endpoints Skill

Execute all discovered REST/gRPC/Kafka endpoints against a running service and generate a diagnostic report.

## Workflow

### Step 1 — Load or Scan Endpoints

1. Check for cached scan results in `.code-agents/{repo}.endpoints.cache.json`
2. If no cache exists, run a full scan via `endpoint_scanner.scan_all()`
3. Save results to cache for future runs

### Step 2 — Load Config

1. Read `.code-agents/endpoints.yaml` for per-repo settings:
   - `base_url` — target server (default: `http://localhost:8080`)
   - `auth_header` — Authorization header value (e.g., `Bearer <token>`)
   - `timeout` — seconds per request (default: 10)
   - `skip_patterns` — glob patterns to skip (e.g., `/actuator/*`, `/health`)
2. Fall back to defaults if no config file exists

### Step 3 — Run Each Endpoint

For each discovered endpoint:
- REST: execute curl with `-o /dev/null -w "%{http_code}"` to capture HTTP status
- gRPC: execute grpcurl with plaintext flag
- Kafka: execute kafka-console-producer with test payload
- Capture: status code, response body (truncated), stderr, exit code, duration

### Step 4 — Classify Results

| Status       | Classification | Action                              |
|-------------|----------------|-------------------------------------|
| 200-299     | PASS           | No action needed                    |
| 400-499     | CHECK          | Review request params, auth headers |
| 500-599     | ERROR          | Diagnose server-side failure        |
| Timeout     | WARN           | Check if service is running         |
| Exit code 7 | CONN_REFUSED   | Service not reachable               |

### Step 5 — Generate Report

Output a summary table:
```
Endpoint Test Report: X passed, Y failed (Z total)

  PASS [rest ] curl -sS ... /api/v1/users                                200  45ms
  FAIL [rest ] curl -sS ... /api/v1/orders                               500  120ms
       error: Internal Server Error
  FAIL [grpc ] grpcurl ... PaymentService/GetStatus                      timeout
       error: Timed out after 10s
```

### Step 6 — Diagnose Failures

For each failure:
1. Check if the service is running (connection refused = service down)
2. Check if auth is needed (401/403 = missing or invalid credentials)
3. Check if the endpoint expects a request body (400 on POST/PUT without body)
4. For 500 errors: suggest checking server logs via `[DELEGATE:kibana-ops]`
5. For code bugs: delegate fix to `[DELEGATE:code-writer]`

## Usage

```
/endpoints run           — run all endpoints
/endpoints run rest      — run REST endpoints only
/endpoints run grpc      — run gRPC endpoints only
/endpoints run kafka     — run Kafka endpoints only
```

## Dependencies

- `code_agents.cicd.endpoint_scanner` — scan, run, format functions
- `.code-agents/endpoints.yaml` — optional per-repo config
- Running target service for meaningful results
