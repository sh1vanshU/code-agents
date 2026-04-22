---
name: test-quality-audit
description: Audit existing tests — assertion quality, naming, isolation, mock usage, speed, coverage gaps. Score A/B/C/D
---

## Before You Start

- Identify the test directories and frameworks used
- Have access to run the test suite and collect coverage
- Know the project's core business logic modules (these need the highest quality tests)

## Workflow

1. **Collect baseline metrics.** Run the full suite and capture:
   ```bash
   poetry run pytest --tb=short -q --cov=code_agents --cov-report=term-missing
   ```
   - Total test count
   - Pass/fail/skip/error counts
   - Line and branch coverage percentages
   - Suite execution time

2. **Audit assertion quality.** Read each test file and flag:

   | Anti-pattern | Example | Fix |
   |-------------|---------|-----|
   | No assertion | `def test_foo(): foo()` | Add `assert result == expected` |
   | Trivial assertion | `assert result is not None` | Assert the actual value or structure |
   | Boolean-only | `assert result == True` | Assert the condition that makes it true |
   | Too many asserts | 15 asserts in one test | Split into focused tests |
   | Assert on repr/str | `assert str(obj) == "..."` | Assert on object properties |
   | Swallowed exception | `try: ... except: pass` | Use `pytest.raises` with match |

   Score:
   - **A**: 90%+ tests have meaningful, specific assertions
   - **B**: 70-89% have meaningful assertions
   - **C**: 50-69% have meaningful assertions
   - **D**: Below 50%

3. **Audit test naming conventions.** Check that names follow `test_<what>_<condition>_<expected>`:
   - Bad: `test_1`, `test_foo`, `test_it_works`
   - Good: `test_parse_config_empty_file_returns_defaults`
   - Check for consistency across the codebase

   Score:
   - **A**: 90%+ follow a consistent descriptive pattern
   - **B**: 70-89% are descriptive
   - **C**: 50-69% are descriptive
   - **D**: Below 50% or no consistent pattern

4. **Audit test isolation.** Check for:
   - Tests that modify global state (module-level variables, singletons, environment)
   - Tests that share mutable fixtures without proper reset
   - Tests that depend on execution order
   - Tests that write to real filesystem without cleanup
   - Tests that use real network calls

   Score:
   - **A**: All tests are fully isolated, proper fixture scoping
   - **B**: Minor isolation issues, mostly fixtures
   - **C**: Several tests share state or have order dependencies
   - **D**: Widespread shared state, tests fail in random order

5. **Audit mock usage.** Check for:

   | Anti-pattern | Problem | Fix |
   |-------------|---------|-----|
   | Mocking the thing under test | Tests nothing | Mock dependencies only |
   | Deep mock chains | `mock.a.b.c.d.return_value` — brittle | Simplify or use fakes |
   | Mock overuse | Every dependency mocked — tests pass but code is broken | Use integration tests for critical paths |
   | No mock verification | Mock set up but never checked | Add `assert_called_with` or remove mock |
   | Patching wrong target | `@patch('module.Class')` vs `@patch('consumer.Class')` | Patch where it's looked up |

   Score:
   - **A**: Mocks used judiciously, only for external deps, all verified
   - **B**: Mostly correct mock usage, minor issues
   - **C**: Significant mock overuse or incorrect patching
   - **D**: Tests mock the code under test, or mocks are decorative

6. **Audit test speed.** Measure execution time:
   ```bash
   poetry run pytest --durations=20
   ```
   - Flag tests taking > 1 second (likely integration tests in unit suite)
   - Check for unnecessary `time.sleep()` calls
   - Check for missing `@pytest.mark.slow` markers

   Score:
   - **A**: Unit suite < 30s, no test > 1s, slow tests marked
   - **B**: Unit suite < 60s, few tests > 1s
   - **C**: Unit suite < 120s, many slow tests
   - **D**: Unit suite > 120s or individual tests > 5s

7. **Audit coverage gaps.** Identify untested critical paths:
   - Business logic with 0% coverage
   - Error handling paths (catch blocks, fallback logic)
   - Edge cases in data validation
   - Configuration parsing and defaults
   - API endpoint handlers

   Score:
   - **A**: 80%+ line coverage, critical paths fully covered
   - **B**: 60-79% coverage, most critical paths covered
   - **C**: 40-59% coverage, significant gaps in critical paths
   - **D**: Below 40% or critical business logic untested

8. **Generate the audit report.** Produce a structured summary:

   ```
   ## Test Quality Audit Report

   | Dimension             | Score | Details |
   |-----------------------|-------|---------|
   | Assertion Quality     | B     | 12/80 tests have weak assertions |
   | Naming Conventions    | A     | Consistent test_what_condition_expected |
   | Test Isolation        | C     | 5 tests share database state |
   | Mock Usage            | B     | 3 tests mock the SUT |
   | Test Speed            | A     | Suite runs in 18s |
   | Coverage Gaps         | C     | PaymentService 32% coverage |
   | **Overall**           | **B** | |

   ## Top Priority Fixes
   1. Fix 5 tests sharing database state (isolation)
   2. Add tests for PaymentService error paths (coverage)
   3. Replace weak assertions in test_auth.py (quality)
   ```

   Overall score = lowest individual score (weakest link).

## Definition of Done

- [ ] All 6 dimensions audited with specific findings
- [ ] Each dimension scored A/B/C/D with evidence
- [ ] Overall score calculated (weakest link)
- [ ] Top 5 priority fixes listed with specific file/test references
- [ ] Report delivered in structured markdown table format
- [ ] Quick wins (< 30 min fixes) identified and flagged
