---
name: spring-upgrade
description: Spring Boot upgrade — migration guide, config changes, deprecated API replacement, dependency alignment
---

## Before You Start

Determine the current and target Spring Boot versions:
- Read `pom.xml` (`<parent>` Spring Boot starter version) or `build.gradle` (Spring Boot plugin version)
- Plan the upgrade path in incremental steps (e.g., 2.7 -> 3.0 -> 3.2 -> 3.5)
- Never skip a major version boundary — upgrade through each major version sequentially

Run the full test suite on the current version to establish a green baseline.

## Workflow

### 1. Upgrade One Version Step at a Time

For each step in the upgrade path, apply changes, fix errors, and get tests green before moving to the next step. Example path:
- Spring Boot 2.7.x -> 3.0.x (major: Jakarta EE, security rewrite)
- Spring Boot 3.0.x -> 3.2.x (minor: property renames, new features)
- Spring Boot 3.2.x -> 3.5.x (minor: further refinements)

### 2. Update Version in Build Config

**Maven:**
```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
</parent>
```

**Gradle:**
```groovy
plugins {
    id 'org.springframework.boot' version '3.5.0'
}
```

### 3. Handle Spring Boot 3.0 Migration (if crossing 2.x -> 3.x)

This is the largest breaking change. Key migrations:

**Jakarta EE namespace:**
```
javax.servlet.*    -> jakarta.servlet.*
javax.persistence.* -> jakarta.persistence.*
javax.validation.*  -> jakarta.validation.*
javax.annotation.*  -> jakarta.annotation.*
javax.transaction.* -> jakarta.transaction.*
```
Find and replace across entire codebase including test files.

**Security configuration:**
```java
// REMOVED in Spring Boot 3.0
// extends WebSecurityConfigurerAdapter

// REPLACEMENT: SecurityFilterChain bean
@Bean
public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
    return http.build();
}
```

**Property renames:**
| Old Property | New Property |
|---|---|
| `spring.redis.*` | `spring.data.redis.*` |
| `spring.elasticsearch.*` | `spring.elasticsearch.uris` (restructured) |
| `spring.datasource.username` | Still valid, but Flyway/Liquibase have own prefixes |
| `server.max-http-header-size` | `server.max-http-request-header-size` |
| `spring.mvc.throw-exception-if-no-handler-found` | Removed (now default behavior) |

**Auto-configuration:**
- `META-INF/spring.factories` -> `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`
- `@ConstructorBinding` no longer needed on single-constructor `@ConfigurationProperties`

### 4. Handle Spring Boot 3.2+ Changes

- **RestClient**: new synchronous HTTP client (alternative to RestTemplate)
- **JdbcClient**: new fluent JDBC API
- **Observability**: Micrometer Observation API is the default
- **Virtual threads**: `spring.threads.virtual.enabled=true` to enable
- **SSL bundles**: `spring.ssl.bundle.*` for centralized SSL config
- **Property binding**: stricter validation on `@ConfigurationProperties`

### 5. Update Dependencies Managed by Spring Boot BOM

Dependencies that follow Spring Boot's BOM update automatically. But verify:
- **Flyway**: major version may change (Flyway 10+ with Spring Boot 3.2+)
- **Hibernate**: 6.x with Spring Boot 3.0+ (HQL changes, type system changes)
- **Jackson**: verify custom serializers/deserializers still work
- **Lombok**: ensure compatible version
- **Springdoc/OpenAPI**: springdoc v1 -> springdoc v2 for Spring Boot 3.x

For dependencies NOT in the BOM:
```bash
mvn versions:display-dependency-updates -q
```

### 6. Fix Compilation Errors

```bash
mvn clean compile -q
```

Common fixes:
- Import replacements (`javax` -> `jakarta`)
- Removed method replacements (check Spring Boot migration guide)
- Constructor changes in Spring Security filters
- Hibernate type mapping changes

### 7. Fix Test Failures

```bash
mvn test -q
```

Common test fixes:
- `@MockBean` deprecated in 3.4+ -> use `@MockitoBean`
- `TestRestTemplate` behavior changes
- Security test configuration updates
- `@AutoConfigureMockMvc` adjustments

### 8. Verify Application Startup and Health

```bash
mvn spring-boot:run
# Verify
curl -s http://localhost:8080/actuator/health
curl -s http://localhost:8080/actuator/info
```

Check:
- Application starts without errors
- Health endpoint returns UP
- Actuator endpoints are accessible (Actuator path changes in 3.x)
- All REST endpoints respond correctly

### 9. Repeat for Next Version Step

Go back to step 2 for the next version in the upgrade path. Do not skip steps.

## Definition of Done

- Spring Boot version updated to target
- All `javax.*` -> `jakarta.*` migrations complete (if applicable)
- Security configuration uses `SecurityFilterChain` bean (no `WebSecurityConfigurerAdapter`)
- Property names updated to current conventions
- All dependencies aligned with Spring Boot BOM
- Full test suite green
- Application starts and health endpoint responds UP
- Each upgrade step was individually compiled and tested
