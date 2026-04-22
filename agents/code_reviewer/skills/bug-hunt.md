---
name: bug-hunt
description: Identify logic bugs, edge cases, race conditions, null safety issues
---

## Workflow

1. **Read the code under review.** Understand the intended behavior before looking for bugs. Check for comments, docstrings, or specs that describe expected behavior.

2. **Check for null/undefined safety.**
   - Variables used without null checks
   - Optional fields accessed without guards
   - Dictionary/map lookups without default values
   - Array access without bounds checking

3. **Check for logic errors.**
   - Off-by-one errors in loops and ranges
   - Incorrect boolean logic (AND vs OR, negation errors)
   - Wrong comparison operators (< vs <=, == vs ===)
   - Missing break/return in switch/match statements
   - Incorrect variable shadowing

4. **Check for edge cases.**
   - Empty collections (empty list, empty string, empty dict)
   - Zero, negative, and maximum integer values
   - Unicode and special characters in string processing
   - Concurrent access to shared mutable state
   - Timeout and retry logic gaps

5. **Check for race conditions.**
   - Shared state modified without locks
   - Time-of-check-to-time-of-use (TOCTOU) vulnerabilities
   - Async operations with missing await
   - Non-atomic read-modify-write sequences

6. **Check error handling.**
   - Bare except/catch blocks that swallow errors silently
   - Missing error handling on I/O operations
   - Resource leaks (unclosed files, connections, locks)
   - Error messages that hide the root cause

7. **For each bug found, report:**
   - Severity: CRITICAL / WARNING / SUGGESTION
   - File and line number
   - What goes wrong and under what conditions
   - A concrete fix or mitigation

8. **Prioritize findings** by impact: data corruption > crashes > incorrect behavior > edge cases.
