---
name: run-coverage
description: Run tests with coverage, report percentages by file
---

## Workflow

1. **Run the test suite with coverage enabled.**
   ```bash
   curl -sS -X POST ${BASE_URL}/testing/run \
     -H "Content-Type: application/json" \
     -d '{"branch": "feature-branch", "test_command": null, "coverage_threshold": 100}'
   ```
   The test runner auto-detects the framework (pytest, jest, maven, gradle, go) and generates coverage.

2. **Check if tests passed.** If any tests fail, report the failures first. Do not proceed to coverage analysis until tests pass.

3. **Get the coverage report.**
   ```bash
   curl -sS "${BASE_URL}/testing/coverage"
   ```

4. **Parse the coverage report.** Extract:
   - Overall coverage percentage
   - Per-file coverage percentages
   - Number of lines covered vs. total lines
   - Number of branches covered vs. total branches (if available)

5. **Rank files by coverage.** Sort from lowest to highest coverage to highlight the weakest areas:
   ```
   File                          Lines    Coverage
   src/services/retry.py         45       22%
   src/api/webhooks.py           120      65%
   src/models/payment.py         80       78%
   src/config.py                 30       100%
   ```

6. **Compare against the threshold.** Default is 100%. Report whether the project meets the threshold or falls short.

7. **Report both overall and incremental coverage.** Overall is the full project; incremental is only new/changed code on this branch.

8. **Summarize with a clear pass/fail verdict** and list the top files that need more test coverage.
