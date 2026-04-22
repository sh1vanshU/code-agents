---
name: test-fix-loop
description: Run tests, classify failures, fix code bugs via code-writer, STOP for non-code issues — max 5 cycles
---

## Before You Start

- [ ] Establish a baseline: know which tests were passing BEFORE the current changes
- [ ] Identify the scope of recent changes (which files were modified) — this narrows root cause analysis
- [ ] Check if the test suite has known flaky tests — do not waste cycles on them
- [ ] Verify the test environment is consistent (correct branch checked out, dependencies installed)

## Workflow

1. **Run the test suite.** Execute tests via the testing API:
   ```bash
   curl -s -X POST ${BASE_URL}/testing/run \
     -H "Content-Type: application/json" \
     -d '{"branch": null, "test_command": null, "coverage_threshold": 80}'
   ```

2. **Parse failures.** For each failed test, extract:
   - Test name, file, and line number
   - Error type and message
   - Stack trace (first relevant frame)

3. **CLASSIFY each failure.** This is CRITICAL — categorize every failure before acting:

   **Code bug** — Logic error in source code caused by recent changes.
   Signs: AssertionError, wrong return value, missing field, TypeError from code changes.
   Action: [DELEGATE:code-writer] with the failing test, expected vs actual, and root cause analysis.

   **Infrastructure issue** — External service is down or unreachable.
   Signs: ConnectionRefusedError, TimeoutError, database connection failed, socket error.
   Action: **STOP.** Report to user: "Infrastructure issue detected: {service} is unreachable. Please verify {service} is running and retry."

   **Flaky test** — Test passes sometimes, fails other times with no code change.
   Signs: Timing-dependent assertions, random ordering issues, race conditions, "works on retry."
   Action: **STOP.** Flag to user: "Flaky test detected: {test_name}. This test has non-deterministic behavior. Consider adding retry logic or fixing the timing dependency."

   **Environment problem** — Missing configuration, wrong env var, missing dependency.
   Signs: KeyError for env var, ModuleNotFoundError, FileNotFoundError for config, permission denied.
   Action: **STOP.** Report to user: "Environment issue: {missing_item} is not configured. Please set {env_var} or install {dependency} and retry."

   **Pre-existing failure** — Test was already failing before your changes.
   Signs: Failure in code you did not touch, test has been failing in CI, unrelated module.
   Action: **STOP.** Inform user: "Pre-existing failure: {test_name} was failing before this change. This is not caused by the current work."

4. **Fix code bugs only.** For failures classified as code bugs:
   - Delegate to code-writer with: failing test name, expected vs actual output, root cause file and line
   - [DELEGATE:code-writer] Fix the failing test {test_name}: expected {expected} but got {actual}. Root cause is in {file}:{line} — {explanation}.

5. **Re-run tests after fixes.**
   ```bash
   curl -s -X POST ${BASE_URL}/testing/run \
     -H "Content-Type: application/json" \
     -d '{"branch": null, "test_command": null, "coverage_threshold": 80}'
   ```

6. **Repeat steps 2-5 until all code bugs are fixed.** Maximum 5 cycles. Track:
   - Which failures were fixed in each cycle
   - Which failures remain and their classification
   - If the same test fails 3 times in a row, escalate to user

7. **Final report.** Summarize the outcome:
   - Tests fixed: list of tests that were broken and are now passing
   - Non-code issues: list of infrastructure/flaky/environment/pre-existing failures (user must resolve)
   - Cycles used: N of 5
   - Current test status: pass/fail counts

## Root Cause Analysis Framework

For every failure, apply this systematic approach instead of guessing:

**Step 1: Reproduce** — Can you reproduce the failure consistently? If not, it is likely flaky.

**Step 2: Isolate** — Run the failing test in isolation. If it passes alone but fails in the suite, there is a shared state leak between tests.

**Step 3: Trace backward** — From the assertion failure, trace backward through the call stack:
- What value was wrong? (the symptom)
- Where was that value computed? (the location)
- What input or state caused the wrong computation? (the root cause)
- Was it a code change or a test assumption change? (the blame)

**Step 4: Classify the root cause type:**

| Root Cause Type | Example | Fix Strategy |
|----------------|---------|--------------|
| **Logic error** | Wrong conditional, off-by-one, missing null check | Fix the source code |
| **Contract change** | Function signature changed, return type changed | Update callers and tests |
| **State leak** | Test A sets global state that test B depends on | Add proper setup/teardown |
| **Missing mock** | Real service called instead of mock | Add or fix mock configuration |
| **Stale test data** | Test expects old data format | Update test fixtures |
| **Race condition** | Timing-dependent assertion | Add synchronization or use async-aware assertions |

## Regression Prevention

After fixing a bug, ask: "Why did this bug reach the test phase?"

- If the bug was a missing validation → the test was missing. Add a test that SPECIFICALLY targets this case.
- If the bug was a logic error in existing code → the existing tests were insufficient. Strengthen them.
- If the bug was caused by a change in a dependency → add a contract test to catch dependency changes early.
- If the same pattern of bug has appeared before → propose a linter rule, code review checklist item, or shared utility to prevent recurrence.

**Track fix patterns across cycles.** If cycle 2 fix breaks something that cycle 1 fixed, the fixes are conflicting — stop and re-approach the problem holistically instead of patching incrementally.

## Risk Assessment

| Risk | Signs | Mitigation |
|------|-------|------------|
| **Fix oscillation** | Fix A breaks test B, fix B breaks test A | Step back, understand both tests, find a solution that satisfies both |
| **Over-mocking** | Tests pass but production breaks | Ensure at least one integration test exercises the real path |
| **Silent regression** | Tests pass but behavior changed in a way no test covers | Check coverage of the CHANGED lines specifically, not just overall coverage |
| **Cascading failures** | One root cause manifests as 10+ test failures | Fix the root cause first, then re-run — most failures may resolve themselves |

## Definition of Done

- [ ] All code bugs fixed and tests passing
- [ ] Non-code issues clearly documented with owner and action required
- [ ] Root cause identified for every failure (not just "I changed this and it worked")
- [ ] No fix introduced a new failure
- [ ] Regression prevention action taken (new test, stronger assertion, or documented pattern)
