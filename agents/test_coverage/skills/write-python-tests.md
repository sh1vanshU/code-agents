---
name: write-python-tests
description: Write pytest tests with unittest.mock for uncovered Python modules
trigger: python tests, pytest, write tests python, py tests
---

## Workflow

1. **Detect the project test framework.**
   ```bash
   ls pyproject.toml setup.cfg pytest.ini conftest.py 2>/dev/null && head -5 pyproject.toml 2>/dev/null
   ```
   Identify: pytest vs unittest, fixture patterns, conftest conventions, test directory layout (`tests/` vs `test/` vs alongside source).

2. **Read the source module under test.** Identify every public function, class, and method. List which have existing tests and which do not. Focus on untested code first.

3. **Analyze dependencies.** For each import and parameter:
   - **Mock** if it is an external service, API client, database, file I/O, network call, or expensive computation
   - **Use real** if it is a dataclass, enum, config dict, or pure function
   - **Patch at the usage site** — always `@patch("module_under_test.dependency")`, not where the dependency is defined

4. **Create the test file.** Follow the project's naming convention (default: `tests/test_<module>.py`):
   ```python
   """Tests for code_agents.<module>."""
   import pytest
   from unittest.mock import patch, MagicMock, AsyncMock
   from code_agents.<module> import TargetClass, target_function
   ```

5. **Write test functions using `test_<method>_<scenario>` naming:**
   ```python
   def test_process_order_returns_confirmation_for_valid_input():
       # Arrange
       order = {"id": "123", "amount": 100}
       # Act
       result = process_order(order)
       # Assert
       assert result.status == "confirmed"
       assert result.amount == 100
   ```

6. **Cover these scenarios for each function/method:**
   - **Happy path** — Normal input, expected output
   - **Edge cases** — None, empty string, empty list, zero, negative numbers
   - **Error paths** — Expected exceptions with `pytest.raises`
   - **Boundary values** — Threshold values, max/min, single-element collections
   ```python
   def test_process_order_raises_on_missing_amount():
       with pytest.raises(ValueError, match="amount is required"):
           process_order({"id": "123"})
   ```

7. **Use `@pytest.mark.parametrize` for multiple input combinations:**
   ```python
   @pytest.mark.parametrize("amount,expected_fee", [
       (100, 2.5),
       (0, 0),
       (1000, 25.0),
   ])
   def test_calculate_fee(amount, expected_fee):
       assert calculate_fee(amount) == expected_fee
   ```

8. **Use fixtures for shared setup.** Create in `conftest.py` or at module level:
   ```python
   @pytest.fixture
   def mock_config():
       return {"api_key": "test-key", "timeout": 30}

   @pytest.fixture
   def service(mock_config):
       with patch("code_agents.service.load_config", return_value=mock_config):
           yield ServiceClass(mock_config)
   ```

9. **Mock external dependencies properly:**
   ```python
   @patch("code_agents.backend.requests.post")
   def test_send_request_returns_parsed_response(mock_post):
       mock_post.return_value = MagicMock(
           status_code=200,
           json=MagicMock(return_value={"result": "ok"})
       )
       result = send_request("/api/test", {"key": "value"})
       assert result == {"result": "ok"}
       mock_post.assert_called_once()
   ```

10. **For async functions, use `@pytest.mark.asyncio`:**
    ```python
    @pytest.mark.asyncio
    async def test_async_fetch_returns_data():
        with patch("code_agents.client.aiohttp.ClientSession") as mock_session:
            mock_resp = AsyncMock()
            mock_resp.json = AsyncMock(return_value={"data": [1, 2, 3]})
            mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_resp
            result = await async_fetch("/data")
            assert result == {"data": [1, 2, 3]}
    ```

11. **Run the tests and verify they pass.**
    ```bash
    poetry run pytest tests/test_<module>.py -x -v
    ```
    If any test fails, read the failure output, fix the test, and re-run. Never leave failing tests.

12. **Check coverage for the module under test.**
    ```bash
    poetry run pytest tests/test_<module>.py --cov=code_agents.<module> --cov-report=term-missing -x
    ```
    If coverage is below target, identify uncovered lines from the `Missing` column and write additional tests. Iterate until target is met.

13. **Final review.** Ensure:
    - No test depends on execution order or global state
    - All patches are scoped (context manager or decorator) — no leaked mocks
    - Test names clearly describe the scenario being tested
    - No production code was modified just to make tests pass
    - Tests are deterministic — no random data, no time-dependent assertions without freezing time
