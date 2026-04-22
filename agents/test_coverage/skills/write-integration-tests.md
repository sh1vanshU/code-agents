---
name: write-integration-tests
description: Write Spring Boot integration tests with Testcontainers, MockMvc, and real database verification
---

## Workflow

1. **Identify the integration boundary.** Determine what is being integrated:
   - **Controller layer** — Use `@WebMvcTest` with `MockMvc`
   - **Repository layer** — Use `@DataJpaTest` with Testcontainers
   - **Full slice** — Use `@SpringBootTest` with `@AutoConfigureMockMvc`
   Choose the narrowest slice that covers the integration point.

2. **Set up Testcontainers for real database access.** Do not use H2 for integration tests — use the same database engine as production:
   ```java
   @Testcontainers
   @DataJpaTest
   @AutoConfigureTestDatabase(replace = Replace.NONE)
   class OrderRepositoryIntegrationTest {

       @Container
       static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:15")
           .withDatabaseName("testdb")
           .withUsername("test")
           .withPassword("test");

       @DynamicPropertySource
       static void configureProperties(DynamicPropertyRegistry registry) {
           registry.add("spring.datasource.url", postgres::getJdbcUrl);
           registry.add("spring.datasource.username", postgres::getUsername);
           registry.add("spring.datasource.password", postgres::getPassword);
       }
   ```

3. **For controller tests, use `@WebMvcTest` with `MockMvc`:**
   ```java
   @WebMvcTest(OrderController.class)
   class OrderControllerIntegrationTest {

       @Autowired private MockMvc mockMvc;
       @MockBean private OrderService orderService;
       @MockBean private AuthService authService;
   ```
   Mock only the immediate dependencies of the controller. The controller itself is real.

4. **Test the full request-to-response flow for controllers:**
   ```java
   @Test
   @DisplayName("should return 201 and order body when creating valid order")
   void should_return201_when_creatingValidOrder() throws Exception {
       given(orderService.create(any())).willReturn(anOrder());

       mockMvc.perform(post("/api/orders")
               .contentType(MediaType.APPLICATION_JSON)
               .content(objectMapper.writeValueAsString(aCreateOrderRequest())))
           .andExpect(status().isCreated())
           .andExpect(jsonPath("$.id").exists())
           .andExpect(jsonPath("$.amount").value("100.00"))
           .andExpect(jsonPath("$.status").value("CONFIRMED"));
   }
   ```

5. **Verify status codes for all paths:**
   - `200 OK` for successful reads
   - `201 Created` for successful creates
   - `400 Bad Request` for validation failures
   - `401 Unauthorized` for missing/invalid auth
   - `404 Not Found` for missing resources
   - `500 Internal Server Error` for unexpected failures

6. **Test repository operations with real DB state verification:**
   ```java
   @Test
   @DisplayName("should persist order and generate ID")
   void should_persistOrder_when_saved() {
       Order order = anOrder();
       Order saved = orderRepository.save(order);

       assertThat(saved.getId()).isNotNull();

       Order fetched = orderRepository.findById(saved.getId()).orElseThrow();
       assertThat(fetched.getAmount()).isEqualByComparingTo(order.getAmount());
       assertThat(fetched.getStatus()).isEqualTo(OrderStatus.CONFIRMED);
   }
   ```

7. **Test transaction rollback on failure.** Verify that when an operation fails mid-transaction, all changes are rolled back:
   ```java
   @Test
   @DisplayName("should rollback all changes when payment fails mid-transaction")
   void should_rollbackOrder_when_paymentFails() {
       given(paymentGateway.charge(any())).willThrow(new PaymentDeclinedException());

       assertThatThrownBy(() -> orderService.createAndPay(aCreateOrderRequest()))
           .isInstanceOf(PaymentDeclinedException.class);

       assertThat(orderRepository.count()).isZero();
       assertThat(paymentRepository.count()).isZero();
   }
   ```

8. **Use `@MockBean` only for external dependencies** (payment gateways, email services, third-party APIs). Everything internal to the Spring context should be real:
   ```java
   @SpringBootTest
   @AutoConfigureMockMvc
   class OrderFlowIntegrationTest {

       @Autowired private MockMvc mockMvc;
       @Autowired private OrderRepository orderRepository;
       @MockBean private PaymentGateway paymentGateway;  // external
       @MockBean private EmailService emailService;      // external
   ```

9. **Test request validation and error response bodies:**
   ```java
   @Test
   @DisplayName("should return 400 with field errors when amount is negative")
   void should_return400_when_amountIsNegative() throws Exception {
       mockMvc.perform(post("/api/orders")
               .contentType(MediaType.APPLICATION_JSON)
               .content("{\"amount\": -10.00}"))
           .andExpect(status().isBadRequest())
           .andExpect(jsonPath("$.errors[0].field").value("amount"))
           .andExpect(jsonPath("$.errors[0].message").value("must be greater than 0"));
   }
   ```

10. **Clean up test data between tests.** Use `@Transactional` on `@DataJpaTest` (auto-rollback) or `@Sql` scripts for `@SpringBootTest`:
    ```java
    @AfterEach
    void cleanup() {
        orderRepository.deleteAll();
        paymentRepository.deleteAll();
    }
    ```

11. **Run integration tests and verify they pass.**
    ```bash
    mvn test -pl <module> -Dtest=*IntegrationTest -q
    ```
    Fix any failures. Check that Testcontainers start and stop cleanly without port conflicts.

12. **Re-check coverage for the integrated classes.** Parse JaCoCo output. Integration tests should cover the wiring — constructor injection, transaction boundaries, query execution — that unit tests cannot reach.
