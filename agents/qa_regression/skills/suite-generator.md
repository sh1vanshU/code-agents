---
name: suite-generator
description: Auto-generate a complete test automation framework from scratch when no tests exist
---

## When to Use
- Repo has NO existing test suite (0 test files)
- User asks for full test coverage setup from scratch
- Triggered via `/qa-suite` slash command or `code-agents qa-suite` CLI

## Before You Start
- The `/qa-suite` command has already analyzed the repo and generated skeleton test files
- Review the QA SUITE GENERATION context injected into the conversation
- Understand the detected stack (language, framework, build tool)

## Workflow

1. **Review generated analysis:**
   - Check discovered endpoints, services, repositories
   - Note CRITICAL services (payment, auth, billing) — these need extra coverage

2. **Write base infrastructure first:**
   - Config files (application-test.yml for Spring, conftest.py for Python, jest.config.js for JS)
   - Base test classes with shared fixtures
   - Test utilities (builders, factories, matchers)

3. **Generate controller/endpoint tests:**
   - For each endpoint: happy path, validation errors, auth failures, not found
   - Use MockMvc (Spring) / TestClient (FastAPI) / supertest (Express)
   - Test request/response contracts, status codes, headers

4. **Generate service unit tests:**
   - Mock ALL dependencies (repositories, external clients)
   - Test business logic: happy path + every error branch
   - For CRITICAL services: add boundary tests, concurrent access tests
   - Use [DELEGATE:code-tester] for complex service test files

5. **Generate repository/DAO tests:**
   - Use @DataJpaTest (Spring) or test DB fixtures (Python)
   - Test custom queries, pagination, edge cases

6. **Add integration tests:**
   - End-to-end flows for critical paths (e.g., create order -> pay -> confirm)
   - Use test containers or embedded DB

7. **Run tests and fix:**
   ```bash
   # Java/Maven
   mvn test -pl . -Dtest="*Test"
   # Python
   pytest tests/ -v --tb=short
   # JavaScript
   npm test
   ```

8. **Git operations:**
   ```bash
   git checkout -b qa-suite/auto-generated-YYYYMMDD
   git add src/test/ tests/ __tests__/
   git commit -m "test: add auto-generated QA regression suite"
   ```
   Do NOT push — user will review and push when ready.

## Test Quality Standards
- Arrange/Act/Assert pattern
- Descriptive test names: `test_<method>_<scenario>_<expectedResult>`
- Each test tests ONE thing
- No test interdependencies
- Mock ALL externals — no real API calls, no real DB in unit tests
- Assert specific values, not just "not null"

## Definition of Done
- Every discovered endpoint has at least 2 tests (happy + error)
- Every service method has at least 2 tests (happy + error)
- CRITICAL services have 5+ tests each
- All tests pass green
- Files committed on a new branch (not pushed)
