---
name: schema-diff
description: Compare schemas between two databases or schemas — find differences
---

## Workflow

1. **Get tables in schema A:**
   ```bash
   curl -sS "${BASE_URL}/db/tables?database=DB&schema=SCHEMA_A"
   ```

2. **Get tables in schema B:**
   ```bash
   curl -sS "${BASE_URL}/db/tables?database=DB&schema=SCHEMA_B"
   ```

3. **Compare:**
   - Tables in A but not in B (to be created)
   - Tables in B but not in A (to be dropped)
   - Tables in both — compare columns, types, constraints

4. **Generate diff report:**
   - Added tables/columns
   - Removed tables/columns
   - Changed column types or constraints
   - Missing indexes

5. **Optionally generate migration** to align schemas.
