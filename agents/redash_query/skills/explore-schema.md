---
name: explore-schema
description: List data sources, explore table schemas and relationships
---

## Workflow

1. **List all available data sources.**
   ```bash
   curl -sS "${BASE_URL}/redash/data-sources"
   ```
   This returns a list of databases/shards with their IDs, names, and types.

2. **Identify the relevant data source.** Based on the user's question, pick the right database:
   - `acqcore0-24` — core acquiring data shards
   - `Acquiring_0-9` — acquiring business data shards
   - `fee0-19` — fee calculation data shards
   - Ask the user if unclear which data source to use

3. **Fetch the schema for the selected data source.**
   ```bash
   curl -sS "${BASE_URL}/redash/data-sources/{id}/schema"
   ```
   This returns all tables and their columns.

4. **Present the schema clearly.** For each relevant table:
   - Table name
   - Column names and types (if available)
   - Key columns: primary keys, foreign keys, indexes

5. **Identify table relationships.** Look for:
   - Foreign key columns (e.g., `order_id` appearing in multiple tables)
   - Naming patterns that indicate joins (e.g., `merchant_id` in both `orders` and `merchants`)
   - Sharding patterns (e.g., `acq_audit_log_0` through `acq_audit_log_N`)

6. **Note sharding patterns.** Tables are often horizontally sharded:
   - Identify the shard key (usually `merchant_id` or `order_id`)
   - Explain which shard to query for a given lookup
   - Remind the user to query a single shard, not UNION across all

7. **Summarize the schema** relevant to the user's question. Suggest which tables and columns to query for their use case.

8. **Offer to write a query** based on the explored schema.
