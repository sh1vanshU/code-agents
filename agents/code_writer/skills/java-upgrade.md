---
name: java-upgrade
description: Java version upgrade — deprecated API replacement, new feature enablement, build config updates
---

## Before You Start

Determine the current and target Java versions:
- Read `pom.xml` (`<java.version>`, `<maven.compiler.source>`, `<maven.compiler.release>`) or `build.gradle` (`sourceCompatibility`, `toolchain`)
- Confirm the target version with the user (e.g., Java 17 -> 21)
- Review the Java release notes for every version in the upgrade path

Run the full test suite on the current version to establish a green baseline.

## Workflow

### 1. Update Build Configuration

**Maven (`pom.xml`):**
```xml
<properties>
    <java.version>21</java.version>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```
Update `maven-compiler-plugin` if explicitly configured:
```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>21</release>
    </configuration>
</plugin>
```

**Gradle (`build.gradle`):**
```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

### 2. Replace Deprecated and Removed APIs

Scan the codebase for each category and replace:

| Removed/Deprecated | Replacement | Since |
|---|---|---|
| `javax.*` packages | `jakarta.*` (if using Jakarta EE 9+) | Java 17+ / Jakarta EE 9 |
| `SecurityManager` | Remove usage, use modern security mechanisms | Java 17 (deprecated), 24 (removed) |
| `Finalization` (`finalize()`) | `Cleaner`, `try-with-resources` | Java 18 (deprecated) |
| `Thread.stop()`, `Thread.suspend()` | Cooperative interruption (`Thread.interrupt()`) | Java 20 (removed) |
| `Applet` API | Remove (no replacement) | Java 17 (removed) |
| `RMI Activation` | Remove or migrate to modern RPC | Java 17 (removed) |
| `Nashorn` JS engine | GraalJS or other JS runtime | Java 15 (removed) |

Run after replacements:
```bash
mvn clean compile -q
```
Fix all compilation errors before proceeding.

### 3. Enable New Language Features

Progressively adopt features available in the target version:

**Java 17+ features:**
- `sealed` classes/interfaces for restricted hierarchies
- Pattern matching for `instanceof`: `if (obj instanceof String s)`
- Text blocks: `"""multi-line"""`
- Records for immutable data carriers (DTOs, value objects)

**Java 21+ features:**
- Record patterns: `if (obj instanceof Point(int x, int y))`
- Pattern matching for `switch`: `case Integer i when i > 0 ->`
- Sequenced collections: `list.getFirst()`, `list.getLast()`, `list.reversed()`
- Virtual threads: `Thread.ofVirtual().start(task)` for I/O-bound workloads
- String templates (preview): evaluate based on project preview policy

Adoption approach:
- Start with new code and modified code (do not rewrite working code just to use new features)
- Prioritize records for DTOs and pattern matching for type checks
- Use virtual threads only where I/O-bound (HTTP clients, DB calls)

### 4. Update CI/CD and Docker

**Dockerfile:**
```dockerfile
FROM eclipse-temurin:21-jre-alpine  # or: amazoncorretto:21-alpine
```

**CI pipeline (Jenkinsfile / GitHub Actions):**
- Update `JAVA_HOME` or tool configuration to target version
- Update any JDK installation steps

**IDE settings** (if committed):
- `.idea/misc.xml`: update `languageLevel`
- `.vscode/settings.json`: update `java.configuration.runtimes`

### 5. Update Dependencies

Some libraries require version bumps for newer Java support:
- Lombok: ensure version supports target Java
- MapStruct: ensure annotation processor works
- Mockito / ByteBuddy: must support target Java bytecode
- ASM: used by many frameworks, must support target class format

```bash
mvn versions:display-dependency-updates -q
```

### 6. Run Full Test Suite

```bash
mvn clean test -q  # or: gradle clean test
```

Fix any failures:
- **Reflection-related**: add `--add-opens` to surefire/failsafe argLine if needed (prefer fixing code over adding opens)
- **Serialization**: update `serialVersionUID` if class structure changed
- **Deprecation warnings**: fix or suppress with justification

### 7. Verify Application Startup

```bash
mvn spring-boot:run  # or: gradle bootRun
# Check health endpoint
curl -s http://localhost:8080/actuator/health
```

## Definition of Done

- Build config updated to target Java version
- All deprecated/removed API usages replaced
- New language features enabled in modified code
- Dockerfile and CI config updated
- Dependencies compatible with target Java version
- Full test suite green
- Application starts and health endpoint responds
