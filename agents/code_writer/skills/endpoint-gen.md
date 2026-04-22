---
name: endpoint-gen
description: Generate CRUD endpoints for a resource with models, routes, and tests
version: "1.0"
tags: [api, crud, rest, code-generation, fastapi, express]
---

# CRUD Endpoint Generator

## Purpose
Generate complete CRUD (Create, Read, Update, Delete) endpoint scaffolding for a named resource, targeting a specific framework.

## Workflow

### Step 1: Gather Requirements
- Resource name (e.g. User, Order, Product)
- Target framework: fastapi (default), express, flask, django
- Field definitions (optional — inferred from name if omitted)
- Authentication requirements

### Step 2: Generate Code
- Pydantic/Schema model with field types and validation
- Router/controller with all CRUD operations (list, get, create, update, delete)
- Database model / migration stub
- Request/response serialization

### Step 3: Generate Tests
- Unit tests for each endpoint (happy path + error cases)
- Fixture factories for test data
- Integration test skeleton

### Step 4: Output
- Print generated code with syntax highlighting
- Optionally write files to the project directory
- Show curl examples for manual testing
