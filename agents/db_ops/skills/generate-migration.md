---
name: generate-migration
description: Generate a database migration script from natural language description
---

## Workflow

1. **Understand current schema:**
   ```bash
   curl -sS "${BASE_URL}/db/tables/TABLE_NAME?database=DB&schema=public"
   ```

2. **Generate migration SQL** based on the user's description:
   - CREATE TABLE, ALTER TABLE, ADD COLUMN, CREATE INDEX, etc.
   - Include both UP and DOWN migrations
   - Use IF NOT EXISTS / IF EXISTS for safety
   - Add comments explaining each change

3. **Review the migration:**
   - Check for data loss risks (DROP COLUMN, ALTER TYPE)
   - Check for locking risks (ADD COLUMN NOT NULL on large table)
   - Suggest safe alternatives (e.g., add nullable column + backfill + add constraint)

4. **Validate by dry-running EXPLAIN:**
   ```bash
   curl -sS -X POST ${BASE_URL}/db/explain -H "Content-Type: application/json" -d '{"database":"DB","query":"ALTER TABLE ..."}'
   ```

5. **Present migration** with warnings and recommendations.

## Definition of Done

- Migration SQL generated (UP + DOWN)
- Safety reviewed (locking, data loss)
- User informed of risks
