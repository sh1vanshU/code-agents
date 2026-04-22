---
name: jacoco-report
description: Parse JaCoCo XML report and produce a structured coverage summary with per-class metrics
---

## Workflow

1. **Run the test suite with JaCoCo report generation.**
   ```bash
   mvn clean test jacoco:report -q
   ```
   If tests fail, report failures and stop. Coverage numbers from a partial run are unreliable.

2. **Locate and read the JaCoCo XML report.**
   The default path is `target/site/jacoco/jacoco.xml`. For multi-module projects, check each module:
   ```bash
   find . -path "*/site/jacoco/jacoco.xml" -type f
   ```
   Read the XML file and parse the coverage counters.

3. **Extract overall project coverage.** From the root `<counter>` elements:
   - **LINE** coverage: covered / (covered + missed)
   - **BRANCH** coverage: covered / (covered + missed)
   - **METHOD** coverage: covered / (covered + missed)
   - **CLASS** coverage: covered / (covered + missed)
   - **INSTRUCTION** coverage: covered / (covered + missed)

4. **Extract per-class coverage.** For each `<class>` element, calculate:
   - Class fully qualified name
   - Line coverage percentage
   - Branch coverage percentage
   - Method coverage percentage
   - Total lines (covered + missed)

5. **Output the structured coverage table.** Color-code by threshold (default 80%):
   ```
   JaCoCo Coverage Report
   Generated: 2025-01-15 14:30

   Overall:
     Lines:        87.3%  (2,341 / 2,682)
     Branches:     74.1%  (891 / 1,202)
     Methods:      91.2%  (456 / 500)

   Per-Class Coverage (sorted by line coverage ascending):

   Status  Class                                    Lines    Branches  Methods
   RED     com.app.payment.RefundService             23.4%    10.0%     40.0%
   RED     com.app.auth.TokenValidator               41.2%    25.3%     55.6%
   RED     com.app.order.OrderProcessor              55.0%    48.7%     66.7%
   YELLOW  com.app.api.OrderController               72.8%    65.0%     80.0%
   GREEN   com.app.service.UserService               92.1%    88.5%     95.0%
   GREEN   com.app.config.AppConfig                 100.0%   100.0%    100.0%

   Legend: RED = below 60%, YELLOW = 60-79%, GREEN = 80%+
   ```

6. **Show the worst 10 classes.** These are the highest-priority targets for new tests. For each, list:
   - Number of missed lines
   - Number of missed branches
   - Package name (to identify which area of the codebase is weakest)

7. **Show the best 10 classes.** Highlight what is already well-tested. This helps identify patterns — well-tested packages often share a testing approach that can be replicated.

8. **Show package-level summary.** Aggregate per-class numbers into per-package coverage:
   ```
   Package                          Lines    Branches  Classes Below Threshold
   com.app.payment                  45.2%    32.1%     3 / 5
   com.app.auth                     58.7%    41.0%     2 / 3
   com.app.order                    71.3%    65.8%     1 / 4
   com.app.service                  89.4%    85.2%     0 / 6
   ```

9. **Show coverage trend if previous report exists.** Compare against the last known coverage numbers (from CI artifacts or a stored baseline):
   ```
   Trend (vs last run):
     Lines:    87.3%  (+2.1%)
     Branches: 74.1%  (+3.5%)
     Methods:  91.2%  (+0.8%)
   ```
   If no previous data is available, note this is the baseline.

10. **Summarize actionable next steps.** Based on the report:
    - If overall coverage is below threshold: recommend running `[SKILL:coverage-plan]`
    - If specific classes are critically low: recommend `[SKILL:write-unit-tests]` for those classes
    - If branch coverage lags line coverage: highlight complex conditional logic that needs more test paths
