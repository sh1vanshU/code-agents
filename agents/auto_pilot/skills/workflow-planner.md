---
name: workflow-planner
description: Plan multi-step workflows before executing — analyze request, map agents, get user approval
---

## Workflow

### Step 1 — Analyze the Request

1. Break down the user's request into discrete, actionable steps.
2. Identify dependencies -- which steps must complete before others start.
3. Estimate scope: quick fix (2-3 steps) or full workflow (10+ steps)?

### Step 2 — Map Steps to Agents

| Task Type | Agent / Endpoint |
|-----------|-----------------|
| Read/analyze code | [DELEGATE:code-reasoning] |
| Write/modify code | [DELEGATE:code-writer] |
| Code review | [DELEGATE:code-reviewer] |
| Write/debug tests | [DELEGATE:code-tester] |
| Git operations | [DELEGATE:git-ops] |
| Jenkins build/deploy | [DELEGATE:jenkins-cicd] |
| ArgoCD verify/rollback | [DELEGATE:argocd-verify] |
| Database queries | [DELEGATE:redash-query] |
| Jira/Confluence | [DELEGATE:jira-ops] |
| Full CI/CD pipeline | [SKILL:cicd-pipeline] |
| Regression testing | [DELEGATE:qa-regression] |

### Step 3 — Present the Plan

```
EXECUTION PLAN
==============
Goal: {one-line summary}

Step 1: {action}
  Agent: {agent-name}
  Input: {what this step needs}
  Output: {what this step produces}

Step 2: {action}
  Agent: {agent-name}
  Depends on: Step 1
  ...

Parallel steps: Steps X and Y can run simultaneously.
Risk areas: {steps that might fail or need user input}
```

### Step 4 — Get User Approval

Ask: "Does this plan look correct? Should I adjust any steps?"
Do NOT proceed until user approves.

### Step 5 — Execute

1. Execute steps in order, respecting dependencies.
2. After each step, report result and confirm before proceeding.
3. If a step fails: stop and present options (retry, skip, adjust, abort).
4. For parallel steps, use [DELEGATE:agent-name] concurrently.

### Step 6 — Summary

After completion: what was accomplished, issues encountered, follow-up actions.

## Guidelines

- Always plan before executing multi-step workflows.
- Use direct API endpoints for simple operations (faster than sub-agents).
- Use sub-agents for tasks requiring judgment (review, analysis, writing).
- Keep user informed at every step transition.
- If plan changes mid-execution, update and re-confirm with user.
