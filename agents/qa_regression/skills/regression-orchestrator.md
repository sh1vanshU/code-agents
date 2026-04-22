---
name: regression-orchestrator
description: Full regression orchestration — functional, API, performance, contract, logs, Jira update, verdict
---

## Before You Start
- All baselines saved (regression, performance, contracts)
- Non-prod environment running with latest code deployed
- Jira ticket key available for status updates

## Workflow

1. **Functional Regression:** [SKILL:regression-suite]
   Run full test suite, compare with baseline.

2. **Targeted Regression:** [SKILL:targeted-regression]
   Run tests only for changed areas.

3. **API Regression:** [SKILL:qa-regression:api-testing]
   Run discovered endpoints, validate responses.

4. **Performance Regression:** [SKILL:performance-regression]
   Compare endpoint response times vs baseline.

5. **Contract Validation:** [SKILL:contract-validation]
   Check for breaking API contract changes.

6. **Log Correlation:**
   ```bash
   curl -sS -X POST "${CODE_AGENTS_PUBLIC_BASE_URL}/kibana/errors" -H "Content-Type: application/json" -d '{"service": "SERVICE_NAME", "time_range": "15m"}'
   ```
   Check for errors generated during test execution.

7. **Combined Report:**
   ```
   ┌─────────────────────────────────────────┐
   │         REGRESSION REPORT                │
   ├─────────────────────────────────────────┤
   │ Functional:  ✅ 442/450 pass (3 new)    │
   │ API:         ✅ 35/35 endpoints OK       │
   │ Performance: ⚠ 1 WARNING, 0 CRITICAL    │
   │ Contracts:   ✅ No breaking changes       │
   │ Logs:        ✅ No new errors             │
   ├─────────────────────────────────────────┤
   │ VERDICT: ✅ PASS — Ready for deployment  │
   └─────────────────────────────────────────┘
   ```

8. **Update Jira:**
   ```bash
   curl -sS -X POST "${CODE_AGENTS_PUBLIC_BASE_URL}/jira/issue/TICKET_KEY/comment" -H "Content-Type: application/json" -d '{"body": "Regression PASSED: 442/450 tests, 35/35 endpoints, no breaking contracts."}'
   ```

9. **Verdict:** PASS (deploy ready) or FAIL (fix required with specific failures listed).

## Definition of Done
- All 5 regression types executed
- Combined report generated
- Jira updated with results
- Clear PASS/FAIL verdict
