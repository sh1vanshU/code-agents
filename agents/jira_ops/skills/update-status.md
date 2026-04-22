---
name: update-status
description: Get transitions, transition ticket, add comment with results
---

## Workflow

1. **Fetch available transitions** for the ticket to know valid status changes.
   ```bash
   curl -sS "BASE_URL/jira/issue/TICKET_KEY/transitions"
   ```

2. **Parse the transitions.** Each transition has:
   - `id` — the transition ID to use in the API call
   - `name` — human-readable name (e.g., "Start Progress", "Done")
   - `to` — target status name

3. **Confirm with the user** which transition to apply. Show available options:
   - List each transition with its target status
   - Ask user to confirm or pick one

4. **Execute the transition** with an optional comment.
   ```bash
   curl -sS -X POST BASE_URL/jira/issue/TICKET_KEY/transition \
     -H "Content-Type: application/json" \
     -d '{"transition_id": "TRANSITION_ID", "comment": "Moving to In Progress — implementation started"}'
   ```

5. **Add a detailed comment** if the user wants to document results (separate from the transition comment).
   ```bash
   curl -sS -X POST BASE_URL/jira/issue/TICKET_KEY/comment \
     -H "Content-Type: application/json" \
     -d '{"body": "Implementation complete. PR: #123. All tests passing. Coverage: 92%."}'
   ```

6. **Verify the update** by re-fetching the ticket.
   ```bash
   curl -sS "BASE_URL/jira/issue/TICKET_KEY"
   ```

7. **Report the result:** new status, comment added, and any follow-up actions needed.
