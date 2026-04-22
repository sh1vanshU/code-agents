---
name: test-infrastructure
description: Set up test infrastructure — Testcontainers, WireMock, test data builders, shared fixtures, test profiles
---

## Before You Start

- Identify which external dependencies the project uses (databases, message queues, HTTP APIs, caches)
- Check the existing test framework and build tool (Maven/Gradle/Poetry/npm)
- Determine if Docker is available for Testcontainers
- Read any existing test configuration files (application-test.yml, conftest.py, jest.config.js)

## Workflow

1. **Audit current test infrastructure.** List what exists:
   - Shared fixtures / conftest files
   - Test configuration profiles
   - Docker compose for tests
   - Mock servers or stubs
   - Test data builders or factories

2. **Set up Testcontainers** for real dependency testing:
   - Add Testcontainers dependency to the build file
   - Create container definitions for each external service (Postgres, Redis, Kafka, Elasticsearch)
   - Configure container lifecycle: start before test class, stop after
   - Wire container connection details into test configuration
   ```python
   # Python example
   @pytest.fixture(scope="session")
   def postgres_container():
       with PostgresContainer("postgres:15") as pg:
           yield pg.get_connection_url()
   ```
   ```java
   // Java example
   @Container
   static PostgreSQLContainer<?> pg = new PostgreSQLContainer<>("postgres:15");
   ```

3. **Set up WireMock / mock servers** for external HTTP APIs:
   - Create a mock server fixture that starts on a random port
   - Define stub mappings for each external API endpoint the project calls
   - Configure the application to point to the mock server URL during tests
   - Add response templates for success, error, and timeout scenarios
   ```python
   @pytest.fixture
   def wiremock():
       with WireMockServer() as wm:
           wm.stub_for(get(url_path_matching("/api/.*"))
               .will_return(ok_json({"status": "ok"})))
           yield wm
   ```

4. **Create shared fixtures and conftest files:**
   - Root `conftest.py` / `TestBase` class with common setup
   - Database transaction rollback fixtures (clean state per test)
   - Authenticated client fixtures (pre-logged-in HTTP client)
   - Temporary directory / file fixtures
   - Clock/time freezing fixtures

5. **Create test data builders** (see also `test-data-factory` skill):
   - Builder for each core entity with sensible defaults
   - Method chaining for overriding specific fields
   - Random but valid data generation for fields that don't matter to the test

6. **Set up test profiles / configuration:**
   - Create `application-test.yml` / `.env.test` / `settings_test.py`
   - In-memory database or Testcontainer connection strings
   - Disabled external integrations (email, SMS, webhooks)
   - Reduced timeouts for faster test execution
   - Logging set to WARN to reduce noise

7. **Configure test organization:**
   - Separate unit tests from integration tests (directories or markers)
   - Add pytest markers: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`
   - Configure CI to run unit tests first, integration tests second
   - Set up parallel test execution if supported (`pytest-xdist`, Maven Surefire forkCount)

8. **Verify the infrastructure works:**
   - Write one smoke test that uses each infrastructure component
   - Run the full test suite to confirm nothing broke
   - Measure test suite startup time — should be under 10 seconds for unit tests

## Definition of Done

- [ ] Testcontainers configured for all external dependencies (or documented why not applicable)
- [ ] WireMock or equivalent configured for external HTTP APIs
- [ ] Shared fixtures in conftest / TestBase cover common setup patterns
- [ ] Test data builders exist for core domain entities
- [ ] Test profile (application-test.yml or equivalent) disables external integrations
- [ ] Unit and integration tests are separated by directory or marker
- [ ] One smoke test per infrastructure component passes
- [ ] Test suite startup time is acceptable (< 10s for unit tests)
