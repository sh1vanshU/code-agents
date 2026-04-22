---
name: orm-review
description: Scan ORM code for anti-patterns — N+1 queries, raw SQL injection, lazy loading in loops, missing eager loading
version: "1.0"
tags: [orm, database, anti-pattern, n+1, sqlalchemy, django, review]
---

# ORM Anti-Pattern Reviewer

## Purpose
Static analysis of ORM usage to detect common anti-patterns that cause performance issues, security risks, and maintainability problems.

## Workflow

### Step 1: Scan Code
- Find files using ORM imports (SQLAlchemy, Django ORM, Peewee, Prisma, Sequelize)
- Parse query patterns, relationship definitions, serialization code

### Step 2: Detect Anti-Patterns
- **N+1 queries** — queries inside loops (for user in users: user.orders)
- **Raw SQL** — `session.execute(text(...))` bypassing ORM safety
- **SQL injection risk** — f-string/format interpolation in raw queries
- **Lazy loading in serialization** — accessing relationships in list comprehensions
- **Missing eager loading** — no `joinedload`/`selectinload` for accessed relations
- **Unbounded queries** — `.all()` without limit
- **Missing transaction boundaries** — multiple writes without explicit transaction

### Step 3: Report
- Findings with file, line, severity, and category
- Explanation of why each pattern is problematic
- Concrete fix suggestion with code example
