---
name: java-spring
description: Java 21+ and Spring Boot coding standards, patterns, and best practices
---

## Java 21+ Standards

### Language Features (prefer modern over legacy)

| Modern (Use This) | Legacy (Avoid) |
|---|---|
| `record Point(int x, int y) {}` | POJO with getters/setters/equals/hashCode |
| `sealed interface Shape permits Circle, Rect` | Open interface hierarchies |
| `case Integer i when i > 0 ->` (pattern matching switch) | `if/else instanceof` chains |
| `obj instanceof String s` (pattern matching) | `(String) obj` manual cast |
| `Thread.ofVirtual().start(task)` (virtual threads) | `new Thread(task).start()` or thread pools for I/O |
| `SequencedCollection`, `getFirst()`, `getLast()` | `list.get(0)`, `list.get(list.size()-1)` |
| `"""multi-line"""` text blocks | String concatenation for SQL/JSON |
| `var list = new ArrayList<String>()` | Full type on both sides |
| `List.of()`, `Map.of()` immutable factories | `Collections.unmodifiableList(new ArrayList<>())` |
| `Optional.ofNullable(x).orElseThrow()` | `if (x == null) throw` |
| `Stream.toList()` (Java 16+) | `Collectors.toList()` |

### Naming Conventions
- Classes: `PascalCase` — `PaymentService`, `OrderRepository`
- Methods: `camelCase` — `processPayment()`, `findByUserId()`
- Constants: `UPPER_SNAKE` — `MAX_RETRY_COUNT`
- Packages: `lowercase` — `com.acme.payments.service`
- DTOs: suffix with `Request`, `Response`, `Dto` — `CreateOrderRequest`
- Entities: no suffix — `Order`, `Payment`, `User`

## Spring Boot Standards

### Dependency Injection
```java
// ✅ Constructor injection (preferred — immutable, testable)
@Service
@RequiredArgsConstructor
public class PaymentService {
    private final PaymentRepository paymentRepo;
    private final NotificationService notificationService;
}

// ❌ Field injection (untestable, hidden dependencies)
@Service
public class PaymentService {
    @Autowired private PaymentRepository paymentRepo;
}
```

### REST Controllers
```java
@RestController
@RequestMapping("/api/v1/payments")
@RequiredArgsConstructor
@Validated
public class PaymentController {
    private final PaymentService paymentService;

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public PaymentResponse createPayment(@Valid @RequestBody CreatePaymentRequest request) {
        return paymentService.create(request);
    }

    @GetMapping("/{id}")
    public PaymentResponse getPayment(@PathVariable UUID id) {
        return paymentService.findById(id);
    }
}
```

### Exception Handling
```java
@RestControllerAdvice
public class GlobalExceptionHandler {
    @ExceptionHandler(EntityNotFoundException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    public ErrorResponse handleNotFound(EntityNotFoundException ex) {
        return new ErrorResponse("NOT_FOUND", ex.getMessage());
    }

    @ExceptionHandler(ConstraintViolationException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ErrorResponse handleValidation(ConstraintViolationException ex) {
        return new ErrorResponse("VALIDATION_ERROR", ex.getMessage());
    }
}
```

### Transactions
```java
// ✅ Read-only where applicable (performance optimization)
@Transactional(readOnly = true)
public List<Payment> findByUserId(UUID userId) { ... }

// ✅ Write transaction with proper isolation
@Transactional(isolation = Isolation.READ_COMMITTED)
public Payment processPayment(CreatePaymentRequest req) { ... }

// ❌ Never on private methods (Spring proxy can't intercept)
// ❌ Never catch exceptions inside @Transactional (breaks rollback)
```

### Configuration
```java
// ✅ Type-safe config with @ConfigurationProperties
@ConfigurationProperties(prefix = "payment")
public record PaymentConfig(
    String gatewayUrl,
    Duration timeout,
    int maxRetries
) {}

// ❌ @Value scattered across services
```

### Profiles
- `application.yml` — shared defaults
- `application-dev.yml` — dev overrides
- `application-staging.yml` — staging
- `application-prod.yml` — prod (secrets from vault/env, never in file)

## Spring Security

```java
@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.ignoringRequestMatchers("/api/**"))
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

## Testing

```java
// Controller test — lightweight, no server
@WebMvcTest(PaymentController.class)
class PaymentControllerTest {
    @Autowired MockMvc mockMvc;
    @MockitoBean PaymentService paymentService;

    @Test
    void createPayment_returns201() throws Exception {
        mockMvc.perform(post("/api/v1/payments")
            .contentType(APPLICATION_JSON)
            .content("""
                {"amount": 100, "currency": "INR"}
                """))
            .andExpect(status().isCreated());
    }
}

// Repository test — real DB via Testcontainers
@DataJpaTest
@Testcontainers
class PaymentRepositoryTest {
    @Container
    static PostgreSQLContainer<?> pg = new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void props(DynamicPropertyRegistry r) {
        r.add("spring.datasource.url", pg::getJdbcUrl);
    }
}

// Integration test — full context
@SpringBootTest(webEnvironment = RANDOM_PORT)
class PaymentIntegrationTest {
    @Autowired TestRestTemplate restTemplate;
}
```

## Code Style

- **Lombok**: Use `@RequiredArgsConstructor`, `@Getter`, `@Builder`, `@Slf4j`. Avoid `@Data` on entities (equals/hashCode issues with JPA).
- **DTO ↔ Entity mapping**: Use MapStruct or manual mapper class. Never expose entities directly in API responses.
- **Logging**: SLF4J with structured context — `log.info("Payment processed", kv("orderId", id), kv("amount", amt))`. Never log sensitive data (PII, tokens, passwords).
- **Null safety**: Use `Optional` for return types, `@NonNull`/`@Nullable` annotations, never return `null` from public methods.

## Workflow

1. **Check project setup**: Verify Java version (`java -version` → 21+), Spring Boot version (`pom.xml` → 3.2+), key dependencies.
2. **Follow the standards above** when writing any Java/Spring code.
3. **Validate**: Run `mvn compile` to check compilation, `mvn test` for tests.
