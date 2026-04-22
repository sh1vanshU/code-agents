---
name: read-ticket
description: Fetch ticket, extract acceptance criteria, linked pages, requirements
---

## Workflow

1. **Fetch the Jira ticket** to get full details.
   ```bash
   curl -sS "BASE_URL/jira/issue/TICKET_KEY"
   ```

2. **Parse the response.** Extract:
   - **Summary** — what the ticket is about
   - **Status** — current state (To Do, In Progress, Done, etc.)
   - **Assignee** — who is responsible
   - **Priority** — urgency level
   - **Labels** — categorization tags
   - **Acceptance Criteria** — extracted from the description
   - **Subtasks** — child tickets with their statuses

3. **Check for linked Confluence pages.** If the description references wiki pages or the user asks for requirements, search Confluence:
   ```bash
   curl -sS -X POST BASE_URL/jira/confluence/search \
     -H "Content-Type: application/json" \
     -d '{"cql": "space = '\''SPACE_KEY'\'' and title ~ '\''relevant title'\''"}'
   ```

4. **Present a structured summary** to the user:
   - Ticket key and summary
   - Current status and assignee
   - Acceptance criteria (numbered list)
   - Subtask progress (completed / total)
   - Linked documentation if found

5. **If acceptance criteria are missing**, note this and suggest the user add them to the ticket.
