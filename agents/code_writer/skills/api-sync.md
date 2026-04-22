---
name: api-sync
description: Check synchronization between API spec (OpenAPI/Swagger) and actual code routes
version: "1.0"
tags: [api, openapi, swagger, sync, drift, validation]
---

# API Spec/Code Sync Checker

## Purpose
Detect drift between an OpenAPI/Swagger specification file and the actual route definitions in code. Ensures documentation matches implementation.

## Workflow

### Step 1: Parse Spec
- Load OpenAPI 3.x or Swagger 2.x spec (JSON or YAML)
- Extract all endpoint definitions: method, path, parameters, request/response schemas

### Step 2: Scan Code
- Detect framework (FastAPI, Express, Flask, Spring, etc.)
- Parse route decorators and handlers
- Extract actual endpoints with methods and paths

### Step 3: Compare
- Match spec endpoints to code endpoints
- Identify endpoints in spec but missing from code
- Identify endpoints in code but missing from spec
- Compare parameter definitions and response schemas

### Step 4: Report
- Sync score (0-100%)
- List of discrepancies with severity
- Suggestions to fix drift (update spec or add routes)
