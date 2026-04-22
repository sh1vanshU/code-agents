---
name: unit-test
description: Write unit tests for a class or function with mocks and edge cases
---

## Workflow

1. **Read the code under test.** Understand the function/class signature, its dependencies, its return values, and its side effects.

2. **Read existing tests** in the project to match the testing framework (pytest, jest, JUnit, Go test) and naming conventions.

3. **Identify test cases.** For each function, plan tests for:
   - Happy path: normal input produces expected output
   - Edge cases: empty input, null/None, zero, negative numbers, max values
   - Error paths: invalid input, missing dependencies, exception scenarios
   - Boundary conditions: first/last element, exact threshold values

4. **Set up mocks for external dependencies.** Mock anything the function calls that is outside its module:
   - HTTP clients: use `unittest.mock.patch`, `httpx_mock`, `requests_mock`
   - Database: mock the repository/ORM layer
   - File system: use `tmp_path` fixture or `tempfile`
   - Environment variables: use `monkeypatch.setenv`
   - Time: use `freezegun` or `time_machine`

5. **Write the tests** using Arrange-Act-Assert pattern:
   ```python
   def test_function_name_condition_expected():
       # Arrange
       input_data = {...}
       mock_dep.return_value = expected_response

       # Act
       result = function_under_test(input_data)

       # Assert
       assert result == expected_value
       mock_dep.assert_called_once_with(...)
   ```

6. **Name tests descriptively:** `test_<what>_<condition>_<expected>`. Example: `test_parse_config_empty_file_returns_defaults`.

7. **Run the tests** to verify they pass:
   ```bash
   poetry run pytest tests/test_<module>.py -v
   ```

8. **Verify coverage** by checking that the tests exercise all branches of the code under test. Add tests for any uncovered paths.
