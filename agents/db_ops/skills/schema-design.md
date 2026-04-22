---
name: schema-design
description: Design database schema from entity definitions — tables, columns, foreign keys, indexes, constraints
version: "1.0"
tags: [database, schema, design, sql, migration, entity]
---

# Database Schema Designer

## Purpose
Transform entity/model definitions (JSON) into a complete database schema with proper normalization, foreign keys, indexes, and constraints.

## Workflow

### Step 1: Parse Entities
- Load entity JSON with field names and types
- Detect relationships (fk:Table references)
- Detect special types (enum, datetime, text, json)

### Step 2: Design Schema
- Create tables with proper naming (snake_case, plural)
- Auto-add primary key (id) if not specified
- Map field types to SQL column types
- Create foreign key constraints for relationships
- Add created_at/updated_at timestamps
- Create indexes on foreign keys and commonly queried columns
- Handle enum types (CHECK constraints or ENUM type)

### Step 3: Output
- CREATE TABLE SQL statements
- Index creation statements
- Table summary with column details
- Optional: migration file (Alembic, Django, Knex)
