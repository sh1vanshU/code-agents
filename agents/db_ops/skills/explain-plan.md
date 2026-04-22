---
name: explain-plan
description: Deep analysis of a query execution plan — identify bottlenecks and suggest optimizations
---

## Workflow

1. **Run EXPLAIN ANALYZE** (with user permission):
   ```bash
   curl -sS -X POST ${BASE_URL}/db/explain -H "Content-Type: application/json" -d '{"database":"DB","query":"SELECT ...","analyze":true}'
   ```

2. **Analyze the plan:**
   - Sequential scans → suggest indexes
   - Nested loops on large tables → suggest join strategy
   - Sort operations → suggest indexes for ORDER BY
   - High cost nodes → identify bottlenecks

3. **Check existing indexes:**
   ```bash
   curl -sS "${BASE_URL}/db/tables/TABLE/indexes?database=DB"
   ```

4. **Recommend optimizations:**
   - Index creation (with exact CREATE INDEX statement)
   - Query rewriting
   - Schema changes

## Definition of Done

- Plan analyzed and bottlenecks identified
- Concrete optimization suggestions provided
