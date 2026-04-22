---
name: baseline-manager
description: Save, compare, and reset regression baselines (test results, performance, contracts)
---

## Workflow

1. **Save baseline** — save current state as the known-good baseline:
   - .code-agents/{repo}.regression-baseline.json (test pass/fail)
   - .code-agents/{repo}.perf-baseline.json (endpoint timings)
   - .code-agents/{repo}.contracts.json (API response structures)

2. **Compare with baseline** — diff current results vs saved baseline.

3. **Reset baseline** — delete saved baselines, next run creates new ones.

4. **List baselines** — show saved baselines with dates and stats.
