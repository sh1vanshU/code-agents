---
name: review-checklist
description: Generate a review checklist for a PR based on changed files
---

## Workflow

1. **Get changed files:**
   ```bash
   curl -sS "${BASE_URL}/pr-review/pulls/${pr_number}/files"
   ```

2. **Generate checklist based on file types:**
   - Python files → check types, error handling, tests
   - JS/TS files → check types, XSS, bundle size
   - SQL/migration files → check reversibility, locking, data loss
   - Config files → check secrets, defaults, environment parity
   - Test files → check coverage, mocking, edge cases
   - API routes → check auth, validation, error responses

3. **Check for test coverage:**
   - Modified files should have corresponding test changes
   - New files should have new test files

4. **Report checklist** as a markdown table.
