---
name: find-gaps
description: Identify files and functions below coverage threshold
---

## Workflow

1. **Get the coverage report** for the current state.
   ```bash
   curl -sS "${BASE_URL}/testing/coverage"
   ```

2. **Get coverage gaps** comparing the branch against main.
   ```bash
   curl -sS "${BASE_URL}/testing/gaps?base=main&head=feature-branch"
   ```
   This returns specific new lines that lack test coverage.

3. **Identify files below the threshold.** Filter the coverage report for files under the target percentage (default 100%). Sort by coverage ascending.

4. **For each under-covered file, identify the specific gaps:**
   - Which functions/methods have no tests?
   - Which branches (if/else paths) are uncovered?
   - Which error handling paths lack coverage?
   - List specific line number ranges that are untested

5. **Categorize gaps by risk:**
   - HIGH: Business logic, payment processing, auth checks — must be tested
   - MEDIUM: API endpoints, data transformations — should be tested
   - LOW: Utility functions, logging, config — nice to have

6. **Report the gaps in a structured format:**
   ```
   Coverage Gaps Report
   Threshold: 100%
   Current:   87%

   HIGH RISK (must fix):
     src/services/payment.py:45-67  — refund logic, 0% covered
     src/api/auth.py:23-41          — token validation, no tests

   MEDIUM RISK:
     src/api/webhooks.py:89-102     — error handler, uncovered

   LOW RISK:
     src/utils/logging.py:12-20     — log formatter, uncovered
   ```

7. **Estimate effort** to close the gaps: number of test cases needed per file.

8. **Recommend next steps:** write missing tests (delegate to code-tester or qa-regression), or adjust the threshold if the gaps are acceptable.
