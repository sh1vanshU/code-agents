---
name: auto-coverage
description: One-button autonomous test coverage improvement — detects scope, plans, writes tests, verifies, commits
trigger: coverage boost, improve coverage, add tests, increase coverage, boost tests, auto coverage
---

# Auto-Coverage Boost

**Autonomous pipeline** — plan, write, verify, iterate, commit. No user intervention needed between steps.

## Quick Start

When the user triggers this skill, extract parameters from their message:

| Parameter | How to detect | Default |
|-----------|--------------|---------|
| **Scope** | File/module/package names mentioned | All files below threshold |
| **Threshold** | Number + "%" mentioned | 80% |
| **Language** | Auto-detect from project files | — |

Examples:
- "boost coverage" → scope=all, threshold=80%
- "boost coverage for backend.py to 90%" → scope=backend.py, threshold=90%
- "increase test coverage for the cli module" → scope=code_agents/cli/, threshold=80%

## Execution

Delegate to `[SKILL:autonomous-boost]` with the extracted parameters. The autonomous-boost skill handles the full self-driving loop:

1. **Discovery** — detect project, run baseline, store in scratchpad
2. **Planning** — gap analysis, prioritize by risk, batch files
3. **Writing** — write tests per batch, verify each, track progress
4. **Commit** — branch, stage, commit, summary report

## Language-Specific Test Writing

The autonomous loop delegates test writing based on detected language:
- **Python** → `[SKILL:write-python-tests]` (pytest + unittest.mock)
- **Java** → `[SKILL:write-unit-tests]` (JUnit 5 + Mockito + AssertJ)
- **Java Integration** → `[SKILL:write-integration-tests]` (Spring + Testcontainers)
- **Java E2E** → `[SKILL:write-e2e-tests]` (Full request flow)

## Progress Tracking

The agent uses `[REMEMBER:]` scratchpad tags to track state across turns:
- `baseline_coverage`, `target_threshold`, `target_scope` — initial params
- `current_batch`, `phase` — execution progress
- `coverage_after_batch_N` — coverage after each batch
- `skipped_<file>` — files that couldn't be tested (with reason)
- `final_coverage`, `threshold_met` — completion state

This allows recovery if the agentic loop context resets mid-execution.

## Cross-Agent Delegation

- `[DELEGATE:code-tester]` — for complex test scenarios needing specialist review
- `[DELEGATE:code-writer]` — if source code needs testability improvements (dependency injection, extracting pure functions)
- `[DELEGATE:code-reviewer]` — optional post-boost review of test quality

## Git Workflow

- Branch: `coverage/auto-boost-YYYYMMDD`
- Stage: `git add tests/test_*.py tests/conftest.py`
- Commit: `git commit -m "test: auto-coverage boost — N test files, X% → Y%"`
- **DO NOT push** — user will push when ready
