---
name: targeted-regression
description: Run regression only on areas affected by code changes — faster than full suite
---

## Before You Start
- Code changes committed or staged
- Test naming convention follows: Foo.java → FooTest.java

## Workflow

1. **Get changed files:**
   ```bash
   curl -sS "${CODE_AGENTS_PUBLIC_BASE_URL}/git/diff?base=main&head=HEAD"
   ```

2. **Map changed files to test files:**
   - src/main/java/com/example/PaymentService.java → src/test/java/com/example/PaymentServiceTest.java
   - Also include tests that import the changed class (dependency mapping)

3. **Run mapped tests only:**
   ```bash
   curl -sS -X POST "${CODE_AGENTS_PUBLIC_BASE_URL}/testing/run" -H "Content-Type: application/json" -d '{"test_command": "mvn test -pl module -Dtest=PaymentServiceTest,OrderServiceTest"}'
   ```

4. **If any fail:** Run full suite to check cascading impact — a change in PaymentService might break OrderController tests.

5. **Report:** Which change caused which failure, impact radius (how many tests affected).

## Definition of Done
- All tests related to changed code pass
- No cascading failures in dependent modules
