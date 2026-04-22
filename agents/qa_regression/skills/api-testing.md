---
name: api-testing
description: Test API endpoints with curls — define test cases, execute, validate responses, generate pass/fail report
---

## Before You Start

- [ ] Identify the base URL for the target environment (dev, staging, etc.) — do not hardcode production URLs
- [ ] Verify the service is running and reachable (hit the health endpoint first)
- [ ] Gather required auth tokens or API keys for authenticated endpoints
- [ ] Know the expected API version — are you testing v1, v2, or the latest?
- [ ] Check if there are OpenAPI/Swagger specs available — use them to generate comprehensive test cases

## Workflow

1. **Define test cases.** For each API endpoint to test, create a test case with:
   - Test name (descriptive, unique)
   - URL (full endpoint path)
   - HTTP method (GET, POST, PUT, DELETE)
   - Headers (Content-Type, Authorization, etc.)
   - Request body (for POST/PUT)
   - Expected status code
   - Expected response body (key fields to validate)

2. **Execute each test case.** Run the curl command and capture the response:
   ```bash
   curl -s -w "\n%{http_code}" -X POST ${BASE_URL}/v1/agents/code-reasoning/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"messages": [{"role": "user", "content": "test"}], "stream": false}'
   ```
   The `-w "\n%{http_code}"` flag appends the HTTP status code after the response body.

3. **Validate the response.** For each test case, check:
   - Status code matches expected (e.g., 200, 201, 400, 404)
   - Response body contains expected fields
   - Response body values match expected values (where exact match is required)
   - Response time is within acceptable limits
   - Content-Type header is correct

4. **Record the result.** For each test case, mark as:
   - **PASS** — status code and response body match expectations
   - **FAIL** — status code or response body does not match
   - **ERROR** — request failed (connection refused, timeout, DNS error)

5. **Generate the pass/fail report.** Format results as a structured table:

   ```
   ## API Test Results

   | # | Test Name           | Method | Endpoint              | Expected | Actual | Result |
   |---|--------------------:|--------|----------------------|----------|--------|--------|
   | 1 | Health check        | GET    | /health              | 200      | 200    | PASS   |
   | 2 | Create completion   | POST   | /v1/agents/.../chat  | 200      | 200    | PASS   |
   | 3 | Invalid agent       | POST   | /v1/agents/bad/chat  | 404      | 404    | PASS   |
   | 4 | Missing body        | POST   | /v1/agents/.../chat  | 422      | 500    | FAIL   |

   ## Summary
   - Total: N tests
   - Passed: N
   - Failed: N
   - Errors: N

   ## Failed Test Details
   | Test Name    | Expected                  | Actual                    |
   |-------------|---------------------------|---------------------------|
   | Missing body | 422 Unprocessable Entity  | 500 Internal Server Error |
   ```

6. **Report actionable findings.** For each failure:
   - What was expected vs what happened
   - Likely root cause (missing validation, wrong handler, server error)
   - Which code file and function is likely responsible

## Contract Testing

Beyond functional correctness, verify the API contract:

| Check | What to Verify | Why It Matters |
|-------|---------------|----------------|
| **Response schema** | All documented fields present, correct types, no extra undocumented fields | Consumers parse responses based on the contract — extra or missing fields break them |
| **Error response format** | Errors follow a consistent schema (`{"error": {"code": ..., "message": ...}}`) | Consumers need predictable error handling |
| **Content-Type** | Response `Content-Type` matches expected (`application/json`, etc.) | Incorrect Content-Type causes parsing failures in clients |
| **Pagination** | Paginated endpoints return `next`, `total`, `page` fields consistently | Broken pagination causes data loss or infinite loops in consumers |
| **Versioning** | API version in URL or header matches the expected behavior | Version mismatches cause subtle bugs |

## Idempotency Checks

For state-changing endpoints (POST, PUT, DELETE), test idempotency:

1. **POST (create)**: Send the same create request twice. Does it create duplicates, return the existing resource, or return a conflict error? Document the behavior.
2. **PUT (update)**: Send the same update request twice. The result should be identical both times.
3. **DELETE**: Delete the same resource twice. First should succeed (200/204), second should return 404. Never return 500.
4. **Concurrent requests**: Send two identical requests simultaneously. Verify no data corruption or duplicate creation.

## Rate Limit Awareness

If the API has rate limiting:
- [ ] Test that requests within the limit succeed normally
- [ ] Test that exceeding the limit returns 429 (Too Many Requests) with a `Retry-After` header
- [ ] Verify rate limit does not persist across test runs (reset between suites)
- [ ] Note the rate limit in the test report so other testers and consumers are aware

## Risk Assessment

| Risk | Signs | Mitigation |
|------|-------|------------|
| **Test pollution** | Tests create data that affects other tests | Use unique identifiers per test run; clean up after each test |
| **Environment drift** | Tests pass in staging but fail in production | Use environment-agnostic test data; parameterize base URLs |
| **Auth token expiry** | Tests fail mid-suite with 401 errors | Refresh tokens before the suite; use long-lived test tokens |
| **Flaky external dependencies** | Intermittent timeouts or 503 errors from upstream services | Retry once on 5xx errors; report flakiness separately from real failures |

## Definition of Done

- [ ] All critical-path endpoints tested (at minimum: health, auth, core CRUD operations)
- [ ] Both happy path and error cases validated
- [ ] API contract verified (response schema, Content-Type, error format)
- [ ] Idempotency tested for state-changing endpoints
- [ ] Rate limits documented (if applicable)
- [ ] Structured pass/fail report generated with actionable failure details
- [ ] No 500 errors on valid requests — every 500 is a bug
