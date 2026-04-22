---
name: flaky-test-hunter
description: Detect and fix flaky tests — run multiple times, classify root cause, fix or quarantine
---

## Before You Start

- Get the list of suspected flaky tests (CI history, developer reports, or run the full suite)
- Check if the project has a quarantine mechanism (skip marker, tag, separate suite)
- Have access to CI logs showing intermittent failures
- Know the test framework's repeat/retry options (pytest-repeat, @RepeatedTest, --retry)

## Workflow

1. **Identify flaky test candidates.** Gather from:
   - CI history: tests that fail sometimes but pass on retry
   - Developer reports: "this test is flaky"
   - Run the full suite 5-10 times and diff results:
   ```bash
   # Python
   for i in $(seq 1 10); do poetry run pytest --tb=line -q 2>&1 | tail -5 >> runs.log; done
   # Then diff the failures across runs
   ```

2. **Reproduce the flakiness.** For each candidate:
   - Run the single test 20-50 times in a loop:
   ```bash
   poetry run pytest tests/test_module.py::test_name --count=50 -x
   ```
   - Record pass/fail ratio and any error messages
   - Note if failure rate changes with parallelism (`-n auto`)

3. **Classify the root cause.** Each flaky test falls into one of these categories:

   | Category | Symptoms | Common Fix |
   |----------|----------|------------|
   | **Timing / race condition** | Fails under load, passes alone | Add proper waits, use `asyncio.Event`, increase timeouts |
   | **Shared mutable state** | Fails when run after specific test | Isolate state — fresh fixture per test, reset globals |
   | **External dependency** | Fails on network issues | Mock the dependency, use WireMock/Testcontainers |
   | **Order-dependent** | Fails in full suite, passes alone | Remove hidden coupling, add missing setup/teardown |
   | **Time-dependent** | Fails at midnight, month boundary | Freeze time with `freezegun` or `time_machine` |
   | **Resource leak** | Fails after many tests run | Close connections/files in teardown, use context managers |
   | **Non-deterministic data** | Random seed, UUIDs in assertions | Pin random seeds, assert structure not exact values |

4. **Isolate order-dependent tests:**
   ```bash
   # Run in random order to surface hidden dependencies
   poetry run pytest --randomly-seed=12345 -v
   # Run the failing test alone
   poetry run pytest tests/test_module.py::test_name -v
   # Run with only its suspected dependency
   poetry run pytest tests/test_other.py::test_setup tests/test_module.py::test_name -v
   ```

5. **Fix the flaky test.** Apply the appropriate fix based on root cause:
   - **Timing**: Replace `time.sleep()` with proper synchronization (polling, events, retries with backoff)
   - **Shared state**: Move setup into fixtures with proper scope, use `tmp_path`, reset singletons
   - **External dep**: Replace with mock/stub, add circuit breaker in test
   - **Order-dependent**: Add explicit setup, remove reliance on other tests' side effects
   - **Time-dependent**: Use `freezegun.freeze_time` or equivalent
   - **Non-deterministic**: Seed RNG, assert on structure/type instead of exact values

6. **Quarantine tests you cannot fix immediately:**
   ```python
   @pytest.mark.skip(reason="Flaky: timing issue in async handler — JIRA-1234")
   # or
   @pytest.mark.flaky(reruns=3, reason="External API timeout")
   ```
   - Always add a ticket reference for quarantined tests
   - Never quarantine silently — log the reason

7. **Verify the fix.** Run the previously flaky test 50 times:
   ```bash
   poetry run pytest tests/test_module.py::test_name --count=50
   ```
   - Must pass 50/50. If it fails even once, the fix is incomplete.

8. **Add a regression guard.** If the flakiness was caused by shared state or ordering:
   - Add an assertion at the start of the test that validates preconditions
   - Consider adding `@pytest.mark.order` if execution order matters

## Definition of Done

- [ ] All suspected flaky tests identified and reproduced (with failure rate)
- [ ] Each flaky test classified into a root cause category
- [ ] Fixed tests pass 50/50 consecutive runs
- [ ] Unfixable tests quarantined with skip marker + ticket reference
- [ ] No test relies on execution order or shared mutable state
- [ ] CI reliability improved — no spurious failures in the last 5 runs
