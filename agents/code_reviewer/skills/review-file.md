---
name: review-file
description: Deep single-file review — naming, error handling, null safety, resource leaks, thread safety, complexity, and test existence check
---

## Workflow

1. **Read the entire file.** Get the full source:
   ```bash
   curl -sS "${BASE_URL}/git/file?path=<file_path>"
   ```
   Understand the file's purpose, its public API, and how it fits into the codebase.

2. **Check naming conventions and code style.**
   - Variable, function, class names follow project conventions (snake_case for Python, camelCase for JS/TS)
   - Names are descriptive — no single-letter variables outside loop indices
   - Constants are uppercase
   - No misleading names (e.g., `isReady` that returns a string)
   - No abbreviations that obscure meaning
   - Consistent naming within the file (don't mix `user_id` and `userId`)

3. **Check error handling.**
   - Every I/O operation (file, network, database) has error handling
   - No bare `except:` or `catch (Exception e)` that swallows all errors
   - Error messages are actionable — include what failed, why, and what to do
   - Errors propagate correctly — no silent failures that corrupt state
   - Retry logic exists for transient failures where appropriate
   - Resource cleanup happens in finally/defer/with blocks

4. **Check null safety.**
   - Nullable parameters are checked before use
   - Optional return values are handled by callers
   - Dictionary/map lookups use `.get()` or check key existence
   - Chained attribute access is guarded (`a.b.c` when `b` could be None)
   - Default values are provided where sensible
   - API responses and external data are validated before access

5. **Check for resource leaks.**
   - Files opened with context managers (`with open()`, `try-with-resources`)
   - Database connections returned to pool after use
   - HTTP clients/sessions properly closed
   - Temporary files cleaned up
   - Event listeners/subscriptions cleaned up on teardown
   - Timers and scheduled tasks cancelled on shutdown

6. **Check thread safety.** (if applicable)
   - Shared mutable state is protected by locks/mutexes
   - No time-of-check-to-time-of-use (TOCTOU) bugs
   - Async code uses proper synchronization primitives
   - Global state is avoided or documented as intentional
   - Collections accessed from multiple threads are thread-safe

7. **Check code complexity.**
   - Methods longer than 30 lines — candidate for extraction
   - Classes with more than 7 public methods — candidate for splitting
   - Nesting deeper than 3 levels — flatten with early returns or extraction
   - Cyclomatic complexity: flag methods with more than 10 branches
   - God classes: single class doing unrelated things
   - Long parameter lists (>4 params) — consider a config object

8. **Check test file existence.**
   - Does a corresponding test file exist? (e.g., `foo.py` -> `test_foo.py`, `Bar.java` -> `BarTest.java`)
   - If yes, does it cover the key public methods?
   - If no, flag as a finding: "No test file found for {file}"
   - Check test quality: meaningful assertions, not just "runs without error"

9. **Output findings and quality score.**
   ```
   ## File Review: <file_path>

   **Quality Score:** X/10

   ### Findings

   #### CRITICAL
   - [file:line] Description + suggested fix

   #### HIGH
   - [file:line] Description + suggested fix

   #### MEDIUM
   - [file:line] Description + suggested fix

   #### LOW
   - [file:line] Description + suggested fix

   ### Metrics
   | Metric | Value | Status |
   |--------|-------|--------|
   | Lines of code | N | OK / TOO LONG |
   | Max method length | N lines | OK / NEEDS SPLIT |
   | Max nesting depth | N | OK / TOO DEEP |
   | Public methods | N | OK / TOO MANY |
   | Test file exists | Yes/No | OK / MISSING |
   | Error handling coverage | Good/Partial/None | ... |
   | Null safety | Good/Partial/None | ... |

   ### Summary
   One paragraph: what the file does well, what needs attention, and priority fix.
   ```
