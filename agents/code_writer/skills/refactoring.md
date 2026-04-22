---
name: refactoring
description: Code refactoring patterns — extract, rename, move, introduce interface, apply design patterns
---

## Before You Start

Identify the refactoring goal. The user should specify one or more of:
- **Extract method/class** — break apart large methods or God classes
- **Rename** — rename class, method, or variable across the entire codebase
- **Move** — relocate class to a different package
- **Introduce interface** — extract interface for testability or abstraction
- **Apply pattern** — Strategy, Factory, Builder, Observer, etc.

Run the existing test suite first to establish a green baseline. If tests fail before refactoring, stop and inform the user.

## Workflow

### 1. Establish Green Baseline

```bash
mvn test -q  # or: gradle test / poetry run pytest
```

If tests fail, report the failures. Do NOT refactor code with a failing test suite.

### 2. Extract Method

When a method exceeds ~20 lines or has multiple logical blocks:
- Identify a self-contained block (has clear input/output)
- Extract to a private method with a descriptive name
- Parameters = variables the block reads; return = variables the block writes
- Preserve exact behavior — no logic changes
- Run tests after extraction

### 3. Extract Class

When a class has multiple unrelated responsibilities (God class):
- List the class's responsibilities (group methods by what they do)
- Create a new class for each secondary responsibility
- Move methods + their fields to the new class
- Inject the new class into the original via constructor injection
- Update all callers to use the new class where appropriate
- Run tests after each class extraction

### 4. Rename (Class / Method / Variable)

- Find ALL references across the entire codebase:
  - Java: imports, method calls, annotations, config files, XML/YAML references
  - Python: imports, function calls, string references, config files
- Rename the declaration
- Rename every reference (imports, usages, tests, configs, docs)
- Run tests to verify nothing is missed

### 5. Move (Relocate Class)

- Create the target package directory if it does not exist
- Move the file to the new package
- Update the `package` declaration in the file
- Update ALL imports across the codebase that reference this class
- Update any config files, XML, or YAML that reference the old path
- Run tests to verify

### 6. Introduce Interface

When a concrete class should be swapped or mocked:
- Extract a public interface with the class's public methods
- Name it descriptively (e.g., `PaymentGateway` interface, `StripePaymentGateway` impl)
- Update the existing class to `implements` the interface
- Change all injection points to depend on the interface, not the concrete class
- Update tests: mock the interface instead of the concrete class
- Run tests to verify

### 7. Apply Design Pattern

Choose the appropriate pattern:
- **Strategy**: Replace conditional logic (if/switch on type) with a strategy interface + implementations. Register strategies in a Map or use Spring's `List<Strategy>` injection.
- **Factory**: Replace direct `new` calls with a factory method/class when object creation is complex or varies by input.
- **Builder**: Replace constructors with many parameters (>4) with a builder. Use Lombok `@Builder` in Java or manual builder.
- **Observer**: Replace direct method calls for notifications with an event system. Use Spring's `ApplicationEventPublisher` in Spring apps.

For each pattern:
- Explain the pattern and why it fits
- Implement incrementally (one step at a time)
- Run tests after each step

### 8. Final Verification

```bash
mvn test -q  # or: gradle test / poetry run pytest
```

- All tests pass (same count as baseline — no tests removed)
- No behavior changes — refactoring is structure-only
- Code compiles cleanly with no warnings from the refactored area

## Definition of Done

- Green test suite before AND after refactoring (same test count)
- Zero behavior changes — only structural improvements
- All references updated (imports, configs, tests, docs)
- Each refactoring step was individually tested (not batched)
- No dead code left behind (unused imports, unreachable methods)
