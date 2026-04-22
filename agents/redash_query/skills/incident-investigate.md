---
name: incident-investigate
description: Data investigation for incidents — query DB for affected records, trace data flow, identify root cause
---

## Before You Start

- [ ] Obtain the incident context: Kibana error, alert, or user report
- [ ] Identify affected entity IDs (transaction ID, merchant ID, user ID, etc.)
- [ ] Confirm the data source ID on Redash for the target environment
- [ ] Determine the time window of the incident
- [ ] Confirm READ-ONLY access — investigation uses SELECT queries only

## Workflow

1. **Gather incident context.** Collect all available information:
   - Error message from Kibana/logs (use [SKILL:_shared:kibana-logs] if available)
   - Affected entity identifiers (IDs, reference numbers)
   - Time window (first occurrence, last occurrence, frequency)
   - Affected service(s) and environment
   - User-reported symptoms

2. **Query the affected record.** Start with the primary entity:
   ```bash
   curl -s -X POST ${CODE_AGENTS_PUBLIC_BASE_URL}/redash/run-query \
     -H "Content-Type: application/json" \
     -d '{"data_source_id": <id>, "query": "SELECT * FROM <table> WHERE id = <affected_id> LIMIT 1", "max_age": 0}'
   ```

   Check for:
   - **Missing record** — ID referenced in logs but row does not exist
   - **Corrupted data** — NULL in NOT NULL-expected fields, invalid enum, broken JSON
   - **Stale data** — `updated_at` is much older than expected
   - **Unexpected status** — stuck in intermediate state (e.g., PROCESSING for hours)

3. **Trace the data flow.** Follow the record through related tables:
   ```sql
   -- Step 1: Main record
   SELECT * FROM payments WHERE txn_id = '<id>';

   -- Step 2: Related transaction log
   SELECT * FROM transaction_logs WHERE payment_id = <payment_id> ORDER BY created_at;

   -- Step 3: Upstream record
   SELECT * FROM orders WHERE id = <order_id>;

   -- Step 4: Downstream settlement
   SELECT * FROM settlements WHERE payment_id = <payment_id>;
   ```

   Build a timeline:
   ```
   14:30:01 — Order created (status: NEW)
   14:30:02 — Payment initiated (status: PROCESSING)
   14:30:03 — Callback received (status: ???) <-- missing log entry
   14:35:00 — Timeout triggered (status: FAILED)
   ```

4. **Identify the root cause.** Common patterns:

   | Pattern | DB Evidence | Root Cause |
   |---------|------------|------------|
   | Missing record | `SELECT` returns 0 rows | Insert failed silently, race condition |
   | Corrupted data | NULL/invalid values in critical fields | Partial update, missing validation |
   | Stale data | `updated_at` hours/days old | Cron job failed, queue backed up |
   | Stuck status | Intermediate state beyond timeout | Callback not received, deadlock |
   | Duplicate records | Same business key, multiple rows | Missing unique constraint, retry without idempotency |
   | Wrong FK reference | FK points to wrong/deleted parent | Race condition, cascade delete issue |

5. **Assess blast radius.** How many records are affected?
   ```sql
   -- Count all records with the same issue pattern
   SELECT COUNT(*) FROM payments
   WHERE status = 'PROCESSING'
   AND created_at < DATE_SUB(NOW(), INTERVAL 1 HOUR);

   -- Check if issue is ongoing
   SELECT DATE(created_at) as day, COUNT(*) as affected
   FROM payments
   WHERE status = 'PROCESSING'
   AND created_at < DATE_SUB(NOW(), INTERVAL 1 HOUR)
   GROUP BY DATE(created_at)
   ORDER BY day DESC LIMIT 7;
   ```

6. **Cross-reference with logs.** If Kibana is available:
   ```
   [DELEGATE:kibana-logs] Search for errors related to transaction ID <id>
   in service <service_name> between <start_time> and <end_time>
   ```

   Correlate DB state with log entries to build the complete picture.

7. **Generate investigation report.**
   ```
   ## Incident Investigation Report
   Incident: Payments stuck in PROCESSING status
   Time: 2024-01-15 14:30 - 15:00 UTC | Environment: production

   ### Affected Records
   - Total affected: 47 payments
   - Time range: 14:28 - 14:52 UTC
   - Pattern: All stuck in PROCESSING, no callback received

   ### Root Cause
   Payment gateway callback endpoint returned 503 between 14:28 - 14:52
   due to pod restart during deployment v2.3.1. Callbacks were not retried
   by the gateway (retry policy: none).

   ### Data Flow Trace (example: TXN-12345)
   | Time | Event | Table | Status | Notes |
   |------|-------|-------|--------|-------|
   | 14:30:01 | Order created | orders | NEW | OK |
   | 14:30:02 | Payment init | payments | PROCESSING | OK |
   | 14:30:03 | Callback | — | — | MISSING — 503 returned |
   | 14:35:00 | Timeout | payments | PROCESSING | Should be FAILED |

   ### Blast Radius
   - 47 payments totaling $12,450
   - 32 unique merchants affected
   - No settlements impacted (blocked by PROCESSING status)

   ### Recommended Fix
   1. Immediate: Run compensating query to mark 47 records as FAILED
   2. Short-term: Add callback retry mechanism
   3. Long-term: Implement timeout-based auto-recovery job

   ### Data Fix (requires approval)
   ```sql
   -- DO NOT RUN without explicit approval
   UPDATE payments SET status = 'FAILED', updated_at = NOW()
   WHERE status = 'PROCESSING'
   AND created_at BETWEEN '2024-01-15 14:28:00' AND '2024-01-15 14:52:00';
   ```
   ```

## Definition of Done

- [ ] Incident context documented (error, time window, affected IDs)
- [ ] Affected records queried and examined
- [ ] Data flow traced through related tables with timeline
- [ ] Root cause identified with supporting DB evidence
- [ ] Blast radius assessed (count of affected records)
- [ ] Cross-referenced with logs if available
- [ ] Investigation report generated with root cause and fix recommendations
- [ ] Data fix SQL prepared (if needed) — clearly marked as requiring approval
