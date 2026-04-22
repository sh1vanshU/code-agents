---
name: test-plan
description: Create a test plan for a feature with test cases and scenarios
---

## Workflow

1. **Understand the feature.** Read the feature requirements, relevant code, and any design documents. Identify:
   - What the feature does (user-facing behavior)
   - Which components are involved
   - External dependencies (APIs, databases, queues)
   - Edge cases and failure modes

2. **Define test categories.** Organize tests into:
   - **Unit tests:** individual functions and methods
   - **Integration tests:** component interactions, API endpoints
   - **Contract tests:** API request/response schemas
   - **Error handling tests:** failure paths, timeouts, retries
   - **Data validation tests:** input sanitization, boundary values

3. **Write test cases for the happy path.** For each user flow:
   ```
   TC-001: User creates a payment order
   - Input: valid merchant_id, amount, currency
   - Expected: order created with status PENDING, order_id returned
   - Verify: database record exists, response schema matches
   ```

4. **Write test cases for edge cases:**
   - Empty or null inputs
   - Maximum/minimum values
   - Duplicate requests (idempotency)
   - Concurrent access
   - Unicode and special characters

5. **Write test cases for error paths:**
   - Invalid input (wrong type, missing required fields)
   - Authentication failure
   - Downstream service timeout
   - Database connection failure
   - Rate limiting

6. **Define mock requirements.** For each external dependency, specify:
   - What to mock
   - What the mock should return (success and failure scenarios)
   - How to verify the mock was called correctly

7. **Estimate coverage targets:**
   - Line coverage target (e.g., 90%)
   - Branch coverage target (e.g., 80%)
   - Specific files that must reach 100%

8. **Present the test plan** as a structured document with test case IDs, descriptions, inputs, expected outputs, and priority levels.
