---
name: saved-queries
description: List and run saved Redash queries
---

## Workflow

1. **Ask the user what they need.** Do they want to:
   - List available saved queries?
   - Run a specific saved query by ID?
   - Find a query related to a topic?

2. **If the user wants to run a saved query**, get the query ID from the user or help them find it.

3. **Run the saved query.**
   ```bash
   curl -sS -X POST ${BASE_URL}/redash/run-saved-query \
     -H "Content-Type: application/json" \
     -d '{"query_id": 123, "max_age": 0}'
   ```
   Setting `max_age: 0` forces a fresh execution rather than using cached results.

4. **Parse and present the results.** Format as a readable table with:
   - Column headers
   - Data rows
   - Row count
   - Highlight any notable values or patterns

5. **Explain the results** in context. What does the data mean for the user's question?

6. **If the query requires parameters**, ask the user for the parameter values before executing.

7. **If the user wants to modify a saved query**, suggest writing a new query based on the saved one using the `write-query` skill instead. Saved queries should not be modified through this agent.

8. **Offer next steps:** run another saved query, write a custom query for deeper analysis, or explore the schema for more tables.
