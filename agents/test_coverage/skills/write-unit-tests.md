---
name: write-unit-tests
description: Write JUnit 5 unit tests with Mockito and AssertJ for uncovered methods
---

## Workflow

1. **Read the source class under test.** Identify every public and package-private method. List which methods have existing tests and which do not. Focus on untested methods first.

2. **Analyze dependencies.** For each dependency (constructor params, field injections):
   - Mark as mockable (`@Mock`) if it is a service, repository, or client
   - Mark as real if it is a value object, DTO, or simple utility
   - Identify static method calls that need `mockStatic` or refactoring

3. **Create the test class skeleton.**
   ```java
   @ExtendWith(MockitoExtension.class)
   class RefundServiceTest {

       @Mock private PaymentRepository paymentRepository;
       @Mock private NotificationService notificationService;
       @InjectMocks private RefundService refundService;
   ```
   Use `@InjectMocks` for the class under test. Never use `@SpringBootTest` for unit tests.

4. **Write test methods following the `should_returnX_when_Y` naming pattern.** Every test gets a `@DisplayName` with a human-readable sentence:
   ```java
   @Test
   @DisplayName("should return full refund when order is within 24 hours")
   void should_returnFullRefund_when_orderWithin24Hours() {
       // given
       // when
       // then
   }
   ```

5. **Cover these scenarios for each method:**
   - **Happy path** — Normal input, expected output
   - **Null/empty inputs** — Null arguments, empty collections, blank strings
   - **Boundary values** — Zero, max int, empty list vs single element, exact threshold
   - **Exception paths** — Expected exceptions with `assertThatThrownBy`
   - **Concurrent access** — If the method uses shared state, test with multiple threads

6. **Use `@ParameterizedTest` for methods with multiple valid input combinations:**
   ```java
   @ParameterizedTest
   @CsvSource({
       "100.00, 24, 100.00",
       "100.00, 48, 50.00",
       "100.00, 72, 0.00"
   })
   @DisplayName("should calculate correct refund amount based on hours since order")
   void should_calculateRefund_when_givenHoursAndAmount(
           BigDecimal amount, int hours, BigDecimal expected) {
       assertThat(refundService.calculate(amount, hours)).isEqualByComparingTo(expected);
   }
   ```

7. **Use test data builders instead of raw constructors.** Create builder methods or use the Builder pattern for complex objects:
   ```java
   private Order anOrder() {
       return Order.builder()
           .id(UUID.randomUUID())
           .amount(new BigDecimal("100.00"))
           .createdAt(Instant.now().minus(Duration.ofHours(12)))
           .status(OrderStatus.CONFIRMED)
           .build();
   }
   ```

8. **Use AssertJ for all assertions.** Never use raw JUnit `assertEquals`:
   ```java
   assertThat(result).isNotNull();
   assertThat(result.getAmount()).isEqualByComparingTo("100.00");
   assertThat(result.getErrors()).isEmpty();
   assertThatThrownBy(() -> service.process(null))
       .isInstanceOf(IllegalArgumentException.class)
       .hasMessageContaining("must not be null");
   ```

9. **Verify mock interactions where behavior matters:**
   ```java
   verify(paymentRepository).save(any(Payment.class));
   verify(notificationService, never()).sendAlert(any());
   verifyNoMoreInteractions(paymentRepository);
   ```

10. **Run the tests and verify they pass.**
    ```bash
    mvn test -pl <module> -Dtest=RefundServiceTest -q
    ```
    If any test fails, read the failure output, fix the test, and re-run. Do not leave failing tests.

11. **Re-check coverage for the class under test.**
    ```bash
    mvn test jacoco:report -pl <module> -Dtest=RefundServiceTest -q
    ```
    Parse the JaCoCo report for the specific class. If coverage is still below the target, identify remaining uncovered lines and write additional tests. Iterate until the target is met.

12. **Final review.** Ensure:
    - No test depends on execution order
    - No test modifies shared state without cleanup
    - All mocks are verified or explicitly ignored
    - Test names clearly describe the scenario
    - No production code was modified to make tests pass (unless fixing a genuine bug)
