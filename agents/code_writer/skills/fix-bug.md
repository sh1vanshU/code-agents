---
name: fix-bug
description: Fix a reported bug — locate, understand, fix, verify
---

## Workflow

1. **Understand the bug report.** Identify:
   - What is the expected behavior?
   - What is the actual behavior?
   - Steps to reproduce (if provided)
   - Error messages or stack traces

2. **Locate the bug.** Search for the relevant code:
   - Start from the error message or stack trace
   - Search for the function or endpoint mentioned in the report
   - Read the code path that produces the incorrect behavior

3. **Understand the root cause.** Trace the logic to find where it diverges from expected behavior. Common causes:
   - Off-by-one errors
   - Missing null checks
   - Incorrect condition logic
   - Wrong variable used
   - Missing error handling
   - Race condition or timing issue

4. **Write a failing test first** (if one does not already exist). The test should reproduce the bug:
   ```python
   def test_bug_description():
       # This test fails before the fix, passes after
       result = function_under_test(bug_triggering_input)
       assert result == expected_correct_output
   ```

5. **Apply the minimal fix.** Change only what is needed to fix the bug:
   - Do not refactor unrelated code
   - Do not add features
   - Preserve the existing code style

6. **Run the new test** to confirm the fix works:
   ```bash
   poetry run pytest tests/test_module.py::test_bug_description -v
   ```

7. **Run the full test suite** to ensure the fix does not break anything:
   ```bash
   poetry run pytest tests/ -v
   ```

8. **Summarize the fix:** what was wrong, what you changed, and confirmation that all tests pass.
