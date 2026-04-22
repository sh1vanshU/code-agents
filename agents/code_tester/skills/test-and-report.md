---
name: test-and-report
description: Run tests, parse results, get coverage, generate structured report with failure summary
---

## Before You Start

- [ ] Confirm which test suite to run (unit, integration, or full) — running everything when you only need unit tests wastes time
- [ ] Verify the test environment is clean (no leftover state from previous runs, databases reset if needed)
- [ ] Check if there are known flaky tests — consult CI history or team notes to avoid false alarms
- [ ] Know the coverage threshold for this project (default 80%, but some modules may have different targets)

## Workflow

1. **Run the test suite.** Execute tests via the testing API:
   ```bash
   curl -s -X POST ${BASE_URL}/testing/run \
     -H "Content-Type: application/json" \
     -d '{"branch": null, "test_command": null, "coverage_threshold": 80}'
   ```

2. **Parse the test results.** From the response, extract:
   - Total tests run
   - Tests passed
   - Tests failed (with names, files, and error messages)
   - Tests skipped (with reasons if available)
   - Test execution time

3. **Get coverage report.** Fetch the coverage data:
   ```bash
   curl -s ${BASE_URL}/testing/coverage
   ```
   Extract: overall coverage percentage, per-file coverage, uncovered lines.

4. **Generate the structured report.** Format the results as a table:

   ```
   ## Test Results
   | Metric       | Value   |
   |-------------|---------|
   | Total       | N       |
   | Passed      | N       |
   | Failed      | N       |
   | Skipped     | N       |
   | Duration    | X.Xs    |
   | Coverage    | XX.X%   |

   ## Failed Tests
   | Test Name          | File            | Error                    |
   |-------------------|-----------------|--------------------------|
   | test_something    | test_foo.py:42  | AssertionError: expected |

   ## Coverage Gaps
   | File              | Coverage | Uncovered Lines           |
   |------------------|----------|---------------------------|
   | module.py        | 65%      | 42-48, 72, 95-100         |
   ```

5. **Summarize failures for code-writer.** For each failed test, provide:
   - The test name and file location
   - What the test expected vs what it got
   - The likely root cause (which source file and function is broken)
   - Suggested fix direction (not the fix itself — code-writer handles that)

6. **Report verdict.** Conclude with one of:
   - **ALL PASS** — all tests passed, coverage meets threshold
   - **FAILURES** — N tests failed, needs code-writer attention
   - **COVERAGE LOW** — tests pass but coverage is below threshold (XX% < threshold%)

## Test Quality Metrics

Beyond pass/fail, assess the quality of the test suite itself:

| Metric | What to Check | Red Flag |
|--------|--------------|----------|
| **Test execution time** | Total duration and slowest individual tests | Any single test > 10s likely has I/O waits or missing mocks |
| **Test isolation** | Do tests pass when run individually AND in suite? | Tests that pass alone but fail in suite have shared state leaks |
| **Assertion density** | Does each test have meaningful assertions? | Tests with zero or only `assertNotNull` are not testing behavior |
| **Mock usage** | Are mocks verifying interactions, not just stubbing? | Over-mocking tests implementation details, not behavior |
| **Test naming** | Do test names describe the scenario and expected outcome? | `test1`, `testMethod` tell you nothing when they fail |

## Flaky Test Detection

Flag a test as potentially flaky if:
- It failed this run but passed in the previous 3 CI runs (or vice versa)
- The error involves timing (`sleep`, `timeout`, `eventually`), ordering, or random data
- The error message references external services, file system, or network
- The same test appears in both "passed" and "failed" in parallel test runs

When flaky tests are detected, report them separately — they should NOT block the pipeline but MUST be tracked for cleanup.

## Coverage Analysis Depth

Do not just report the coverage number. Analyze WHERE coverage is missing:

| Coverage Gap Type | Priority | Action |
|-------------------|----------|--------|
| **Error handling paths** (catch blocks, error returns) | HIGH | These are the paths that matter most in production — add tests |
| **Boundary conditions** (empty input, max values) | HIGH | Often where real bugs hide — add edge case tests |
| **Happy path variants** (different valid inputs) | MEDIUM | Add parameterized tests to cover variants |
| **Configuration branches** (feature flags, env-dependent code) | MEDIUM | Test both branches of each flag |
| **Logging and metrics code** | LOW | Usually safe to leave uncovered unless logging IS the feature |

## Definition of Done

- [ ] Test report is generated with pass/fail/skip counts and coverage percentage
- [ ] Every failure has a root cause classification (code bug, flaky, infra, pre-existing)
- [ ] Coverage gaps are identified with priority (not just "coverage is 78%")
- [ ] Flaky tests are flagged separately from real failures
- [ ] Actionable next steps are provided for each failure — code-writer should not have to re-investigate
