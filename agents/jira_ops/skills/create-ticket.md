---
name: create-ticket
description: Create Jira subtask with implementation details
---

## Workflow

1. **Gather information** from the user:
   - Project key (e.g., TEAM)
   - Summary — clear, concise title
   - Description — implementation details, requirements
   - Issue type — Task, Bug, Story, or Sub-task

2. **Create the issue** via the API.
   ```bash
   curl -sS -X POST BASE_URL/jira/issue \
     -H "Content-Type: application/json" \
     -d '{"project": "PROJECT_KEY", "summary": "Implement retry logic for payment API", "description": "Add exponential backoff retry for failed payment API calls. Max 3 retries with 1s, 2s, 4s delays.", "issue_type": "Task"}'
   ```

3. **Parse the response.** Extract:
   - `key` — the new ticket key (e.g., TEAM-1235)
   - `id` — internal Jira ID

4. **Report the result** to the user:
   - New ticket key and link
   - Summary of what was created
   - Suggest next steps (assign, add to sprint, link to parent)

5. **If creating a subtask for an existing ticket**, note the parent ticket key in the description for reference. The Jira API v3 subtask linking may require additional fields depending on the project configuration.
