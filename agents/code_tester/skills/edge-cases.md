---
name: edge-cases
description: Edge case suggester — analyze function and suggest untested edge cases
tags: [testing, edge-cases, coverage, quality]
---

# Edge Case Suggester

## Workflow

1. **Analyze function** — Read the function signature, body, types, and existing tests.
2. **Map input space** — Identify parameter types and their boundary values (nulls, empty, zero, max, negative).
3. **Check branches** — Walk every conditional and loop; identify paths not covered by existing tests.
4. **Generate cases** — For each gap, produce a concrete test case with input, expected output, and rationale.
5. **Prioritize** — Rank by likelihood of real-world occurrence and severity of failure.
6. **Output** — Return a list of suggested test cases ready to copy into the test file.

## Notes

- Common misses: empty collections, unicode/special chars, concurrent calls, timezone boundaries.
- Consider error paths: network failure, permission denied, malformed input.
