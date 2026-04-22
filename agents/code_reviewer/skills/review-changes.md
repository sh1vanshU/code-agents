---
name: review-changes
description: Unified diff review — get branch diff vs main, read full files for context, review across 6 categories, output findings with severity and verdict
---

## Before You Start

- [ ] Confirm you are on a feature branch (not main/master)
- [ ] Verify the server is running and /git endpoints are accessible
- [ ] Ask the user if there is a specific focus area or known risk to prioritize
- [ ] Confirm the base branch (default: main) — adjust if the team uses develop or release branches

## Quality Gates

| Gate | Criteria | Fail Action |
|------|----------|-------------|
| Diff available | /git/diff returns non-empty response | Check branch exists, check remote is up to date |
| File readable | Full file content retrieved for every changed file | Warn user, review diff-only for that file |
| No CRITICAL findings | Zero CRITICAL severity issues | Verdict = REQUEST_CHANGES, no exceptions |
| No unhandled HIGH findings | All HIGH issues acknowledged | Verdict = REQUEST_CHANGES unless user explicitly accepts risk |

## Workflow

1. **Get current branch.** Identify what branch is being reviewed:
   ```bash
   curl -sS "${BASE_URL}/git/current-branch"
   ```
   Confirm it is not main/master. If it is, ask the user which branch to review.

2. **Get diff vs main.** Fetch the full unified diff:
   ```bash
   curl -sS "${BASE_URL}/git/diff?base=main&head=HEAD"
   ```
   Parse the diff to extract the list of changed files with change type (added, modified, deleted).

3. **Read full files for context.** For each changed file (not deleted), read the entire file:
   ```bash
   curl -sS "${BASE_URL}/git/file?path=<file_path>"
   ```
   Understanding the full file is essential — diff-only review misses context bugs like:
   - New code duplicating existing logic elsewhere in the file
   - Changes breaking invariants established earlier in the file
   - Missing updates to related methods in the same class

4. **Review each file across 6 categories.** For every changed file, check:

   **a. Bugs and Logic Errors**
   - Off-by-one errors, incorrect boolean logic, wrong operator
   - Missing return statements, unreachable code
   - Race conditions in concurrent code
   - Incorrect assumptions about input data

   **b. Security (OWASP Top 10)**
   - Injection: SQL, command, LDAP, XSS
   - Broken authentication: hardcoded credentials, missing auth checks
   - Sensitive data exposure: secrets in code, PII in logs
   - Broken access control: missing authorization on new endpoints
   - Security misconfiguration: debug mode, verbose errors, permissive CORS

   **c. Performance**
   - N+1 queries: loops that hit the database or API per iteration
   - Memory leaks: unclosed resources, growing caches without eviction
   - Unbounded collections: lists/maps that grow without limit
   - Missing pagination on list endpoints
   - Blocking calls in async code paths

   **d. Error Handling**
   - Bare except/catch blocks that swallow errors
   - Missing error handling on I/O, network, or database calls
   - Error messages that leak internals to users
   - Missing retry logic for transient failures
   - Inconsistent error response format

   **e. Null Safety**
   - Nullable values accessed without checks
   - Optional fields used as required
   - Missing default values for configuration
   - Null propagation through call chains

   **f. Test Coverage**
   - New code paths without corresponding tests
   - Changed logic without updated tests
   - Missing edge case tests (empty input, max values, error paths)
   - Test quality: are tests actually asserting behavior, or just running code?

5. **Format findings.** For each issue found, output:
   ```
   ### [SEVERITY] file:line — Short description

   **Category:** bugs | security | performance | error-handling | null-safety | test-coverage
   **Description:** Explain WHY this is a problem. Reference the specific code.
   **Suggested fix:**
   ```diff
   - problematic code
   + fixed code
   ```
   ```

   Severity definitions:
   - **CRITICAL** — Will cause data loss, security breach, or production outage. Must fix before merge.
   - **HIGH** — Significant bug or risk. Should fix before merge.
   - **MEDIUM** — Code smell or minor bug. Fix recommended but not blocking.
   - **LOW** — Suggestion for improvement. Nice to have.

6. **Verdict.** Based on findings, declare one of:
   - **APPROVE** — No CRITICAL or HIGH issues. Code is ready to merge.
   - **REQUEST_CHANGES** — CRITICAL or HIGH issues found. Must fix before merge.
   - **COMMENT** — No blocking issues, but suggestions provided for improvement.

7. **Summary.** Write the final review output:
   ```
   ## Review: <branch name> vs main

   **Verdict:** APPROVE | REQUEST_CHANGES | COMMENT
   **Quality Score:** X/10
   **Files reviewed:** N
   **Findings:** C critical, H high, M medium, L low

   ### What's Good
   - Highlight 2-3 things done well (patterns followed, good test coverage, clean abstractions)

   ### What Needs Fixing
   - List all CRITICAL and HIGH findings with file:line references

   ### Suggestions
   - List MEDIUM and LOW findings

   ### Quality Score Breakdown
   | Dimension | Score (1-10) | Notes |
   |-----------|-------------|-------|
   | Correctness | X | ... |
   | Security | X | ... |
   | Performance | X | ... |
   | Error handling | X | ... |
   | Test coverage | X | ... |
   | Code clarity | X | ... |
   | **Overall** | **X** | Weighted average |
   ```

## Definition of Done

- [ ] All changed files reviewed (not just the diff — full file context read)
- [ ] All 6 review categories checked for every file
- [ ] Every finding has severity, file:line, description, and suggested fix
- [ ] Verdict is clear and justified
- [ ] Quality score is calculated with breakdown
- [ ] Summary highlights both strengths and issues
