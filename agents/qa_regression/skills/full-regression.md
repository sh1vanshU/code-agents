---
name: full-regression
description: Run full test suite, report pass/fail/skip, identify flaky tests
---

## Workflow

1. **Discover the test framework and existing tests.** Read the project structure to identify the test runner (pytest, jest, JUnit, go test) and test directories.

2. **Run the full test suite.**
   ```bash
   curl -sS -X POST ${BASE_URL}/testing/run \
     -H "Content-Type: application/json" \
     -d '{"branch": "release", "test_command": null, "coverage_threshold": 80}'
   ```

3. **Parse the results.** Extract:
   - Total tests, passed, failed, skipped, errored
   - Coverage percentage (overall and per-file)
   - Duration of the test run

4. **For each failing test, analyze the failure:**
   - Read the test code and the code under test
   - Identify whether it is a real bug or a flaky test
   - Check if the test passes when run in isolation (indicates shared state issue)

5. **Identify flaky tests.** A test is flaky if:
   - It fails intermittently (passes on retry)
   - It depends on timing, network, or shared state
   - It passes in isolation but fails in suite
   Mark flaky tests for investigation.

6. **Get coverage gaps for new code.**
   ```bash
   curl -sS "${BASE_URL}/testing/gaps?base=main&head=release"
   ```

7. **Report the regression test results:**
   ```
   === Regression Test Report ===
   Total tests:    247
   Passed:         245
   Failed:         1
   Skipped:        1
   Coverage:       87%

   Failed tests:
     test_payment_timeout — Expected 408, got 500

   Flaky tests:
     test_async_webhook — intermittent timeout

   Coverage gaps:
     src/new_module.py — 0% (no tests)
   ```

8. **Give a pass/fail verdict** for the regression. Block release if critical tests fail or coverage is below threshold.
