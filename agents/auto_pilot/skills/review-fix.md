---
name: review-fix
description: Code review, apply fixes, run tests, and verify — automated review-fix cycle
---

## Workflow

1. **Get the current diff:**
   ```bash
   curl -sS "${BASE_URL}/git/diff?base=main&head=HEAD"
   ```

2. **Send to code-reviewer:**
   [DELEGATE:code-reviewer] -- review diff for bugs, security issues, quality.
   Parse findings by severity.

3. **If issues found, send to code-writer:**
   [DELEGATE:code-writer] -- fix the issues identified in review.

4. **Re-run code-reviewer** to verify fixes addressed all issues.

5. **Run tests:**
   ```bash
   curl -sS -X POST ${BASE_URL}/testing/run -H "Content-Type: application/json" -d '{"branch": "HEAD"}'
   ```

6. **Report the full cycle:**
   - Issues found (count by severity)
   - Fixes applied
   - Verification result (all resolved or remaining)
   - Test results (pass/fail count)
