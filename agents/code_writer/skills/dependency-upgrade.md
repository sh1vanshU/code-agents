---
name: dependency-upgrade
description: Library dependency upgrades — scan outdated deps, check CVEs, upgrade with breaking change fixes
---

## Before You Start

Identify the build tool and dependency file:
- **Maven**: `pom.xml`
- **Gradle**: `build.gradle` / `build.gradle.kts`
- **Python**: `pyproject.toml` / `requirements.txt`
- **Node**: `package.json`

Run the full test suite to establish a green baseline before any upgrades.

## Workflow

### 1. Scan for Outdated Dependencies

**Maven:**
```bash
mvn versions:display-dependency-updates -q
mvn versions:display-plugin-updates -q
```

**Gradle:**
```bash
gradle dependencyUpdates
```

**Python:**
```bash
pip list --outdated
```

**Node:**
```bash
npm outdated
```

Record every outdated dependency with current version, latest version, and version gap.

### 2. Check for Security Vulnerabilities

**Maven:**
```bash
mvn org.owasp:dependency-check-maven:check
```

**Gradle:**
```bash
gradle dependencyCheckAnalyze
```

**Python:**
```bash
pip-audit
```

**Node:**
```bash
npm audit
```

Prioritize CVE fixes — these go first regardless of breaking change risk.

### 3. Plan Upgrade Order

Sort dependencies by risk (lowest first):
1. **Patch versions** (1.2.3 -> 1.2.5): bug fixes only, safe
2. **Minor versions** (1.2.3 -> 1.4.0): new features, backward compatible
3. **Major versions** (1.2.3 -> 2.0.0): breaking changes expected
4. **Framework-coupled** (Spring Boot BOM, etc.): upgrade with framework

For each dependency, before upgrading:
- Read the CHANGELOG or release notes for every version in the gap
- Identify breaking changes, renamed classes/methods, removed APIs
- Check if the library has a migration guide

### 4. Upgrade One Dependency at a Time

For each dependency:

**a. Update the version:**
```xml
<!-- Maven -->
<dependency>
    <groupId>com.example</groupId>
    <artifactId>library</artifactId>
    <version>2.0.0</version>  <!-- was 1.5.0 -->
</dependency>
```

**b. Compile:**
```bash
mvn clean compile -q
```

**c. Fix compilation errors:**
- Replace removed classes/methods with their replacements
- Update import statements if packages changed
- Adjust API calls if method signatures changed

**d. Run tests:**
```bash
mvn test -q
```

**e. Fix test failures:**
- Update test code for new API behavior
- Adjust assertions if return types changed
- Update mocks if interfaces changed

**f. Move to the next dependency** only after tests are green.

### 5. Handle Transitive Dependency Conflicts

After upgrading, check for version conflicts:
```bash
mvn dependency:tree -q | grep -i conflict
```

Resolve by:
- Excluding the older transitive version
- Adding an explicit version in `<dependencyManagement>`
- Using BOM imports to align versions

### 6. Generate Upgrade Report

Summarize what was done:
```
Dependency Upgrade Report
=========================
Upgraded: X libraries
Security fixes: Y CVEs resolved
Breaking changes fixed: Z
Skipped: N (reason for each)

Details:
- library-a: 1.2.0 -> 2.0.0 (breaking: renamed FooClient -> FooService)
- library-b: 3.1.0 -> 3.1.5 (patch: CVE-2024-XXXXX fixed)
- library-c: skipped (requires Java 21, currently on 17)
```

### 7. Final Verification

```bash
mvn clean test -q  # or: gradle clean test
```

All tests must pass. Run the application and verify startup:
```bash
mvn spring-boot:run  # or equivalent
curl -s http://localhost:8080/actuator/health
```

## Definition of Done

- All patch/minor updates applied
- All CVE-affected dependencies upgraded
- Major version upgrades applied with breaking changes fixed
- No transitive dependency conflicts
- Full test suite green
- Application starts and health endpoint responds
- Upgrade report generated listing all changes
