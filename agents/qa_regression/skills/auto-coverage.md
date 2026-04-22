---
name: auto-coverage
description: One-button test coverage improvement pipeline
trigger: coverage boost, improve coverage, add tests, increase coverage
---

# Auto-Coverage Boost

Automated pipeline to improve test coverage:

1. **Scan** existing tests (count files, methods)
2. **Baseline** coverage run (pytest --cov / mvn jacoco:report)
3. **Identify gaps** -- uncovered classes/methods
4. **Prioritize** by risk (payment > utils) and complexity
5. **Write tests** for top-priority gaps
6. **Verify** coverage improved

## Git Workflow
- Create branch: `coverage/auto-boost-YYYYMMDD`
- Stage new test files: `git add tests/test_*.py`
- Commit: `git commit -m "test: auto-coverage boost -- N test files added"`
- DO NOT push -- user will push when ready

## Delegation
- [DELEGATE:code-tester] for writing individual test files
- [DELEGATE:code-writer] if source code needs testability improvements
