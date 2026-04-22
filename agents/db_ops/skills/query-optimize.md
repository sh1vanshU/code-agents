---
name: query-optimize
description: Analyze SQL queries for performance issues — SELECT *, missing LIMIT, wildcard LIKE, missing indexes, subquery anti-patterns
version: "1.0"
tags: [sql, query, optimization, performance, database, index]
---

# SQL Query Optimizer

## Purpose
Static analysis of SQL queries to detect common performance anti-patterns and suggest optimizations.

## Workflow

### Step 1: Parse Query
- Tokenize SQL query (SELECT, FROM, WHERE, JOIN, etc.)
- Identify tables, columns, conditions, joins, subqueries

### Step 2: Detect Issues
- **SELECT *** — suggest specific column list
- **Missing LIMIT** — unbounded result sets on SELECT queries
- **Leading wildcard LIKE** — `LIKE '%term%'` prevents index usage
- **Missing index hints** — WHERE/JOIN columns without likely indexes
- **Cartesian joins** — joins without ON conditions
- **Subquery in WHERE** — suggest JOIN or CTE instead
- **ORDER BY without index** — full table scan risk

### Step 3: Report
- Severity-ranked findings with line/position info
- Original query with annotated issues
- Optimized query suggestion
- Index creation recommendations
