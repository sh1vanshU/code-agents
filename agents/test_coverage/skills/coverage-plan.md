---
name: coverage-plan
description: Build a prioritized plan to reach target coverage with effort estimates and test pyramid ratios
---

## Before You Start

- Confirm the target coverage threshold with the user (default: 80%).
- Confirm the project uses Maven + JaCoCo. If Gradle or another build tool, adapt commands accordingly.
- Identify the source root (default: `src/main/java`) and test root (default: `src/test/java`).
- Check if a previous coverage plan exists and whether this is a fresh plan or an update.

## Workflow

1. **Run the test suite with JaCoCo coverage.**
   ```bash
   mvn clean test jacoco:report -q
   ```
   If tests fail, stop and report failures. Coverage planning requires a green build.

2. **Parse the JaCoCo XML report.**
   Read `target/site/jacoco/jacoco.xml` and extract per-class metrics:
   - Line coverage (covered / missed)
   - Branch coverage (covered / missed)
   - Method coverage (covered / missed)

3. **List ALL classes with coverage below the target threshold.** Sort by coverage gap descending (worst first):
   ```
   Class                                  Lines    Branches  Gap
   com.app.payment.RefundService          23%      10%       -70%
   com.app.auth.TokenValidator            41%      25%       -55%
   com.app.order.OrderProcessor           55%      48%       -32%
   com.app.util.DateHelper                72%      65%       -15%
   ```

4. **For each under-covered class, identify specific gaps:**
   - Uncovered methods (list method signatures)
   - Uncovered branches (if/else, switch, try/catch paths)
   - Uncovered line ranges with descriptions of what they do

5. **Categorize each gap by test type needed:**
   - **Unit test** — Pure logic, no external deps, mockable collaborators
   - **Integration test** — DB access, Spring context, external service calls
   - **E2E test** — Full request flow, multi-service interaction, message queue consumption

6. **Estimate effort for each class:**
   - **S (Small)** — 1-3 test methods, < 1 hour. Simple logic, few branches.
   - **M (Medium)** — 4-10 test methods, 1-3 hours. Multiple paths, some mocking.
   - **L (Large)** — 10+ test methods, 3+ hours. Complex logic, many dependencies, state setup.

7. **Prioritize by risk.** Payment, auth, and financial transaction classes come first. Then core business logic. Then utilities and helpers:
   - **P0 (Critical)** — Payment processing, auth/security, financial calculations
   - **P1 (High)** — Core business logic, order management, user operations
   - **P2 (Medium)** — API controllers, data transformations, validators
   - **P3 (Low)** — Utilities, logging, configuration, DTOs

8. **Calculate test pyramid ratios.** Count existing tests by type and compare to ideal:
   ```
   Test Type       Current   Target    Ideal Ratio
   Unit            45        120       70%
   Integration     30        40        20%
   E2E             15        18        10%
   Total           90        178
   ```

9. **Output the structured coverage plan:**
   ```
   Coverage Plan
   Current Overall: 62%    Target: 80%    Gap: -18%

   Priority  Class                        Coverage  Type         Effort  Tests Needed
   P0        RefundService                23%       Unit+Integ   L       15
   P0        TokenValidator               41%       Unit         M       8
   P1        OrderProcessor               55%       Unit+E2E     M       7
   P1        InventoryService             60%       Integration  M       6
   P2        UserController               68%       Unit         S       3
   P3        DateHelper                   72%       Unit         S       2

   Pyramid: 70% unit / 20% integration / 10% E2E
   Estimated total: 41 new test methods
   ```

10. **Recommend execution order.** Start with P0 unit tests (fastest ROI), then P0 integration, then P1 unit, and so on. Delegate to `[SKILL:write-unit-tests]`, `[SKILL:write-integration-tests]`, or `[SKILL:write-e2e-tests]` as appropriate.

## Definition of Done

- Every class below the target threshold is listed with its coverage gap.
- Each gap has a test type, effort estimate, and priority.
- Test pyramid ratios are calculated (current vs target).
- The plan is ordered by priority and actionable — a developer can pick up any row and start writing tests.
- Running the plan to completion would bring overall coverage to or above the target threshold.
