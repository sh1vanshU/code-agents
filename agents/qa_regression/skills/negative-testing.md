---
name: negative-testing
description: Test error cases — invalid input, missing auth, wrong method, empty body, boundary values — verify proper 4xx responses
---

## Before You Start

- [ ] Read the API documentation or route handler code to understand ALL validation rules
- [ ] Identify which endpoints handle sensitive data (PII, financial, auth) — these need extra scrutiny
- [ ] Know the expected error response format for the project (consistent error schema)
- [ ] Check if there is a WAF (Web Application Firewall) or API gateway that may intercept requests before your code

## Workflow

1. **Identify the endpoints to test.** For each API endpoint:
   - Read the route handler to understand expected inputs and validation
   - Identify required fields, types, and constraints
   - Note authentication and authorization requirements

2. **Define negative test cases.** Create tests for each error category:

   **Invalid input:**
   - Wrong data type (string where int expected, number where string expected)
   - Invalid format (malformed email, bad date format, invalid UUID)
   - Values out of range (negative count, string exceeding max length)
   ```bash
   curl -s -w "\n%{http_code}" -X POST ${BASE_URL}/v1/agents/code-reasoning/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"messages": "not-an-array"}'
   ```

   **Missing required fields:**
   - Omit each required field one at a time
   - Send completely empty body
   - Send empty JSON object `{}`
   ```bash
   curl -s -w "\n%{http_code}" -X POST ${BASE_URL}/v1/agents/code-reasoning/chat/completions \
     -H "Content-Type: application/json" \
     -d '{}'
   ```

   **Missing or invalid authentication:**
   - No auth header
   - Invalid token
   - Expired token
   ```bash
   curl -s -w "\n%{http_code}" -X POST ${BASE_URL}/v1/agents/code-reasoning/chat/completions \
     -H "Authorization: Bearer invalid-token" \
     -H "Content-Type: application/json" \
     -d '{"messages": [{"role": "user", "content": "test"}]}'
   ```

   **Wrong HTTP method:**
   - GET on a POST-only endpoint
   - DELETE on a GET-only endpoint
   ```bash
   curl -s -w "\n%{http_code}" -X GET ${BASE_URL}/v1/agents/code-reasoning/chat/completions
   ```

   **Boundary values:**
   - Empty string `""`
   - Very long string (10,000+ characters)
   - Zero, negative numbers, MAX_INT
   - Empty array `[]`
   - Null values where not allowed

3. **Execute each test case.** Run the curl and capture status code + response body.

4. **Validate proper error responses.** For each test, verify:
   - **Status code is 4xx** (not 500): 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 405 Method Not Allowed, 422 Unprocessable Entity
   - **Error message is descriptive**: tells the caller what went wrong
   - **No stack traces or internal details** leaked in the response
   - **No server crash**: the server continues to respond after the error

5. **Generate the negative test report.**

   ```
   ## Negative Test Results

   | # | Category        | Test Case             | Expected | Actual | Result |
   |---|----------------|-----------------------|----------|--------|--------|
   | 1 | Invalid input  | messages as string    | 422      | 422    | PASS   |
   | 2 | Missing field  | empty body            | 422      | 500    | FAIL   |
   | 3 | Wrong method   | GET on POST endpoint  | 405      | 405    | PASS   |
   | 4 | Auth           | no auth header        | 401      | 200    | FAIL   |

   ## Issues Found
   | Issue                    | Severity | Endpoint          | Details                        |
   |-------------------------|----------|-------------------|--------------------------------|
   | Missing input validation | HIGH     | /v1/agents/.../chat | Empty body returns 500 not 422 |
   | Missing auth check       | CRITICAL | /v1/agents/.../chat | No auth returns 200            |
   ```

6. **Prioritize findings.** Rate each issue:
   - **CRITICAL**: Security issue (auth bypass, data leak, injection)
   - **HIGH**: Server crash (500) on bad input — should be 4xx
   - **MEDIUM**: Wrong error code (400 vs 422) or unclear error message
   - **LOW**: Missing error detail or inconsistent format

## Security Testing

Beyond input validation, test for common security vulnerabilities:

| Attack Vector | Test | Expected Response | Severity if Fails |
|--------------|------|-------------------|-------------------|
| **SQL Injection** | `' OR 1=1 --` in string fields | 400/422 with validation error, NOT a DB error | CRITICAL |
| **NoSQL Injection** | `{"$gt": ""}` in JSON fields | 400/422, not a query result leak | CRITICAL |
| **Command Injection** | `; ls -la` or `$(whoami)` in string fields | 400/422, no command execution | CRITICAL |
| **Path Traversal** | `../../etc/passwd` in file path params | 400/404, not file contents | CRITICAL |
| **XSS** | `<script>alert(1)</script>` in input fields | Input sanitized or escaped in response | HIGH |
| **Auth bypass** | Request without token, with expired token, with token for wrong user | 401/403, never 200 with data | CRITICAL |
| **IDOR** | Request resource belonging to another user using their ID | 403 or 404, never the other user's data | CRITICAL |
| **Mass assignment** | Send extra fields not in the API spec (e.g., `"role": "admin"`) | Extra fields ignored, not applied | HIGH |

For each security test, the goal is to verify the application REJECTS the attack, not that the attack works.

## Chaos Engineering Hints

For more thorough negative testing, consider these failure injection scenarios:

| Scenario | How to Simulate | What to Observe |
|----------|----------------|-----------------|
| **Slow response** | Add artificial delay to requests (large payload) | Does the server timeout gracefully or hang? |
| **Concurrent abuse** | Send 50+ identical requests in parallel | Does the server crash, produce duplicates, or handle gracefully? |
| **Oversized payload** | Send a 10MB+ JSON body | Does the server return 413 (Payload Too Large) or OOM? |
| **Malformed encoding** | Send invalid UTF-8, wrong Content-Type | Does the server return 400 or crash? |
| **Connection drop** | Start a request and disconnect mid-stream | Does the server clean up resources or leak connections? |

These are NOT required for every test run, but should be performed before major releases.

## Risk Assessment

| Risk | Signs | Mitigation |
|------|-------|------------|
| **False security** | All negative tests pass but real attacks use different vectors | Use OWASP Top 10 as a checklist, not just the tests above |
| **Over-restrictive validation** | Valid inputs rejected (false positives) | Test valid edge cases too: unicode names, long but valid emails, etc. |
| **Error information leakage** | 500 errors include stack traces, DB schema, or internal paths | Every error response should be checked for information disclosure |
| **Inconsistent error handling** | Some endpoints return structured errors, others return raw strings | Flag inconsistencies — consumers need predictable error formats |

## Definition of Done

- [ ] All input validation paths tested (wrong type, missing field, out of range, empty, null)
- [ ] Authentication and authorization tested (no token, bad token, wrong role)
- [ ] Security attack vectors tested (injection, path traversal, IDOR at minimum)
- [ ] Every 500 response flagged as a bug (bad input should NEVER cause 500)
- [ ] No stack traces or internal details leaked in error responses
- [ ] Error response format is consistent across all endpoints
- [ ] Findings prioritized (CRITICAL > HIGH > MEDIUM > LOW) with fix recommendations
- [ ] Server stability verified — server continues to respond normally after all negative tests
