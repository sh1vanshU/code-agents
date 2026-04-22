---
name: review-summary
description: Aggregate all findings from a review session — group by severity, identify top files and recurring patterns, give merge recommendation
---

## Workflow

1. **Collect all findings from the current review session.** Gather every issue reported across all reviewed files and diffs in this conversation. Include:
   - File path and line number
   - Severity (CRITICAL / HIGH / MEDIUM / LOW)
   - Category (bugs, security, performance, error-handling, null-safety, test-coverage)
   - Short description

2. **Group findings by severity.** Present a consolidated view:
   ```
   ## Review Session Summary

   ### CRITICAL (X findings)
   1. [file:line] Category — Description
   2. ...

   ### HIGH (X findings)
   1. [file:line] Category — Description
   2. ...

   ### MEDIUM (X findings)
   1. [file:line] Category — Description
   2. ...

   ### LOW (X findings)
   1. [file:line] Category — Description
   2. ...
   ```

3. **Identify top files with most issues.** Rank files by total finding count:
   ```
   ### Hotspot Files
   | Rank | File | Critical | High | Medium | Low | Total |
   |------|------|----------|------|--------|-----|-------|
   | 1 | path/to/worst.py | 2 | 3 | 1 | 0 | 6 |
   | 2 | path/to/bad.py | 0 | 2 | 2 | 1 | 5 |
   | ... | | | | | | |
   ```
   These files need the most attention and should be fixed first.

4. **Identify recurring patterns.** Look across all findings for repeated issue types:
   ```
   ### Recurring Patterns
   | Pattern | Occurrences | Files Affected | Example |
   |---------|-------------|----------------|---------|
   | Missing null checks | 8 | 5 files | user.py:42, api.py:88 |
   | Bare except blocks | 4 | 3 files | handler.py:15 |
   | No test coverage | 3 | 3 files | utils.py, config.py, cache.py |
   | N+1 queries | 2 | 2 files | repo.py:30, service.py:55 |
   ```
   Recurring patterns suggest systemic issues — recommend addressing the pattern, not just individual instances.

5. **Calculate overall statistics.**
   ```
   ### Statistics
   | Metric | Value |
   |--------|-------|
   | Files reviewed | N |
   | Total findings | N |
   | Critical | N |
   | High | N |
   | Medium | N |
   | Low | N |
   | Average quality score | X/10 |
   | Files with no issues | N |
   | Files missing tests | N |
   ```

6. **Give a merge recommendation.** Based on all findings:
   - **MERGE** — No CRITICAL or HIGH findings. Code is safe to merge.
   - **FIX FIRST** — HIGH findings exist but are fixable. Estimate effort (e.g., "~30 min of fixes"). List exactly what must change.
   - **REDESIGN NEEDED** — CRITICAL findings or systemic issues that require architectural changes. Explain what needs rethinking and why patching is not enough.

   ```
   ### Recommendation: MERGE | FIX FIRST | REDESIGN NEEDED

   **Rationale:** ...

   **If FIX FIRST, required changes:**
   1. Fix [file:line] — description (CRITICAL)
   2. Fix [file:line] — description (HIGH)
   3. ...

   **Estimated effort:** X minutes / hours

   **If REDESIGN NEEDED, what to rethink:**
   - ...
   ```

7. **Provide actionable next steps.** Tell the user exactly what to do:
   - Which files to fix first (prioritized by severity)
   - Whether to delegate fixes to code-writer: `[DELEGATE:code-writer] Fix these issues: ...`
   - Whether to re-run review after fixes: `[SKILL:review-changes]`
   - Whether tests need updating: `[DELEGATE:code-tester] Add tests for ...`
