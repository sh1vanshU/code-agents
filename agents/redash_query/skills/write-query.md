---
name: write-query
description: Write SQL from natural language, explain the query, execute it
---

## Workflow

1. **Understand the user's data question.** What do they want to know? Translate from natural language to SQL intent.

2. **Identify the data source and fetch the schema** if not already known.
   ```bash
   curl -sS "${BASE_URL}/redash/data-sources/{id}/schema"
   ```

3. **Write the SQL query.** Follow these rules:
   - SELECT only — never INSERT, UPDATE, DELETE, or DROP
   - Always add `LIMIT 100` (or user-specified limit) to prevent huge result sets
   - Use proper column names from the schema (not guessed)
   - Query a single shard when tables are sharded (e.g., `acq_audit_log_0`)
   - Use parameterized date ranges, not hardcoded dates

4. **Show the query to the user** before executing. Explain:
   - What the query does in plain English
   - Which table(s) and columns it uses
   - Any filters or conditions applied
   - Expected result format

5. **Execute the query.**
   ```bash
   curl -sS -X POST ${BASE_URL}/redash/run-query \
     -H "Content-Type: application/json" \
     -d '{"data_source_id": 1, "query": "SELECT col1, col2 FROM table WHERE condition LIMIT 100", "max_age": 0}'
   ```

6. **Present the results.** Format them as a readable table with column headers. Highlight key findings.

7. **If the query fails**, explain the error and suggest a fix:
   - Unknown column: check the schema for the correct column name
   - Syntax error: fix the SQL
   - Timeout: add more specific WHERE filters or reduce LIMIT

8. **Offer to refine the query** based on the results — add filters, change grouping, or join with another table.
