---
name: schema-analysis
description: Scan repo for JPA entities, map to DB via Redash, build ER map, identify mismatches and missing indexes
---

## Before You Start

- [ ] Confirm the target data source ID on Redash
- [ ] Identify the repo path containing JPA entities (Java/Spring project)
- [ ] Verify Redash connectivity — `GET /redash/data-sources` should return sources

## Workflow

1. **Scan repo for entity definitions.** Search Java files for:
   - `@Entity` — marks a JPA entity class
   - `@Table(name = "...")` — explicit table name mapping
   - `@Column(name = "...", nullable = ..., length = ...)` — column definitions
   - `@ManyToOne` / `@OneToMany` / `@ManyToMany` / `@OneToOne` — relationships
   - `@JoinColumn(name = "...")` — foreign key columns
   - `@Index(name = "...", columnList = "...")` — declared indexes
   - `@Enumerated(EnumType.STRING)` — enum columns

   Build a code-side entity map:
   ```
   Entity: PaymentTransaction
     Table: payment_transactions
     Columns: id (PK), merchant_id (FK), amount, status, created_at
     Relations: ManyToOne -> Merchant (merchant_id)
     Indexes: idx_merchant_status (merchant_id, status)
   ```

2. **Fetch DB schema from Redash.** Query the actual database:
   ```bash
   curl -s ${CODE_AGENTS_PUBLIC_BASE_URL}/redash/data-sources/{id}/schema
   ```

   For deeper analysis, run:
   ```bash
   curl -s -X POST ${CODE_AGENTS_PUBLIC_BASE_URL}/redash/run-query \
     -H "Content-Type: application/json" \
     -d '{"data_source_id": <id>, "query": "SHOW TABLES", "max_age": 0}'
   ```

   Then for each important table:
   ```bash
   curl -s -X POST ${CODE_AGENTS_PUBLIC_BASE_URL}/redash/run-query \
     -H "Content-Type: application/json" \
     -d '{"data_source_id": <id>, "query": "DESCRIBE <table_name>", "max_age": 0}'
   ```

   And check indexes:
   ```bash
   curl -s -X POST ${CODE_AGENTS_PUBLIC_BASE_URL}/redash/run-query \
     -H "Content-Type: application/json" \
     -d '{"data_source_id": <id>, "query": "SHOW INDEX FROM <table_name>", "max_age": 0}'
   ```

3. **Build ER map.** Create a relationship diagram showing:
   - All entities and their tables
   - Primary keys and foreign keys
   - Relationship types (1:1, 1:N, M:N)
   - Join paths between entities

   Format as a text-based ER diagram:
   ```
   [Merchant] 1--N [PaymentTransaction] N--1 [PaymentMethod]
       |                    |
       |                    N
       1                    |
       |              [TransactionLog]
   [MerchantConfig]
   ```

4. **Identify mismatches.** Compare code entities vs DB schema:
   - **Missing in DB** — entity declared in code but table missing in DB
   - **Missing in code** — table exists in DB but no entity maps to it (orphan table)
   - **Column mismatch** — column type/name differs between code and DB
   - **Missing FK constraint** — relationship in code but no FK in DB
   - **Naming inconsistency** — code uses camelCase but DB uses snake_case incorrectly

5. **Identify missing indexes.** Check for:
   - Foreign key columns without indexes
   - Columns used in WHERE clauses (from `@Query` annotations) without indexes
   - Composite indexes that could improve common query patterns
   - Redundant indexes (subset of another index)

6. **Generate report.** Output a structured analysis:
   ```
   ## Schema Analysis Report

   ### Entity Map: N entities across M tables
   | Entity | Table | Columns | Relations | Indexes |
   |--------|-------|---------|-----------|---------|

   ### Mismatches Found: X issues
   | Type | Entity/Table | Details | Severity |
   |------|-------------|---------|----------|

   ### Missing Indexes: Y suggestions
   | Table | Suggested Index | Reason | Impact |
   |-------|----------------|--------|--------|

   ### Orphan Tables: Z tables
   | Table | Row Count | Last Modified | Action |
   |-------|-----------|---------------|--------|
   ```

## Definition of Done

- [ ] All JPA entities scanned from the codebase
- [ ] DB schema fetched from Redash for all relevant data sources
- [ ] ER map generated showing all entities and relationships
- [ ] Code-vs-DB mismatches identified and categorized
- [ ] Missing indexes identified with impact assessment
- [ ] Orphan tables listed with recommended action
- [ ] Structured report delivered to the user
