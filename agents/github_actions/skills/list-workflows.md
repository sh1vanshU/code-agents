---
name: list-workflows
description: List all GitHub Actions workflows and their recent status
---

## Workflow

1. **List all workflows:**
   ```bash
   curl -sS "${BASE_URL}/github-actions/workflows"
   ```

2. **For each active workflow, show recent runs:**
   ```bash
   curl -sS "${BASE_URL}/github-actions/workflows/${workflow_id}/runs?per_page=3"
   ```

3. **Summarize:** Show workflow name, last run status, conclusion, branch, and duration.
