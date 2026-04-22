---
name: write-missing
description: Analyze codebase for untested code, write missing tests
---

## Workflow

1. **Get the coverage report** to identify untested files and functions.
   ```bash
   curl -sS "${BASE_URL}/testing/coverage"
   ```

2. **Get coverage gaps** comparing against the base branch.
   ```bash
   curl -sS "${BASE_URL}/testing/gaps?base=main&head=release"
   ```

3. **Prioritize what to test.** Rank untested code by:
   - Critical business logic (payments, auth, data validation)
   - New code with zero coverage
   - Error handling paths
   - Public API endpoints

4. **Read the untested code.** For each file/function that needs tests:
   - Understand what it does
   - Identify its inputs, outputs, and side effects
   - Note its dependencies (what to mock)
   - List the test cases needed (happy path, edge cases, error paths)

5. **Read existing test patterns.** Match the project's test style:
   - Framework (pytest, jest, JUnit)
   - Naming conventions
   - Fixture and mock patterns
   - Directory structure

6. **Write the missing tests.** For each untested function:
   - Create a test file following project conventions
   - Write tests using Arrange-Act-Assert pattern
   - Mock external dependencies
   - Cover happy path, edge cases, and error paths
   - Name tests descriptively: `test_<feature>_<scenario>_<expected>`

7. **Run the new tests** to verify they pass.
   ```bash
   curl -sS -X POST ${BASE_URL}/testing/run \
     -H "Content-Type: application/json" \
     -d '{"branch": "HEAD"}'
   ```

8. **Report what was added:** number of new tests, files covered, new coverage percentage.
