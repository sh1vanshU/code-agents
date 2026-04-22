---
name: endpoint-discovery
description: Discover REST/gRPC/Kafka endpoints in a repo, generate test commands, validate responses, and report results
---

## Before You Start

- [ ] Confirm the target repo path — this is where we scan for endpoints
- [ ] Check if a cached scan exists (`.code-agents/{repo-name}.endpoints.cache.json`)
- [ ] Know the base URL for REST endpoints (default: `http://localhost:8080`)
- [ ] Know the gRPC host if applicable (default: `localhost:9090`)
- [ ] Know the Kafka bootstrap server if applicable (default: `localhost:9092`)

## Workflow

1. **Scan the repository for endpoints.** Use the endpoint scanner to discover all REST, gRPC, and Kafka endpoints:
   ```bash
   # The endpoint scanner runs automatically on `code-agents init`
   # To force a rescan from chat, use: /endpoints scan
   # To view cached results: /endpoints
   ```

   The scanner detects:
   - **REST**: `@RestController`, `@GetMapping`, `@PostMapping`, `@PutMapping`, `@DeleteMapping`, `@PatchMapping`, `@RequestMapping` annotations in Java/Spring files
   - **gRPC**: `service` and `rpc` definitions in `.proto` files
   - **Kafka**: `@KafkaListener` annotations with topic and group ID

2. **Review discovered endpoints.** Check the scan summary:
   - `/endpoints` — full summary with all endpoint types
   - `/endpoints rest` — REST endpoints only
   - `/endpoints grpc` — gRPC services only
   - `/endpoints kafka` — Kafka listeners only

3. **Generate test commands.** For each endpoint type, generate executable test commands:
   - **REST**: curl commands with method, headers, and sample body
   - **gRPC**: grpcurl commands with service/method and empty request
   - **Kafka**: kafka-console-producer commands with test payload

4. **Execute test commands.** Run generated curls against the target environment:
   ```bash
   # Health check first
   curl -sS "http://localhost:8080/health"

   # Then test each endpoint
   curl -sS "http://localhost:8080/api/v1/users"
   curl -sS -X POST "http://localhost:8080/api/v1/users" \
     -H "Content-Type: application/json" -d '{"name": "test"}'
   ```

5. **Validate responses.** For each endpoint:
   - Check HTTP status code (2xx for success, appropriate 4xx for errors)
   - Verify response Content-Type header
   - Validate response body schema (expected fields present, correct types)
   - Note response time for performance baseline

6. **Generate the report.** Produce a structured report:

   ```
   ## Endpoint Discovery Report

   Repository: {repo-name}
   Scanned: {timestamp}
   Total: {N} endpoints ({X} REST, {Y} gRPC, {Z} Kafka)

   ### REST Endpoints
   | # | Method | Path              | Controller        | Status | Notes |
   |---|--------|-------------------|-------------------|--------|-------|
   | 1 | GET    | /api/v1/users     | UserController    | 200 OK | -     |
   | 2 | POST   | /api/v1/users     | UserController    | 201    | -     |

   ### gRPC Services
   | # | Service       | Method    | Request Type | Response Type |
   |---|---------------|-----------|-------------|---------------|
   | 1 | UserService   | GetUser   | UserRequest | UserResponse  |

   ### Kafka Listeners
   | # | Topic              | Group ID       | File                  |
   |---|--------------------|----------------|-----------------------|
   | 1 | user.events        | user-service   | UserEventListener.java|

   ### Test Results Summary
   - Tested: N endpoints
   - Passed: N
   - Failed: N
   - Unreachable: N
   ```

## Cross-Agent Delegation

- Use `[DELEGATE:code-reasoning]` to analyze endpoint implementations
- Use `[DELEGATE:code-tester]` to write integration tests for discovered endpoints
- Use `[DELEGATE:jenkins-cicd]` to run endpoint tests as part of CI/CD pipeline

## Risk Assessment

| Risk | Signs | Mitigation |
|------|-------|------------|
| **Undocumented endpoints** | Endpoints found in code but not in Swagger/OpenAPI spec | Flag as documentation gap |
| **Dead endpoints** | Endpoints in code but returning 404 or not routed | Check routing config, may be disabled feature flags |
| **Missing auth** | Endpoints responding 200 without authentication | Flag as security concern |
| **Schema drift** | Response body differs from documented contract | Compare against OpenAPI spec if available |

## Definition of Done

- [ ] All endpoint types scanned (REST, gRPC, Kafka)
- [ ] Scan results cached for quick access
- [ ] Test commands generated for each endpoint
- [ ] Endpoints tested against target environment
- [ ] Response validation completed (status codes, schemas)
- [ ] Structured report generated with pass/fail summary
- [ ] Security concerns flagged (unauthenticated endpoints, missing HTTPS)
