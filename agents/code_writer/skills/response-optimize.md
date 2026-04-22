---
name: response-optimize
description: Scan API endpoints for response optimization opportunities — pagination, field selection, N+1, caching
version: "1.0"
tags: [api, performance, optimization, pagination, n+1, caching]
---

# API Response Optimizer

## Purpose
Analyze API endpoint implementations for common response performance anti-patterns and suggest optimizations.

## Workflow

### Step 1: Scan Endpoints
- Find all API route handlers in the codebase
- Analyze response construction patterns

### Step 2: Detect Anti-Patterns
- **Missing pagination** — list endpoints returning `.all()` without limit/offset
- **No field selection** — returning full objects when clients need subsets
- **N+1 queries** — loops with individual database queries inside
- **Missing caching headers** — no Cache-Control or ETag on read endpoints
- **Large payloads** — returning nested objects without depth control

### Step 3: Report
- Findings grouped by severity (critical, high, medium, low)
- Specific file and line numbers
- Concrete fix suggestions with code examples
