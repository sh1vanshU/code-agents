---

## name: performance-regression
description: Detect performance regressions — compare endpoint response times against baseline

## Before You Start

- Endpoints discovered (run /endpoints scan if needed)
- Performance baseline exists (.code-agents/{repo}.perf-baseline.json)
- Non-prod environment running

## Workflow

1. **Load endpoint cache and baseline timings.**
2. **For each REST endpoint, run 3 times with timing:**
  ```bash
   curl -sS -o /dev/null -w "%{time_total}" "http://BASE_URL/endpoint"
  ```
   Take the median of 3 runs.
3. **Compare with baseline:**
  - OK: within 20% of baseline
  - WARNING: 20-100% slower
  - CRITICAL: >2x slower
4. **Report:**
  ```
   Performance Regression:
     Endpoint                    Baseline  Current  Delta   Status
     GET /api/v1/payments        120ms     145ms    +21%   ⚠ WARNING
     POST /api/v1/orders         200ms     190ms    -5%    ✅ OK
     GET /api/v1/users/{id}      50ms      110ms    +120%  ❌ CRITICAL
  ```
5. **For CRITICAL:** Investigate — check if new code added N+1 queries, missing indexes, or expensive operations.

## Definition of Done

- No CRITICAL performance regressions
- All WARNING items acknowledged or explained

