---
name: autonomous-boost
description: Fully autonomous coverage improvement loop — plan, write, verify, iterate until target met
trigger: autonomous, auto boost, boost coverage, auto test, self-driving, autonomous coverage
---

# Autonomous Coverage Boost

You are now in **autonomous mode**. You will plan, write tests, verify, and iterate WITHOUT waiting for user input between steps. Execute the full pipeline end-to-end.

## Inputs

Parse the user's request for:
- **Target scope**: specific module(s), file(s), package, or "all" (default: all under-covered modules)
- **Coverage threshold**: target percentage (default: 80%)
- **Language**: auto-detect from project files (Python/Java/JS/Go)

If the user said something like "boost coverage for backend.py to 90%", extract: scope=`code_agents/backend.py`, threshold=90%.

## Phase 1: Discovery & Baseline

1. **Detect project type:**
   ```bash
   pwd && ls pyproject.toml pom.xml build.gradle package.json go.mod Makefile 2>/dev/null
   ```

2. **Run baseline coverage for the target scope.**

   For Python:
   ```bash
   poetry run pytest tests/ --cov=<source_package> --cov-report=term-missing -q 2>&1 | tail -40
   ```
   For Java:
   ```bash
   mvn clean test jacoco:report -q 2>&1 | tail -20
   ```

3. **Store baseline in scratchpad:**
   ```
   [REMEMBER:baseline_coverage=<overall_pct>]
   [REMEMBER:target_threshold=<threshold>]
   [REMEMBER:target_scope=<scope>]
   [REMEMBER:phase=discovery]
   ```

4. **Parse the coverage output.** Extract per-file/per-class coverage percentages and uncovered line numbers. Identify all files below the threshold.

## Phase 2: Gap Analysis & Planning

5. **For each under-covered file, read the source and identify:**
   - Untested functions/methods (cross-reference with existing test files)
   - Complex branches (if/else, try/except, match/case)
   - Error handling paths
   - Edge cases in business logic

6. **Prioritize by risk and impact:**
   - **P0 (Critical)**: Core business logic, security, payment/auth, data integrity
   - **P1 (High)**: API handlers, backend dispatch, streaming, config loading
   - **P2 (Medium)**: CLI commands, formatters, parsers, validators
   - **P3 (Low)**: Utilities, constants, simple getters/setters

7. **Build execution plan.** Group into batches of 3-5 files. Each batch should be independently verifiable:
   ```
   [REMEMBER:plan_batch_count=<N>]
   [REMEMBER:plan_batch_1=file1.py,file2.py,file3.py]
   [REMEMBER:plan_batch_2=file4.py,file5.py]
   [REMEMBER:phase=planning_done]
   ```

8. **Report the plan to the user** (but DO NOT wait for approval — continue executing):
   ```
   Coverage Boost Plan
   Baseline: <X>%  →  Target: <Y>%
   Batches: <N>
   Batch 1 (P0): file1.py (23%), file2.py (41%)  — est. 8 test methods
   Batch 2 (P1): file3.py (55%), file4.py (60%)  — est. 12 test methods
   ...
   ```

## Phase 3: Autonomous Test Writing Loop

For each batch (1 through N):

9. **Start the batch:**
   ```
   [REMEMBER:current_batch=<batch_num>]
   [REMEMBER:phase=writing_batch_<batch_num>]
   ```

10. **For each file in the batch:**
    a. Read the source file completely
    b. Read any existing test file for it
    c. Identify untested functions/branches
    d. Write new tests or extend existing test file

    **Language-specific delegation:**
    - Python → follow `[SKILL:write-python-tests]` patterns
    - Java → follow `[SKILL:write-unit-tests]` patterns
    - Use the project's existing test conventions (fixtures, naming, structure)

    **Test quality rules:**
    - Tests must catch bugs, not just hit lines — assert meaningful behavior
    - Mock external deps, use real objects for value types
    - Cover happy path + at least 2 edge cases per function
    - Use parametrize/data-driven for multi-input functions
    - Never modify production code to make tests pass (unless fixing a genuine bug)

11. **Run the new tests to verify they pass:**

    For Python:
    ```bash
    poetry run pytest tests/test_<module>.py -x -v
    ```
    For Java (Maven):
    ```bash
    mvn test -Dtest=<TestClass> -pl <module> -q
    ```
    For Java (Gradle):
    ```bash
    ./gradlew test --tests <TestClass> -q
    ```

    If tests fail → read error → fix → re-run. Iterate up to 3 times per file. If still failing after 3 attempts, skip the file and note it:
    ```
    [REMEMBER:skipped_<filename>=<reason>]
    ```

12. **After batch completes, run coverage check:**

    For Python:
    ```bash
    poetry run pytest tests/ --cov=<source_package> --cov-report=term-missing -q 2>&1 | tail -40
    ```
    For Java (Maven):
    ```bash
    mvn clean test jacoco:report -q 2>&1 | tail -20
    ```
    For Java (Gradle):
    ```bash
    ./gradlew test jacocoTestReport -q 2>&1 | tail -20
    ```
    ```
    [REMEMBER:coverage_after_batch_<N>=<pct>]
    [REMEMBER:phase=verified_batch_<N>]
    ```

13. **Check if threshold is met.** If overall coverage >= target:
    - Skip remaining batches
    - Jump to Phase 4 (commit)
    ```
    [REMEMBER:threshold_met=true]
    [REMEMBER:final_coverage=<pct>]
    ```

14. **If threshold not met, continue to next batch.** Loop back to step 9.

## Phase 4: Git Commit & Report

15. **Create branch and commit:**

    For Python:
    ```bash
    git checkout -b coverage/auto-boost-$(date +%Y%m%d)
    git add tests/test_*.py tests/conftest.py
    git status
    git commit -m "test: auto-coverage boost — <N> test files, <baseline>% → <final>%"
    ```
    For Java:
    ```bash
    git checkout -b coverage/auto-boost-$(date +%Y%m%d)
    git add src/test/java/
    git status
    git commit -m "test: auto-coverage boost — <N> test classes, <baseline>% → <final>%"
    ```
    ```
    [REMEMBER:phase=committed]
    [REMEMBER:branch=coverage/auto-boost-YYYYMMDD]
    ```

16. **Final summary report:**
    ```
    ══════════════════════════════════════════
    AUTONOMOUS COVERAGE BOOST — COMPLETE
    ══════════════════════════════════════════
    Branch:     coverage/auto-boost-YYYYMMDD
    Baseline:   <X>%
    Final:      <Y>%  (Δ +<diff>%)
    Threshold:  <T>%  — <MET/NOT MET>

    Files tested:
      ✓ module_a.py     23% → 85%  (+62%)
      ✓ module_b.py     41% → 92%  (+51%)
      ✗ module_c.py     SKIPPED — <reason>

    New test files:   <count>
    New test methods: <count>
    Batches run:      <N> of <total>

    Next steps:
      git push -u origin coverage/auto-boost-YYYYMMDD
    ══════════════════════════════════════════
    ```

## Error Recovery

- **Tests won't pass after 3 retries**: Skip the file, log reason, continue with next file
- **Coverage command fails**: Try alternative (`python -m pytest --cov` or `coverage run`)
- **Import errors in tests**: Read the source file again, fix imports, retry
- **Module not found**: Check the package structure, adjust import paths
- **Already on a coverage branch**: Reuse it, don't create a new one

## Self-Driving Rules

- **DO NOT stop to ask the user** between phases. Execute the full pipeline.
- **DO report progress** at the end of each batch (one-line summary).
- **DO use [REMEMBER:] tags** to track state so you can recover if context is lost.
- **DO iterate** — if first pass doesn't hit threshold, write more tests.
- **DO stop** if you've completed all batches and still can't hit threshold — report what's left.
- **MAX iterations**: 5 batches or 30 test files, whichever comes first. Beyond that, report remaining gaps for manual work.
