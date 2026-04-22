---
name: migration-verify
description: Verify Flyway/Liquibase migrations — snapshot before, compare after, verify columns/indexes, rollback plan
---

## Before You Start

- [ ] Identify the migration tool in use (Flyway or Liquibase) and locate migration files
- [ ] Confirm the data source ID on Redash for the target database
- [ ] Determine which migration version is being verified (e.g., V20240115_1__add_status_column)
- [ ] Take a pre-migration schema snapshot if migration has not run yet
- [ ] Confirm READ-ONLY access — verification uses SELECT and DESCRIBE only

## Workflow

1. **Identify migration files.** Scan the repo for:
   - Flyway: `src/main/resources/db/migration/V*.sql`
   - Liquibase: `src/main/resources/db/changelog/*.xml` or `*.yaml`

   Parse the target migration to understand expected changes:
   - New tables (CREATE TABLE)
   - New columns (ALTER TABLE ADD COLUMN)
   - New indexes (CREATE INDEX)
   - Data migrations (INSERT/UPDATE within migration)
   - Dropped objects (DROP TABLE/COLUMN/INDEX)

2. **Capture pre-migration snapshot.** Before migration runs (or from known baseline):
   ```bash
   curl -s -X POST ${CODE_AGENTS_PUBLIC_BASE_URL}/redash/run-query \
     -H "Content-Type: application/json" \
     -d '{"data_source_id": <id>, "query": "DESCRIBE <table_name>", "max_age": 0}'
   ```

   For each affected table, capture:
   - Column definitions (name, type, nullable, default)
   - Indexes (SHOW INDEX FROM table)
   - Row count (SELECT COUNT(*))
   - Schema version (Flyway: `SELECT * FROM flyway_schema_history ORDER BY installed_rank DESC LIMIT 5`)

3. **Capture post-migration snapshot.** After migration runs:
   - Same queries as step 2 for all affected tables
   - Verify schema version advanced:
     ```sql
     SELECT version, description, success, installed_on
     FROM flyway_schema_history
     ORDER BY installed_rank DESC LIMIT 5;
     ```

4. **Compare snapshots.** Verify each expected change:

   | Expected Change | Verification Query | Pass Criteria |
   |----------------|-------------------|---------------|
   | New table created | `SHOW TABLES LIKE 'new_table'` | Table exists |
   | New column added | `DESCRIBE table_name` | Column present with correct type |
   | Index created | `SHOW INDEX FROM table WHERE Key_name = 'idx_name'` | Index exists |
   | Data migrated | `SELECT COUNT(*) FROM new_table` | Row count > 0 |
   | Column dropped | `DESCRIBE table_name` | Column absent |
   | Default value set | `DESCRIBE table_name` | Default matches expected |

5. **Verify data migration completeness.** If the migration moved data:
   ```sql
   -- Check source still has data (should it?)
   SELECT COUNT(*) FROM old_table;

   -- Check target has expected rows
   SELECT COUNT(*) FROM new_table;

   -- Spot-check data integrity
   SELECT o.id, o.value, n.value
   FROM old_table o JOIN new_table n ON o.id = n.id
   LIMIT 10;
   ```

6. **Check for side effects.** Look for unintended changes:
   - Other tables modified unexpectedly
   - Constraints broken by the migration
   - Auto-increment values reset
   - Character set or collation changes

7. **Document rollback plan.** For each migration change:
   ```
   ## Rollback Plan for V20240115_1__add_status_column

   ### Steps to rollback:
   1. ALTER TABLE payments DROP COLUMN status;
   2. DROP INDEX idx_payment_status ON payments;
   3. DELETE FROM flyway_schema_history WHERE version = '20240115.1';

   ### Risk assessment:
   - Column drop is safe if no code reads it yet
   - Index drop has no data impact
   - If data was migrated INTO the column, it will be lost

   ### Pre-requisites for rollback:
   - Rollback the application code FIRST (remove code reading the new column)
   - Verify no downstream consumers depend on the new column
   ```

8. **Generate verification report.**
   ```
   ## Migration Verification Report
   Migration: V20240115_1__add_status_column
   Database: acqcore0 | Environment: staging

   ### Schema Changes: 3 expected, 3 verified
   | # | Change | Expected | Actual | Verdict |
   |---|--------|----------|--------|---------|
   | 1 | Add column payments.status | VARCHAR(20) NOT NULL DEFAULT 'PENDING' | VARCHAR(20) NOT NULL DEFAULT 'PENDING' | PASS |
   | 2 | Create index idx_payment_status | (status) | (status) | PASS |
   | 3 | Backfill status from legacy_status | 5M rows | 5,000,127 rows | PASS |

   ### Rollback plan: documented above
   ### Side effects: none detected
   ```

## Definition of Done

- [ ] Migration files identified and parsed for expected changes
- [ ] Pre-migration snapshot captured (or baseline established)
- [ ] Post-migration snapshot captured
- [ ] Each expected change verified with PASS/FAIL
- [ ] Data migration completeness confirmed (if applicable)
- [ ] No unintended side effects detected
- [ ] Rollback plan documented with step-by-step SQL
- [ ] Verification report delivered
