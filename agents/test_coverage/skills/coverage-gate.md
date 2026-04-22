---
name: coverage-gate
description: Pipeline quality gate that blocks on coverage threshold with detailed gap report
---

## Workflow

1. **Run the full test suite with JaCoCo coverage.**
   ```bash
   mvn clean test jacoco:report -q
   ```
   If any test fails, the gate is **FAIL** immediately. Report the test failures and stop. Broken tests are a harder blocker than low coverage.

2. **Parse the JaCoCo XML report.** Read `target/site/jacoco/jacoco.xml` and extract:
   - Overall line coverage percentage
   - Overall branch coverage percentage
   - Per-class line and branch coverage

3. **Compare against the coverage threshold.** Default threshold is 80%. Check both line and branch coverage. The gate passes only if BOTH metrics meet the threshold:
   ```
   Coverage Gate Check
   Threshold:        80%
   Line Coverage:    87.3%   PASS
   Branch Coverage:  74.1%   FAIL

   Verdict: FAIL (branch coverage below threshold)
   ```

4. **If PASS: report success and allow the pipeline to proceed.**
   ```
   COVERAGE GATE: PASS

   Line Coverage:    87.3%  (threshold: 80%)
   Branch Coverage:  82.1%  (threshold: 80%)

   All metrics meet the required threshold. Pipeline may proceed.
   ```

5. **If FAIL: produce a detailed gap report.** List every class that is below the threshold, sorted by gap size:
   ```
   COVERAGE GATE: FAIL

   Line Coverage:    72.3%  (threshold: 80%, gap: -7.7%)
   Branch Coverage:  65.1%  (threshold: 80%, gap: -14.9%)

   Classes Below Threshold (sorted by impact):

   Class                                    Lines    Branches  Lines Needed
   com.app.payment.RefundService             23.4%    10.0%     +34 lines
   com.app.auth.TokenValidator               41.2%    25.3%     +22 lines
   com.app.order.OrderProcessor              55.0%    48.7%     +18 lines
   com.app.api.WebhookHandler                68.0%    52.0%     +8 lines

   Total lines to cover to reach 80%: ~82 lines across 4 classes
   ```

6. **Calculate the minimum work to pass.** Estimate how many additional test lines/methods would bring coverage above the threshold. Focus on the classes with the largest gap — covering the worst offenders has the highest impact on overall numbers:
   ```
   Fastest Path to 80%:
   1. Cover RefundService.processRefund() — +3.2% overall
   2. Cover TokenValidator.validate() — +2.1% overall
   3. Cover OrderProcessor.submitOrder() — +1.8% overall

   These 3 methods alone would bring coverage to 79.4%.
   Add OrderProcessor.cancelOrder() to reach 80.6%.
   ```

7. **For SDLC pipeline integration:** When this skill is invoked as part of a pipeline (via `[SKILL:pipeline_orchestrator:advance]` or `[SKILL:auto_pilot:full-sdlc]`), the gate blocks advancement to the next stage:
   - **PASS** — Pipeline continues to the next step (deploy, review, etc.)
   - **FAIL** — Pipeline is blocked. The user must either:
     - Write tests to close the gap (delegate to `[SKILL:write-unit-tests]` or `[SKILL:write-integration-tests]`)
     - Override the gate with explicit user confirmation: "I acknowledge coverage is below threshold, proceed anyway"
   - Never auto-override. The user must explicitly approve proceeding with insufficient coverage.

8. **Output a machine-parseable summary** for CI integration:
   ```
   GATE_RESULT=FAIL
   LINE_COVERAGE=72.3
   BRANCH_COVERAGE=65.1
   THRESHOLD=80
   LINE_GAP=-7.7
   BRANCH_GAP=-14.9
   CLASSES_BELOW_THRESHOLD=4
   ```

9. **Recommend next actions based on the result:**
   - **FAIL, small gap (<5%):** "Run `[SKILL:coverage-plan]` to identify quick wins"
   - **FAIL, medium gap (5-15%):** "Run `[SKILL:coverage-plan]` then `[SKILL:write-unit-tests]` for the top 5 classes"
   - **FAIL, large gap (>15%):** "Coverage is significantly below threshold. Consider a dedicated sprint for test coverage"
   - **PASS, close to threshold:** "Coverage is passing but at risk. Consider adding tests to maintain buffer"
