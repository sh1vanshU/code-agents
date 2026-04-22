---
name: generate-tests
description: Generate comprehensive tests for a source file
trigger: generate tests, create tests, write tests
---
# Test Generation

When asked to generate tests for a file:

1. **Read the source file** — understand its structure, classes, functions, and dependencies
2. **Identify context** — language, test framework, project conventions, existing test patterns
3. **Analyze dependencies** — find external calls (HTTP, DB, filesystem, subprocess) that need mocking
4. **Generate test structure:**
   - Unit tests for every public function/method
   - Integration tests for key workflows and multi-step operations
   - Edge cases: null/None inputs, empty collections, boundary values, large inputs
   - Error cases: exceptions, invalid input, timeout scenarios, permission errors
   - Mock all external dependencies using the appropriate mocking library
5. **Follow project conventions** — match existing test file naming, structure, and patterns
6. **Target 80%+ coverage** — ensure all branches and code paths are exercised
7. **Use descriptive test names** — each test name should explain the scenario being tested

## Mock Strategy
- Python: `unittest.mock.patch` / `pytest-mock` fixtures
- Java: `@Mock` + `@InjectMocks` with Mockito
- JavaScript/TypeScript: `jest.mock()` / `jest.spyOn()`
- Go: interfaces + `gomock`

## Output Format
- Output ONLY the test code as a complete, runnable file
- Include all necessary imports
- Group related tests in classes or describe blocks
- Add setup/teardown or beforeEach/afterEach where needed
