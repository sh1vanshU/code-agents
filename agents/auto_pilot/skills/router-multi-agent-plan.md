---
name: multi-agent-plan
description: Plan delegation order for complex requests needing multiple agents — identify dependencies, suggest parallel vs sequential execution
---

## Overview

For complex requests that span multiple agents, create a delegation plan that identifies which agents are needed, in what order, and which steps can run in parallel.

## Workflow

### Step 1 — Decompose the Request

Break the user's request into discrete tasks. For each task, identify:
- What needs to be done
- What input it requires
- What output it produces
- Which agent handles it

### Step 2 — Build the Dependency Graph

Map dependencies between tasks:
- **Sequential:** Task B needs output from Task A (e.g., "review code" before "fix issues")
- **Parallel:** Tasks are independent (e.g., "run tests" and "check ArgoCD" simultaneously)
- **Conditional:** Task C only runs if Task B succeeds (e.g., "deploy" only after "build passes")

### Step 3 — Create the Delegation Plan

Present the plan:

```
MULTI-AGENT DELEGATION PLAN
============================
Goal: {summary}

Phase 1 (parallel):
  [code-reasoning] Analyze the codebase for {requirement}
  [git-ops] Get branch info and recent changes

Phase 2 (sequential, depends on Phase 1):
  [code-writer] Implement changes based on analysis

Phase 3 (parallel):
  [code-tester] Write tests for new code
  [code-reviewer] Review the implementation

Phase 4 (conditional — only if Phase 3 passes):
  [auto-pilot:cicd-pipeline] Build, deploy, verify

Agents involved: 5
Estimated phases: 4
Can parallelize: Phases 1 and 3
```

### Step 4 — Recommend Execution Strategy

Two options:

**Option A — Auto-pilot orchestration (recommended for complex workflows):**
Route the entire request to `auto-pilot` which can delegate to sub-agents and manage the workflow end-to-end.
```
/auto-pilot {original request}
```

**Option B — Manual step-by-step (for more control):**
The user invokes each agent in order, passing results between them.
```
Step 1: /code-reasoning analyze auth module
Step 2: /code-writer implement the fix (paste analysis)
Step 3: /code-reviewer review the changes
```

### Step 5 — Flag Risks

Identify potential issues:
- Steps where failure is likely and what the fallback is
- Steps requiring user confirmation (deploys, destructive operations)
- Long-running steps (builds, test suites) where the user should expect to wait
- Cross-agent data that needs to be passed manually in Option B

## Agent Capability Quick Reference

| Agent | Can Read Code | Can Write Code | Has API Access | Can Deploy |
|-------|:---:|:---:|:---:|:---:|
| code-reasoning | Yes | No | No | No |
| code-writer | Yes | Yes | No | No |
| code-reviewer | Yes | No | No | No |
| code-tester | Yes | Yes | No | No |
| qa-regression | Yes | Yes | Testing API | No |
| git-ops | Yes | No | Git API | No |
| jenkins-cicd | No | No | Jenkins API | Yes |
| argocd-verify | No | No | ArgoCD API | Yes |
| redash-query | No | No | Redash API | No |
| jira-ops | No | No | Jira API | No |
| auto-pilot | Yes | Via delegation | All APIs | Yes |
