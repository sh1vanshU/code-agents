---
name: integration-test
description: Write integration tests with real dependencies
---

## Workflow

1. **Identify the integration boundary.** Determine what components interact: API endpoint + database, service A + service B, CLI + server, etc.

2. **Read the existing integration test setup** in the project. Look for:
   - Test fixtures for database setup/teardown
   - Test client configuration (e.g., FastAPI `TestClient`, Django `Client`)
   - Docker Compose files for test dependencies
   - conftest.py or setup files with shared fixtures

3. **Design the test scenarios.** Integration tests should verify:
   - End-to-end request flow through multiple layers
   - Data persistence: write then read back
   - Error propagation across boundaries
   - Response format and status codes
   - Side effects (database writes, queue messages, file creation)

4. **Set up the test environment.** Use real dependencies where possible, mock only external third-party services:
   ```python
   @pytest.fixture
   def client():
       """FastAPI test client with real database."""
       from code_agents.app import app
       with TestClient(app) as c:
           yield c
   ```

5. **Write the integration tests.** Test the full request-response cycle:
   ```python
   def test_create_and_retrieve_resource(client, db_session):
       # Create
       response = client.post("/api/resource", json={"name": "test"})
       assert response.status_code == 201
       resource_id = response.json()["id"]

       # Retrieve
       response = client.get(f"/api/resource/{resource_id}")
       assert response.status_code == 200
       assert response.json()["name"] == "test"
   ```

6. **Test error scenarios across boundaries:**
   - Invalid input at the API level → proper error response
   - Database constraint violations → meaningful error message
   - Downstream service timeout → graceful degradation

7. **Add cleanup.** Ensure tests clean up after themselves: delete created records, reset state, close connections.

8. **Run the integration tests** and verify they pass consistently (no flakiness):
   ```bash
   poetry run pytest tests/integration/ -v --timeout=30
   ```
