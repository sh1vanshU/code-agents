---
name: deadlock-scan
description: Concurrency hazard scanner — race conditions, deadlocks, async issues
tags: [debug, concurrency, deadlock, race-condition, async]
---

# Concurrency Hazard Scanner

## Workflow

1. **Identify concurrency primitives** — Find locks, mutexes, semaphores, channels, async/await, thread pools.
2. **Trace lock ordering** — Map lock acquisition order across code paths; flag inconsistent ordering (deadlock risk).
3. **Check shared state** — Find variables accessed by multiple threads/coroutines without synchronization.
4. **Audit async patterns** — Detect: unawaited coroutines, blocking calls in async context, missing error propagation.
5. **Review atomicity** — Flag check-then-act sequences and compound operations that are not atomic.
6. **Report** — List each hazard with: type, file, line, severity, and recommended fix.

## Notes

- Common deadlock pattern: lock A then B in one path, lock B then A in another.
- For async code, check for event loop blocking (sync I/O in async function).
