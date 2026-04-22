---
name: query-builder
description: Write SQL queries from natural language — analyze repo schema, build SELECT, execute on Redash, format results
---

## Before You Start

- [ ] Confirm the target data source ID (use `GET /redash/data-sources` to list available sources)
- [ ] Understand the user's intent — what data do they need and why
- [ ] Check if the repo has JPA entities (`@Entity`, `@Table`) to infer schema from code
- [ ] Confirm READ-ONLY mode — only SELECT queries are allowed

## Workflow

1. **Understand the request.** Parse the user's natural language query. Identify:
   - Target tables and columns
   - Filter conditions (WHERE)
   - Aggregations (COUNT, SUM, AVG, MIN, MAX)
   - Grouping (GROUP BY) and ordering (ORDER BY)
   - JOINs needed across tables
   - Whether CTEs or subqueries are required for complex logic

2. **Analyze repo schema.** Scan the codebase for JPA entity definitions:
   - `@Entity` / `@Table(name = "...")` — table names
   - `@Column(name = "...")` — column names and types
   - `@ManyToOne` / `@OneToMany` / `@ManyToMany` — relationships and JOIN paths
   - `@Id` / `@GeneratedValue` — primary keys
   - `@Enumerated` — enum columns and valid values

   Cross-reference with Redash schema:
   ```bash
   curl -s ${CODE_AGENTS_PUBLIC_BASE_URL}/redash/data-sources/{id}/schema
   ```

3. **Build the SQL query.** Construct the query following these rules:
   - **Always SELECT** — never INSERT, UPDATE, DELETE, or DROP
   - **Always LIMIT** — default LIMIT 100, adjust based on user need
   - **Shard-aware** — if tables are sharded, query a single shard (e.g., `acqcore0`)
   - **Readable formatting** — use indentation, aliases, and comments
   - **Parameterize** where possible — note which values the user should customize

   Support patterns:
   - Simple SELECT with WHERE and ORDER BY
   - Aggregations with GROUP BY and HAVING
   - Multi-table JOINs (INNER, LEFT, RIGHT)
   - Subqueries in WHERE or FROM
   - CTEs (WITH clause) for multi-step logic
   - Window functions (ROW_NUMBER, RANK, LAG/LEAD)

4. **Show the SQL.** Present the query to the user with:
   - The formatted SQL
   - Explanation of what each part does
   - Any assumptions made about table/column names
   - Expected result shape (columns and rough row count)

5. **Execute on Redash.** Run the query:
   ```bash
   curl -s -X POST ${CODE_AGENTS_PUBLIC_BASE_URL}/redash/run-query \
     -H "Content-Type: application/json" \
     -d '{"data_source_id": <id>, "query": "<SQL>", "max_age": 0}'
   ```

6. **Format and explain results.** Present the output:
   - Format as a readable table (markdown or aligned text)
   - Highlight key findings and patterns
   - Suggest follow-up queries if the data reveals something interesting
   - Note any data quality concerns (NULLs, unexpected values)

## Definition of Done

- [ ] SQL query written and explained before execution
- [ ] Query is READ-ONLY (SELECT only) with LIMIT applied
- [ ] Query executed successfully on Redash
- [ ] Results formatted and explained to the user
- [ ] Follow-up suggestions provided if applicable
