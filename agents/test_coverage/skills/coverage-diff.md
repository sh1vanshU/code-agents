---
name: coverage-diff
description: Compare coverage before and after changes
---

## Workflow

1. **Run tests on the base branch** to get the baseline coverage.
   ```bash
   curl -sS -X POST ${BASE_URL}/testing/run \
     -H "Content-Type: application/json" \
     -d '{"branch": "main", "coverage_threshold": 0}'
   ```
   Record the overall coverage percentage and per-file numbers.

2. **Run tests on the head branch** to get the current coverage.
   ```bash
   curl -sS -X POST ${BASE_URL}/testing/run \
     -H "Content-Type: application/json" \
     -d '{"branch": "feature-branch", "coverage_threshold": 0}'
   ```

3. **Get the coverage gaps for new code.**
   ```bash
   curl -sS "${BASE_URL}/testing/gaps?base=main&head=feature-branch"
   ```

4. **Compare the two reports.** For each file, calculate:
   - Coverage before (base branch)
   - Coverage after (head branch)
   - Delta (increase or decrease)

5. **Identify coverage regressions.** Flag any file where coverage decreased — these are the most important to address.

6. **Check new code coverage.** All new lines added on the feature branch should have tests. Report the percentage of new lines covered.

7. **Present a comparison table:**
   ```
   Coverage Diff: main...feature-branch

   Overall: 85% --> 87% (+2%)

   File                        Before   After    Delta
   src/api/payments.py         90%      92%      +2%
   src/services/refund.py      75%      70%      -5%  <-- REGRESSION
   src/models/order.py         NEW      85%

   New code coverage: 91% (45/49 new lines covered)
   Uncovered new lines:
     src/models/order.py:23-26  — error handling path
   ```

8. **Give a verdict:** coverage improved, stayed the same, or regressed. Block the PR if new code coverage is below threshold or if existing coverage regressed.
