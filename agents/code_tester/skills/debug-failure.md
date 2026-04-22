---
name: debug-failure
description: Debug test failures systematically — reproduce, isolate, trace root cause, fix with minimal change, add regression test
---

## Before You Start

- Get the exact test failure: test name, error message, stack trace
- Know whether this failure is new (regression) or pre-existing
- Have access to run the failing test locally
- Check CI logs if the failure only happens in CI

## Workflow

1. **Reproduce the failure.** Run the exact failing test:
   ```bash
   poetry run pytest tests/test_module.py::TestClass::test_name -v --tb=long
   ```
   - If it passes locally but fails in CI: check environment differences (env vars, OS, Python version, installed packages)
   - If it's intermittent: run 20 times to confirm flakiness (see `flaky-test-hunter` skill)
   - Capture the full stack trace and error message

2. **Read the failing test.** Understand what it does:
   - What is the code under test?
   - What inputs does it provide?
   - What does it assert?
   - What mocks/fixtures does it use?
   - When was it last modified? (`git log -5 -- tests/test_module.py`)

3. **Read the code under test.** Understand the implementation:
   - What does the function/method actually do?
   - What are its dependencies?
   - What has changed recently? (`git log -10 -- src/module.py`)
   - Check `git diff main -- src/module.py` for recent changes

4. **Isolate the failure.** Narrow down the cause:

   | Technique | Command | Purpose |
   |-----------|---------|---------|
   | Run alone | `pytest test_name -v` | Rule out order dependency |
   | Run with verbose | `pytest test_name -v --tb=long -s` | See print output |
   | Add breakpoint | `breakpoint()` in test | Step through execution |
   | Reduce test | Comment out asserts one by one | Find which assertion fails |
   | Check fixtures | Print fixture values | Verify setup is correct |
   | Git bisect | `git bisect start HEAD~20 HEAD` | Find the breaking commit |

5. **Classify the root cause.** Determine which category:

   | Category | Indicators | Action |
   |----------|-----------|--------|
   | **Code bug** | Logic error, wrong return value, missing null check | Fix the production code |
   | **Test bug** | Wrong expected value, stale mock, incorrect setup | Fix the test |
   | **Environment** | Missing env var, wrong Python version, missing dependency | Fix the environment/config |
   | **Flaky** | Passes sometimes, timing-dependent | See `flaky-test-hunter` skill |
   | **Intentional change** | Code changed, test not updated | Update the test to match new behavior |

6. **Fix with minimal change.** Apply the smallest fix that resolves the root cause:
   - **Code bug**: Fix the production code, not the test assertion
   - **Test bug**: Fix the test setup, mock, or assertion
   - **Stale test**: Update expected values to match intentional behavior changes
   - Do NOT change the test to make it pass if the code is wrong
   - Do NOT change the code to make the test pass if the test is wrong

7. **Verify the fix:**
   ```bash
   # Run the previously failing test
   poetry run pytest tests/test_module.py::test_name -v
   # Run the entire test file to check for side effects
   poetry run pytest tests/test_module.py -v
   # Run the full suite to catch regressions
   poetry run pytest --tb=short -q
   ```

8. **Add a regression test** if the root cause was a code bug:
   - Write a test that specifically targets the bug that was fixed
   - Name it clearly: `test_<function>_<scenario_that_was_broken>`
   - This test should fail if the fix is reverted
   - Add a comment: `# Regression test for <brief description of bug>`

9. **Document the finding.** Leave a brief note:
   - What failed and why
   - What the root cause was (code bug / test bug / env / flaky)
   - What was changed to fix it
   - Whether a regression test was added

## Definition of Done

- [ ] Failure reproduced locally with full stack trace captured
- [ ] Root cause identified and classified (code bug / test bug / env / flaky)
- [ ] Fix applied with minimal change — only the root cause addressed
- [ ] Previously failing test now passes
- [ ] Full test suite passes (no regressions introduced)
- [ ] Regression test added if root cause was a code bug
- [ ] Finding documented (what broke, why, how it was fixed)
