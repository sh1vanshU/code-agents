---
name: safe-query
description: Execute a SQL query with safety checks — explain plan, limit, read-only preference
---

## Before Starting

Check [Session Memory] for database, schema, table context.

## Workflow

1. **Validate the query:**
   - Is it a read query (SELECT) or write query (INSERT/UPDATE/DELETE/DDL)?
   - If write → STOP and ask for explicit user confirmation.
   - Ensure LIMIT clause exists (add LIMIT 100 if missing).

2. **Run EXPLAIN first** for any non-trivial query:
   ```bash
   curl -sS -X POST ${BASE_URL}/db/explain -H "Content-Type: application/json" -d '{"database":"DB","query":"SELECT ...","analyze":false}'
   ```
   - Check for sequential scans on large tables
   - Check estimated rows and cost
   - Warn if cost > 10000 or rows > 100000

3. **Execute the query:**
   ```bash
   curl -sS -X POST ${BASE_URL}/db/query -H "Content-Type: application/json" -d '{"database":"DB","query":"SELECT ...","limit":100}'
   ```

4. **Format results:** Present as a readable table. Note row count, execution time.

## Definition of Done

- Query executed safely with results displayed
- Any performance concerns flagged
