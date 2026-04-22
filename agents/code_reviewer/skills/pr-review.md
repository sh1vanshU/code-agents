---
name: pr-review
description: Full pull request review — diff analysis, test coverage, style check
---

## Workflow

1. **Get the diff between the PR branch and the base branch.**
   ```bash
   curl -sS "${BASE_URL}/git/diff?base=main&head=feature-branch"
   ```

2. **Read the full diff carefully.** Understand what changed and why. Group changes by:
   - New files added
   - Existing files modified
   - Files deleted
   - Test files added or changed

3. **Review each changed file for correctness.**
   - Does the logic match the stated intent?
   - Are there bugs, edge cases, or error handling gaps?
   - Does the code follow existing project patterns and conventions?
   - Are there performance concerns (N+1 queries, unbounded loops)?

4. **Check test coverage for the changes.**
   - Are there new tests for new code?
   - Do existing tests still pass with these changes?
   - Are edge cases and error paths tested?
   - Are mocks appropriate (not over-mocking or under-mocking)?

5. **Check for security issues** in the changed code.
   - Input validation at boundaries
   - No secrets or credentials in the diff
   - Proper auth checks on new endpoints

6. **Check code style consistency.**
   - Naming conventions match the project
   - Import order and structure match existing patterns
   - No unnecessary commented-out code
   - No debug print statements or TODOs without tickets

7. **Write the review summary** with this structure:
   ```
   ## PR Review: <title>

   **Overall:** Approve / Request Changes / Comment

   ### Findings
   CRITICAL: ...
   WARNING: ...
   SUGGESTION: ...

   ### What's done well
   - ...

   ### Test coverage
   - New tests: X files
   - Missing tests for: ...
   ```

8. **Give a clear verdict:** approve, request changes, or comment-only. Be specific about what must change before approval.
