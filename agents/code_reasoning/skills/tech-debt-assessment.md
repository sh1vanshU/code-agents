---
name: tech-debt-assessment
description: Quantify tech debt — TODOs, deprecated APIs, duplication, complexity, missing tests. Output prioritized debt list with effort estimates
---

## Before You Start

- [ ] Clarify scope: entire codebase, a specific module, or a specific category of debt
- [ ] Identify the test suite location and coverage tooling (if any)
- [ ] Check for existing debt tracking (GitHub issues labeled "tech-debt", Jira epic, TODO comments)
- [ ] Understand the team's capacity context — are you prioritizing for a sprint or a quarter?

## Workflow

1. **Scan for explicit debt markers.** Search the codebase for:
   - `TODO` comments — unfinished work acknowledged by the author
   - `FIXME` comments — known bugs or fragile code
   - `HACK` / `WORKAROUND` / `XXX` comments — intentional shortcuts
   - `@deprecated` annotations or `warnings.warn(DeprecationWarning)` calls
   - `# noqa`, `# type: ignore`, `// @ts-ignore`, `# pylint: disable` — suppressed warnings

   For each marker, record: file, line, age (git blame), author, and the comment text.

2. **Identify deprecated API usage.** Look for:
   - Calls to functions/methods marked as deprecated in the codebase
   - Usage of deprecated library APIs (check library changelogs or deprecation warnings)
   - Outdated framework patterns (e.g., old-style class components in React, synchronous DB calls in async frameworks)
   - Pinned dependency versions far behind current releases

3. **Detect code duplication.** Find repeated patterns:
   - Functions or methods with near-identical logic in different files
   - Copy-pasted blocks (same variable names, same structure, minor differences)
   - Repeated boilerplate that could be extracted into a shared utility
   - Similar error handling patterns duplicated across endpoints/handlers

4. **Assess code complexity.** Identify overly complex code:
   - **Long functions**: methods over 50 lines that do too many things
   - **Deep nesting**: more than 3 levels of if/for/try nesting
   - **High parameter count**: functions with 5+ parameters (sign of missing abstraction)
   - **God classes/modules**: files over 500 lines that handle multiple responsibilities
   - **Complex conditionals**: boolean expressions with 3+ conditions, nested ternaries

5. **Evaluate test coverage gaps.** Identify:
   - Modules with zero test files
   - Public functions/endpoints with no corresponding test
   - Critical paths (auth, payment, data mutation) without integration tests
   - Test files that only test the happy path — missing error cases, edge cases, boundary conditions
   - Flaky tests (if test history is available)

6. **Check configuration and infrastructure debt.**
   - Hardcoded values that should be configuration
   - Missing environment variable validation
   - Inconsistent config patterns across modules
   - Missing health checks, readiness probes, or graceful shutdown
   - Logging gaps: missing structured logging, inconsistent log levels

7. **Classify and prioritize.** For each debt item, assign:

   | Field | Values |
   |-------|--------|
   | **Category** | Code quality, Missing tests, Deprecated API, Duplication, Complexity, Config, Documentation |
   | **Severity** | Critical (blocks development), High (causes bugs/incidents), Medium (slows development), Low (cosmetic) |
   | **Effort** | XS (< 1 hour), S (1-4 hours), M (1-2 days), L (3-5 days), XL (1+ weeks) |
   | **Risk if ignored** | What breaks or degrades over time |
   | **Quick win** | Yes/No — high value, low effort |

8. **Output the debt assessment.**
   ```
   ## Tech Debt Assessment: {scope}

   ### Summary
   - Total debt items: {count}
   - Critical: {count} | High: {count} | Medium: {count} | Low: {count}
   - Quick wins: {count} items that can be fixed in < 4 hours each
   - Estimated total effort: {range}

   ### Quick Wins (do these first)
   | # | Item | File | Effort | Impact |
   |---|------|------|--------|--------|

   ### Critical & High Priority
   | # | Item | Category | File:Line | Severity | Effort | Risk if Ignored |
   |---|------|----------|-----------|----------|--------|----------------|

   ### Medium & Low Priority
   | # | Item | Category | File:Line | Severity | Effort | Risk if Ignored |
   |---|------|----------|-----------|----------|--------|----------------|

   ### Debt by Category
   | Category | Count | Total Effort | Recommended Sprint Allocation |
   |----------|-------|-------------|-------------------------------|

   ### Recommendations
   1. {Top recommendation with rationale}
   2. {Second recommendation}
   3. {Third recommendation}
   ```

## Definition of Done

- [ ] All TODO/FIXME/HACK markers inventoried with file, line, and age
- [ ] Deprecated API usage identified with migration path
- [ ] Code duplication detected with specific file pairs
- [ ] Complex methods flagged with reason (length, nesting, parameters)
- [ ] Test coverage gaps identified for critical paths
- [ ] Each debt item classified by category, severity, and effort
- [ ] Quick wins separated for immediate action
- [ ] Prioritized debt list output with effort estimates
- [ ] Top 3 recommendations provided with rationale
