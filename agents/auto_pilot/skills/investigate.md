---
name: investigate
description: Research a problem across code, git history, logs, and databases
---

## Workflow

1. **Understand the problem.** Clarify: bug, performance issue, data anomaly, or behavioral question.

2. **Analyze relevant code:**
   [DELEGATE:code-reasoning] -- explain how the affected component works, trace the flow.

3. **Check git history** for recent changes to the affected area:
   ```bash
   curl -sS "${BASE_URL}/git/log?branch=main&limit=20"
   ```
   ```bash
   curl -sS "${BASE_URL}/git/diff?base=main~10&head=main"
   ```
   Look for recent commits modifying affected files.

4. **Query the database** if the problem involves data anomalies:
   [DELEGATE:redash-query] -- check for records matching the anomaly condition.

5. **Check deployment and pod logs** if the problem is runtime:
   [DELEGATE:argocd-verify] with [SKILL:health-check] for pod status.
   [SKILL:_shared:kibana-logs] for application errors.

6. **Correlate findings** across all sources: code changes, data state, runtime behavior.

7. **Report:**
   - Root cause (or most likely hypothesis)
   - Evidence from each source (code, git, data, logs)
   - Recommended fix or next steps
   - Affected scope (users, services, data)
