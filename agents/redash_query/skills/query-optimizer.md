---
name: query-optimizer
description: Run EXPLAIN on queries, identify full scans and missing indexes, suggest optimizations with before/after comparison
---

## Before You Start

- [ ] Have the query to optimize (user-provided or extracted from `@Query` annotations)
- [ ] Confirm the data source ID on Redash
- [ ] Verify the query is SELECT-only (no modifications)
- [ ] Identify the table sizes if possible (large tables benefit most from optimization)

## Workflow

1. **Collect queries to optimize.** Sources:
   - User-provided SQL query
   - `@Query` annotations from the codebase (scan for `@Query(value = "...")`)
   - Slow query log patterns described by the user
   - Queries from Redash saved queries that are known to be slow

   For code scanning, look for:
   - `@Query(value = "...", nativeQuery = true)` — native SQL, highest optimization potential
   - `@Query("SELECT ...")` — JPQL queries, map to SQL first
   - Repository method names like `findByStatusAndCreatedAtBetween` — derive the implicit query

2. **Run EXPLAIN on each query.** Execute via Redash:
   ```bash
   curl -s -X POST ${CODE_AGENTS_PUBLIC_BASE_URL}/redash/run-query \
     -H "Content-Type: application/json" \
     -d '{"data_source_id": <id>, "query": "EXPLAIN <original_query>", "max_age": 0}'
   ```

   For MySQL, also run EXPLAIN FORMAT=JSON for detailed cost analysis:
   ```bash
   curl -s -X POST ${CODE_AGENTS_PUBLIC_BASE_URL}/redash/run-query \
     -H "Content-Type: application/json" \
     -d '{"data_source_id": <id>, "query": "EXPLAIN FORMAT=JSON <original_query>", "max_age": 0}'
   ```

3. **Analyze the EXPLAIN output.** Look for red flags:
   - **Full table scan** — `type: ALL` with large `rows` estimate
   - **Filesort** — `Extra: Using filesort` on large result sets
   - **Temporary table** — `Extra: Using temporary` for GROUP BY/ORDER BY
   - **No index used** — `key: NULL` when an index should be available
   - **Index not optimal** — using a less selective index than available
   - **Dependent subquery** — `select_type: DEPENDENT SUBQUERY` (N+1 pattern)
   - **Large rows examined** — `rows` >> actual result rows

4. **Identify N+1 patterns in code.** Scan for:
   - `@ManyToOne(fetch = FetchType.EAGER)` — implicit joins on every query
   - Repository methods called inside loops
   - `@Query` returning entities with lazy collections accessed later
   - Missing `@BatchSize` or `@Fetch(FetchMode.SUBSELECT)` annotations

5. **Suggest optimizations.** For each issue found:
   - **Missing index** — provide the CREATE INDEX statement
   - **Query rewrite** — rewrite the SQL for better plan (e.g., subquery to JOIN)
   - **N+1 fix** — suggest `JOIN FETCH`, `@EntityGraph`, or `@BatchSize`
   - **Covering index** — suggest composite index that covers all query columns
   - **Partition pruning** — ensure shard-aware queries filter on partition key

6. **Show before/after EXPLAIN.** For each optimization:
   ```
   ### Optimization: Add index on payment_transactions(merchant_id, status)

   **Before EXPLAIN:**
   | type | key  | rows    | Extra          |
   |------|------|---------|----------------|
   | ALL  | NULL | 5000000 | Using filesort |

   **Suggested fix:**
   CREATE INDEX idx_merchant_status ON payment_transactions(merchant_id, status);

   **After EXPLAIN (estimated):**
   | type | key                  | rows | Extra       |
   |------|----------------------|------|-------------|
   | ref  | idx_merchant_status  | 150  | Using index |

   **Impact:** ~33,000x fewer rows scanned
   ```

7. **Prioritize recommendations.** Rank by:
   - Query frequency (how often it runs)
   - Current cost (rows scanned, time)
   - Fix effort (index creation vs query rewrite vs code change)
   - Risk (adding an index is safe; rewriting a query needs testing)

## Definition of Done

- [ ] All target queries analyzed with EXPLAIN
- [ ] Red flags identified and categorized (full scan, filesort, N+1, etc.)
- [ ] Optimization suggestions provided with CREATE INDEX or rewritten SQL
- [ ] Before/after EXPLAIN comparison shown for each suggestion
- [ ] N+1 patterns in code identified (if codebase scanned)
- [ ] Recommendations prioritized by impact and effort
