---
name: regression-suite
description: Run full regression suite, compare with baseline, identify NEW failures vs pre-existing
---

## Before You Start
- Ensure test framework is configured (Maven/Gradle/pytest)
- Baseline exists at .code-agents/{repo}.regression-baseline.json (create with baseline-manager if not)

## Workflow

1. **Detect test framework:** Check pom.xml (Maven surefire), build.gradle (Gradle), package.json (jest), pyproject.toml (pytest).

2. **Run full test suite:**
   ```bash
   curl -sS -X POST "${CODE_AGENTS_PUBLIC_BASE_URL}/testing/run" -H "Content-Type: application/json" -d '{"branch": "current"}'
   ```

3. **Parse results:** Extract total, passed, failed, skipped, errors. Note execution time.

4. **Load baseline:** Read .code-agents/{repo}.regression-baseline.json (previous known-good results).

5. **Compare with baseline:**
   - NEW failures: tests that passed in baseline but fail now → caused by code change
   - Pre-existing failures: tests that were already failing in baseline → not your fault
   - Fixed tests: tests that failed in baseline but pass now → improvement
   - Flaky tests: tests that fail intermittently (check if retry passes)

6. **Classify NEW failures:**
   - Code bug → [DELEGATE:code-writer] to fix
   - Infrastructure → STOP, inform user
   - Flaky → flag, don't block

7. **Report:**
   ```
   Regression Report:
     Total: 450  Passed: 442  Failed: 8  Skipped: 3
     NEW failures: 3 (caused by your changes)
     Pre-existing: 4 (not your fault)
     Fixed: 1 (improvement!)
     Flaky: 1
   ```

## Definition of Done
- All NEW failures either fixed or acknowledged
- No regression in pass rate vs baseline
- Report generated with clear attribution
