---
name: env-diff
description: Environment differ — compare env configs between local, staging, and prod
tags: [debug, environment, config, diff]
---

# Environment Differ

## Workflow

1. **Collect configs** — Gather env files, config maps, or secret references for the target environments.
2. **Normalize** — Strip comments, sort keys alphabetically, unify formats (dotenv, YAML, JSON).
3. **Diff** — Compare key-by-key across environments; categorize as: missing, added, changed value.
4. **Classify sensitivity** — Flag secrets, API keys, and credentials (mask values in output).
5. **Assess impact** — For each difference, note whether it could explain the reported bug or behavior drift.
6. **Report** — Return: side-by-side diff table, high-risk differences, and recommended fixes.

## Notes

- Never print raw secret values — always mask with `****`.
- Check for common pitfalls: trailing whitespace, quote mismatches, case sensitivity.
