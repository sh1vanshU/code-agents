---
name: api-changelog
description: Generate API changelog by diffing two OpenAPI spec versions — added, removed, modified, breaking changes
version: "1.0"
tags: [api, changelog, diff, breaking-changes, openapi, versioning]
---

# API Changelog Generator

## Purpose
Compare two versions of an API spec (OpenAPI/Swagger) and generate a structured changelog highlighting added, removed, and modified endpoints with breaking change detection.

## Workflow

### Step 1: Load Specs
- Parse old and new OpenAPI/Swagger specs (JSON or YAML)
- Extract all endpoints with methods, parameters, request/response schemas

### Step 2: Diff
- Identify added endpoints (in new but not old)
- Identify removed endpoints (in old but not new) — flag as breaking
- Identify modified endpoints (parameter changes, schema changes)
- Detect breaking changes: removed endpoints, removed required fields, type changes

### Step 3: Classify
- Non-breaking: added endpoints, added optional parameters
- Breaking: removed endpoints, removed fields, type changes, new required parameters
- Deprecation: endpoints marked deprecated

### Step 4: Format Changelog
- Grouped by change type (Added, Removed, Modified, Breaking)
- Migration guide for breaking changes
- Output as text, markdown, or JSON
