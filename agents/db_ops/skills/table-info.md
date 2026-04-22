---
name: table-info
description: Get comprehensive information about a database table
---

## Workflow

1. **Get table structure:**
   ```bash
   curl -sS "${BASE_URL}/db/tables/TABLE_NAME?database=DB&schema=public"
   ```

2. **Get indexes:**
   ```bash
   curl -sS "${BASE_URL}/db/tables/TABLE_NAME/indexes?database=DB"
   ```

3. **Get constraints:**
   ```bash
   curl -sS "${BASE_URL}/db/tables/TABLE_NAME/constraints?database=DB"
   ```

4. **Get size:**
   ```bash
   curl -sS "${BASE_URL}/db/tables/TABLE_NAME/size?database=DB"
   ```

5. **Summarize:** Columns, types, nullable, defaults, indexes, constraints, size, row estimate.
   → Emit: `[REMEMBER:table=TABLE]` `[REMEMBER:row_count=N]` `[REMEMBER:indexes=...]`
