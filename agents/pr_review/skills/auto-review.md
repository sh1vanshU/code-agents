---
name: auto-review
description: Automatically review a PR — fetch diff, analyze, post findings
---

## Before Starting

Check [Session Memory] for pr_number.

## Workflow

1. **Get PR details:**
   ```bash
   curl -sS "${BASE_URL}/pr-review/pulls/${pr_number}"
   ```
   → Emit: `[REMEMBER:pr_number=N]` `[REMEMBER:pr_title=...]` `[REMEMBER:pr_author=...]`

2. **Get changed files:**
   ```bash
   curl -sS "${BASE_URL}/pr-review/pulls/${pr_number}/files"
   ```
   → Emit: `[REMEMBER:files_changed=N]` `[REMEMBER:additions=N]` `[REMEMBER:deletions=N]`

3. **Get the diff:**
   ```bash
   curl -sS "${BASE_URL}/pr-review/pulls/${pr_number}/diff"
   ```

4. **Analyze the diff** against review standards:
   - 🔴 **Critical:** Security issues, data loss, breaking changes
   - 🟡 **Warning:** Performance issues, error handling gaps, missing validation
   - 🔵 **Suggestion:** Style improvements, refactoring opportunities, documentation

5. **Check PR checks status:**
   ```bash
   curl -sS "${BASE_URL}/pr-review/pulls/${pr_number}/checks"
   ```

6. **Post review with inline comments:**
   ```bash
   curl -sS -X POST ${BASE_URL}/pr-review/pulls/${pr_number}/review -H "Content-Type: application/json" -d '{"event":"COMMENT","body":"## Code Review Summary\n\n...","comments":[{"path":"file.py","line":42,"body":"🔴 ..."}]}'
   ```

7. **Summarize to user:** Findings count by severity, overall recommendation (approve/request changes).
   → Emit: `[REMEMBER:review_status=approved/changes_requested]`

## Definition of Done

- All files reviewed
- Inline comments posted for issues found
- Summary review posted with recommendation
