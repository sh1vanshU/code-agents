---
name: test-fix
description: Test fixer — diagnose failing tests and suggest fixes
tags: [testing, fix, diagnosis, debug]
---

# Test Fixer

## Workflow

1. **Read failure** — Parse the test output: assertion errors, exceptions, timeouts, setup failures.
2. **Locate test** — Open the failing test file and the code under test.
3. **Diagnose** — Determine if the failure is in the test (wrong assertion, stale mock) or the source code (regression).
4. **Check environment** — Rule out flaky causes: test ordering, missing fixtures, env variables, timing.
5. **Suggest fix** — Provide a concrete code change for either the test or the source, with explanation.
6. **Verify** — Recommend the command to re-run just the fixed test for confirmation.

## Notes

- For flaky tests, suggest deterministic alternatives (freeze time, seed randomness, retry isolation).
- If the test is correct and source is wrong, flag it as a regression and suggest the source fix.
