---
name: generate-from-spec
description: Full code generation from specification — Jira ticket, API spec, or LLD to complete vertical slice
---

## Before You Start

Gather the input specification. Exactly one of:
- **Jira ticket**: use `[SKILL:write-from-jira]` to fetch ticket details, then return here
- **OpenAPI spec**: read the YAML/JSON file, identify the endpoints to implement
- **LLD document**: read the design doc, extract entities, APIs, and flows

Read the project's `CLAUDE.md`, existing code patterns, and `[SKILL:java-spring]` standards before writing any code.

## Workflow

1. **Parse the specification.** Extract from the input:
   - Entities and their fields (types, constraints, relationships)
   - API endpoints (method, path, request/response bodies, status codes)
   - Business rules and validation constraints
   - Error scenarios and edge cases
   - Non-functional requirements (pagination, caching, async)

2. **Map to project layers.** Plan the vertical slice:
   - **Entity** — JPA entity with `@Entity`, `@Table`, field constraints (`@NotNull`, `@Size`)
   - **Repository** — Spring Data interface, custom `@Query` methods if needed
   - **Service** — Business logic, transaction boundaries (`@Transactional`)
   - **DTO** — `record` types for Request and Response (use `[SKILL:java-spring]` conventions)
   - **Mapper** — MapStruct interface or manual mapping methods
   - **Controller** — REST endpoints with `@Valid`, `@PathVariable`, `@RequestParam`
   - **Config** — application.yml properties, `@ConfigurationProperties` bean if needed
   - **Exception** — custom exceptions + `@ControllerAdvice` handler

3. **Generate bottom-up.** Create files in this order:
   ```
   Entity → Repository → DTO (Request/Response records) → Mapper →
   Service (interface + impl) → Controller → Exception handler → Config
   ```
   For each file:
   - Place in the correct package following existing project structure
   - Follow `[SKILL:java-spring]` standards (constructor injection, records for DTOs, etc.)
   - Add validation annotations: `@NotNull`, `@NotBlank`, `@Size`, `@Min`, `@Max`, `@Pattern`
   - Add logging: `private static final Logger log = LoggerFactory.getLogger(ClassName.class);`

4. **Add error handling.** Create or update `@ControllerAdvice`:
   - `@ExceptionHandler` for each custom exception
   - Standard error response body: `{ "error": "...", "message": "...", "timestamp": "..." }`
   - Map exceptions to HTTP status codes (400, 404, 409, 500)

5. **Generate tests.** For each layer:
   - **Repository**: `@DataJpaTest` with test DB, verify custom queries
   - **Service**: `@ExtendWith(MockitoExtension.class)`, mock repository, test business logic
   - **Controller**: `@WebMvcTest`, mock service, test request validation + response codes
   - **Integration**: `@SpringBootTest` with `@Testcontainers` if DB needed, test full flow

6. **Run build and tests.**
   ```bash
   # Build
   mvn clean compile -q  # or: gradle build
   # Tests
   mvn test -q            # or: gradle test
   ```
   Fix any compilation errors or test failures. Repeat until green.

7. **Verify completeness.** Check against the original spec:
   - Every endpoint implemented and tested
   - Every validation rule enforced
   - Every error scenario handled
   - Every business rule covered by a test

## Definition of Done

- All layers generated: Entity, Repository, DTO, Mapper, Service, Controller, Config, Exception handler
- Validation annotations on all request DTOs
- `@ControllerAdvice` handles all custom exceptions
- Logging at service layer (entry, exit, errors)
- Unit tests for service + controller, integration test for full flow
- Build passes with zero errors
- All tests green
