---
name: debug
description: Debug a failing test — trace the root cause and fix it
---

## Workflow

1. **Read the failing test output.** Identify:
   - Which test is failing (file and test name)
   - The assertion error or exception message
   - The full stack trace

2. **Read the failing test code.** Understand what it expects: the setup (Arrange), the operation (Act), and the assertion (Assert).

3. **Read the code under test.** Understand what the function actually does. Compare expected behavior (from the test) with actual behavior (from the code).

4. **Identify the root cause.** Common causes:
   - **Wrong mock setup:** mock not returning the expected value, or not mocking the right target
   - **Stale test data:** test assumes old behavior after a code change
   - **Missing fixture:** test depends on state from another test (test isolation issue)
   - **Race condition:** async test not properly awaited
   - **Environment issue:** missing env var, wrong Python version, missing dependency
   - **Code bug:** the code is actually wrong, and the test correctly caught it

5. **Verify the diagnosis.** Check if:
   - The test worked before (check git log for recent changes to the test or the source)
   - Other related tests also fail (indicates a shared root cause)
   - The test passes in isolation but fails in suite (indicates shared state)

6. **Apply the fix.** Fix the root cause, not the symptom:
   - If the code is wrong: fix the code
   - If the test is wrong: fix the test
   - If the mock is wrong: fix the mock setup
   - If there is a test isolation issue: add proper setup/teardown

7. **Run the fixed test** to confirm it passes:
   ```bash
   poetry run pytest tests/test_<module>.py::<test_name> -v
   ```

8. **Run the full test suite** to make sure the fix did not break anything else.
