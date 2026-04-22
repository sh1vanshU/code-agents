---
name: fix-and-verify
description: Apply a fix for a bug and verify it passes tests
trigger: "[SKILL:fix-and-verify]"
---

# Fix and Verify

## Steps

1. **Plan the fix** — Before editing:
   - State what you'll change and why
   - Identify ALL files that need changes
   - Assess blast radius (what else might break)

2. **Apply minimal fix** — Edit only what's necessary:
   - Fix the root cause, not symptoms
   - Don't refactor surrounding code
   - Keep the diff as small as possible
   - Add a code comment only if the fix is non-obvious

3. **Re-run the failing test** — Verify the fix:
   ```bash
   python -m pytest <test_file>::<test_name> -x -v
   ```

4. **Run related tests** — Check for regressions:
   ```bash
   # Run the full test file
   python -m pytest <test_file> -v

   # Run tests that import the changed module
   python -m pytest tests/ -k "<module_name>" -v
   ```

5. **Report results**:
   - "FIX VERIFIED: [test] passes after [change description]"
   - OR "FIX FAILED: [test] still fails because [reason]" → retry with different approach

6. **Show the diff**:
   ```bash
   git diff
   ```

## Retry Strategy

If the first fix doesn't work:
1. Re-read the error output from the new failure
2. Check if the fix introduced a new issue
3. Try an alternative approach
4. Max 3 attempts before escalating to the user
