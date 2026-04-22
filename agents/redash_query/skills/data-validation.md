---
name: data-validation
description: Post-deploy data checks — row counts, FK integrity, business rules, enum validity, pre/post comparison
---

## Before You Start

- [ ] Confirm the deployment that triggered this validation (version, environment, timestamp)
- [ ] Identify the data source ID on Redash for the target environment
- [ ] Obtain pre-deploy snapshot if available (row counts, checksums from previous run)
- [ ] Identify business-critical tables and rules to validate
- [ ] Confirm READ-ONLY mode — all checks use SELECT queries only

## Workflow

1. **Capture current state.** Run baseline counts on critical tables:
   ```bash
   curl -s -X POST ${CODE_AGENTS_PUBLIC_BASE_URL}/redash/run-query \
     -H "Content-Type: application/json" \
     -d '{"data_source_id": <id>, "query": "SELECT table_name, table_rows FROM information_schema.tables WHERE table_schema = '\''<db>'\'' ORDER BY table_rows DESC LIMIT 50", "max_age": 0}'
   ```

2. **Row count validation.** Compare pre-deploy vs post-deploy counts:
   - No unexpected DROP in row counts (> 5% decrease = WARNING)
   - No unexpected SPIKE in row counts (> 100% increase = WARNING)
   - Zero-row tables that previously had data = CRITICAL

   ```
   | Table | Pre-Deploy | Post-Deploy | Delta | Verdict |
   |-------|-----------|-------------|-------|---------|
   | payments | 5,000,000 | 5,001,234 | +0.02% | PASS |
   | merchants | 12,000 | 0 | -100% | FAIL |
   ```

3. **Foreign key integrity.** Check for orphaned references:
   ```sql
   -- Example: transactions referencing non-existent merchants
   SELECT COUNT(*) as orphaned
   FROM payment_transactions t
   LEFT JOIN merchants m ON t.merchant_id = m.id
   WHERE m.id IS NULL AND t.merchant_id IS NOT NULL
   LIMIT 1;
   ```
   Run this pattern for each critical FK relationship. Any orphaned rows = FAIL.

4. **Business rule validation.** Check domain-specific invariants:
   - **No negative balances:** `SELECT COUNT(*) FROM accounts WHERE balance < 0`
   - **No future dates:** `SELECT COUNT(*) FROM transactions WHERE created_at > NOW()`
   - **Status consistency:** `SELECT COUNT(*) FROM orders WHERE status = 'COMPLETED' AND payment_status = 'PENDING'`
   - **Amount sanity:** `SELECT COUNT(*) FROM payments WHERE amount <= 0 OR amount > 10000000`
   - **Duplicate detection:** `SELECT txn_id, COUNT(*) FROM payments GROUP BY txn_id HAVING COUNT(*) > 1`

   Customize these rules based on the application's domain.

5. **Enum validity.** Verify enum columns contain only valid values:
   ```sql
   SELECT status, COUNT(*) FROM payment_transactions
   GROUP BY status ORDER BY COUNT(*) DESC;
   ```
   Compare against the `@Enumerated` values defined in the codebase. Unknown values = FAIL.

6. **Data freshness.** Verify data is being written post-deploy:
   ```sql
   SELECT MAX(created_at) as latest, TIMESTAMPDIFF(MINUTE, MAX(created_at), NOW()) as minutes_ago
   FROM payment_transactions;
   ```
   If `minutes_ago` > expected threshold = WARNING (system may not be processing).

7. **Generate validation report.** Output results:
   ```
   ## Post-Deploy Data Validation Report
   Deploy: v2.3.1 | Environment: staging | Time: 2024-01-15 14:30 UTC

   ### Summary: 12 checks — 10 PASS, 1 WARN, 1 FAIL

   | # | Check | Table | Result | Details |
   |---|-------|-------|--------|---------|
   | 1 | Row count delta | payments | PASS | +0.02% (within threshold) |
   | 2 | FK integrity | transactions->merchants | PASS | 0 orphaned rows |
   | 3 | No negative balances | accounts | FAIL | 3 rows with balance < 0 |
   | 4 | Enum validity | payments.status | PASS | All values valid |
   | 5 | Data freshness | payments | WARN | Last write 12 min ago |

   ### Action Required
   - FAIL: 3 accounts with negative balance — investigate IDs: [list]
   - WARN: Data freshness lag — verify processing pipeline is running
   ```

## Definition of Done

- [ ] Row count comparison completed (pre vs post deploy)
- [ ] FK integrity validated for all critical relationships
- [ ] Business rules checked with PASS/FAIL per rule
- [ ] Enum validity confirmed against codebase definitions
- [ ] Data freshness verified
- [ ] Structured report generated with actionable findings
- [ ] Any FAIL items highlighted with investigation steps
