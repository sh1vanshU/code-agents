---
name: rest-to-grpc
description: Convert REST API endpoints to gRPC proto definitions with service extraction
version: "1.0"
tags: [api, grpc, proto, rest, conversion, code-generation]
---

# REST to gRPC Converter

## Purpose
Scan existing REST endpoints and generate equivalent gRPC `.proto` definitions with proper service grouping, message types, and RPC naming.

## Workflow

### Step 1: Discover REST Endpoints
- Scan codebase for route definitions (FastAPI, Express, Flask, Spring)
- Extract method, path, request body, response shape, path parameters

### Step 2: Generate Proto
- Group endpoints by resource into gRPC services
- Map HTTP methods to RPC names (GET list -> List, GET detail -> Get, POST -> Create, PUT -> Update, DELETE -> Delete)
- Generate request/response message types from endpoint signatures
- Use PascalCase for service, RPC, and message names

### Step 3: Output
- Complete `.proto` file with syntax, package, imports
- Service definitions with all RPCs
- Message type definitions
- Optional: gRPC gateway annotations for HTTP compatibility
