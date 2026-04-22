---
name: write-and-test
description: Write code, run tests, fix failures, repeat until green — max 5 cycles
---

## Before You Start

- [ ] Confirm you have a clear, unambiguous requirement (if vague, ask before coding)
- [ ] Identify the test framework and runner used by the project (pytest, jest, JUnit, etc.)
- [ ] Check if there is a linter, formatter, or pre-commit hook you must satisfy
- [ ] Verify the existing test suite passes BEFORE you touch anything — establish a clean baseline
- [ ] Understand the module boundaries: which package/layer does this change belong to?

## Workflow

1. **Read existing code first.** Before writing anything:
   - Understand the project structure, conventions, and style
   - Identify the files that need changes and their dependencies
   - Find similar patterns in the codebase to follow

2. **Write minimal diffs.** Make only the changes needed:
   - Follow existing code style exactly (indentation, naming, imports)
   - Change only what is necessary — no unrelated modifications
   - Keep functions focused and responsibilities clear

3. **Run tests via the testing API.**
   ```bash
   curl -s -X POST ${BASE_URL}/testing/run \
     -H "Content-Type: application/json" \
     -d '{"branch": null, "test_command": null, "coverage_threshold": 80}'
   ```

4. **Parse the test results.** Examine the response:
   - Count passed, failed, skipped, and errored tests
   - For each failure, extract the test name, file, line number, and error message
   - Identify whether failures are caused by your changes or are pre-existing

5. **Fix failures caused by your changes.** For each failing test:
   - Read the test code to understand what it expects
   - Read the code under test to find the mismatch
   - Apply the minimal fix — either in the source code or the test (if the test expectation is wrong)
   - Do NOT fix pre-existing failures unrelated to your changes

6. **Re-run tests after fixes.**
   ```bash
   curl -s -X POST ${BASE_URL}/testing/run \
     -H "Content-Type: application/json" \
     -d '{"branch": null, "test_command": null, "coverage_threshold": 80}'
   ```

7. **Repeat steps 4-6 until all tests pass.** Maximum 5 cycles. If tests still fail after 5 cycles:
   - Report which tests are still failing and why
   - Show what you tried and what did not work
   - Ask the user for guidance

8. **Verify coverage has not decreased.** Check coverage report:
   ```bash
   curl -s ${BASE_URL}/testing/coverage
   ```
   If coverage dropped, add tests for uncovered lines before declaring done.

## Code Quality Gates

Before declaring any code complete, verify each of these:

| Gate | Check | Why It Matters |
|------|-------|----------------|
| **Naming** | Functions, variables, and classes follow project conventions and are self-documenting | Future maintainers should understand intent without reading implementation |
| **Error handling** | Every external call (I/O, network, DB) has explicit error handling; no bare `except`/`catch` | Unhandled errors become production incidents |
| **Logging** | Key decision points and error paths emit structured log messages with context | Without logs, debugging production issues is guesswork |
| **Input validation** | Public functions validate their inputs; fail fast with clear messages | Garbage-in should produce a clear error, not silent corruption |
| **No hardcoded values** | Magic numbers, URLs, timeouts, and thresholds are constants or config | Hardcoded values create tech debt and deployment surprises |
| **Idempotency** | If the operation can be retried, retrying produces the same result | Retries and replays are reality in distributed systems |
| **Test quality** | Tests assert behavior (not implementation), cover happy + sad + edge paths | Tests that test implementation details break on every refactor |
| **No side-effects in imports** | Module-level code does not perform I/O, network calls, or mutation | Import-time side effects cause mysterious test failures and slow startups |

## Risk Assessment

Before writing code, consider:

- **Concurrency**: Will this code be called from multiple threads/requests simultaneously? If yes, ensure thread safety.
- **Performance**: Does this introduce a loop, query, or I/O call that scales with input size? If yes, consider pagination or batching.
- **Backward compatibility**: Does this change a function signature, API response, or data format that other code depends on? If yes, ensure the old contract still works.
- **Failure modes**: What happens when this code fails? Does the caller get a clear error or a silent hang?

## Definition of Done

- [ ] All tests pass (zero failures introduced)
- [ ] Coverage has not decreased (ideally increased for new code paths)
- [ ] No linter or formatter warnings introduced
- [ ] Error paths are tested, not just happy paths
- [ ] Code is readable without comments explaining "what" — comments only explain "why"
- [ ] No TODO or FIXME left without a linked ticket
- [ ] Changes are minimal — no unrelated reformatting, no bonus refactors
