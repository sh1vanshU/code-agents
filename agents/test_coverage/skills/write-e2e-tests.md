---
name: write-e2e-tests
description: Write end-to-end tests with full request flow, WireMock for external APIs, and side effect verification
---

## Workflow

1. **Identify the end-to-end flow to test.** Map the full request path:
   - API entry point (controller endpoint)
   - Service chain (which services are called in order)
   - Database operations (reads, writes, updates)
   - External API calls (payment gateways, notification services)
   - Side effects (messages published, emails sent, audit logs written)

2. **Set up the test class with a real Spring context and random port:**
   ```java
   @SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
   @Testcontainers
   class OrderFlowE2ETest {

       @Autowired private TestRestTemplate restTemplate;
       @Autowired private OrderRepository orderRepository;
       @Autowired private PaymentRepository paymentRepository;

       @Container
       static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:15")
           .withDatabaseName("testdb");

       @DynamicPropertySource
       static void configureProperties(DynamicPropertyRegistry registry) {
           registry.add("spring.datasource.url", postgres::getJdbcUrl);
           registry.add("spring.datasource.username", postgres::getUsername);
           registry.add("spring.datasource.password", postgres::getPassword);
       }
   ```

3. **Use WireMock to stub external API dependencies:**
   ```java
   @WireMockTest(httpPort = 9091)
   class PaymentFlowE2ETest {

       @DynamicPropertySource
       static void configureProperties(DynamicPropertyRegistry registry) {
           registry.add("payment.gateway.url", () -> "http://localhost:9091");
       }

       @BeforeEach
       void stubExternalApis() {
           stubFor(post(urlPathEqualTo("/api/v1/charge"))
               .willReturn(aResponse()
                   .withStatus(200)
                   .withHeader("Content-Type", "application/json")
                   .withBody("{\"transactionId\": \"txn-123\", \"status\": \"APPROVED\"}")));
       }
   ```

4. **Test the complete happy path request and response:**
   ```java
   @Test
   @DisplayName("should create order, charge payment, and return confirmation")
   void should_completeOrderFlow_when_allServicesSucceed() {
       CreateOrderRequest request = aCreateOrderRequest();

       ResponseEntity<OrderResponse> response = restTemplate.postForEntity(
           "/api/orders", request, OrderResponse.class);

       assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
       assertThat(response.getBody().getTransactionId()).isEqualTo("txn-123");
       assertThat(response.getBody().getStatus()).isEqualTo("CONFIRMED");
   }
   ```

5. **Verify database side effects after the request completes:**
   ```java
   @Test
   @DisplayName("should persist order and payment records in the database")
   void should_persistRecords_when_orderCreated() {
       restTemplate.postForEntity("/api/orders", aCreateOrderRequest(), OrderResponse.class);

       List<Order> orders = orderRepository.findAll();
       assertThat(orders).hasSize(1);
       assertThat(orders.get(0).getStatus()).isEqualTo(OrderStatus.CONFIRMED);

       List<Payment> payments = paymentRepository.findAll();
       assertThat(payments).hasSize(1);
       assertThat(payments.get(0).getTransactionId()).isEqualTo("txn-123");
   }
   ```

6. **Test failure scenarios with external service errors:**
   ```java
   @Test
   @DisplayName("should return 502 and not persist order when payment gateway times out")
   void should_return502_when_paymentGatewayTimesOut() {
       stubFor(post(urlPathEqualTo("/api/v1/charge"))
           .willReturn(aResponse().withFixedDelay(5000).withStatus(200)));

       ResponseEntity<ErrorResponse> response = restTemplate.postForEntity(
           "/api/orders", aCreateOrderRequest(), ErrorResponse.class);

       assertThat(response.getStatusCode()).isEqualTo(HttpStatus.BAD_GATEWAY);
       assertThat(orderRepository.count()).isZero();
   }

   @Test
   @DisplayName("should return 502 when payment gateway returns 500")
   void should_return502_when_paymentGatewayReturns500() {
       stubFor(post(urlPathEqualTo("/api/v1/charge"))
           .willReturn(aResponse().withStatus(500).withBody("{\"error\": \"internal\"}")));

       ResponseEntity<ErrorResponse> response = restTemplate.postForEntity(
           "/api/orders", aCreateOrderRequest(), ErrorResponse.class);

       assertThat(response.getStatusCode()).isEqualTo(HttpStatus.BAD_GATEWAY);
   }

   @Test
   @DisplayName("should return 400 when request body has invalid data")
   void should_return400_when_requestInvalid() {
       Map<String, Object> invalid = Map.of("amount", -50);

       ResponseEntity<ErrorResponse> response = restTemplate.postForEntity(
           "/api/orders", invalid, ErrorResponse.class);

       assertThat(response.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
       assertThat(orderRepository.count()).isZero();
   }
   ```

7. **Verify WireMock received the expected requests (outbound call verification):**
   ```java
   WireMock.verify(1, postRequestedFor(urlPathEqualTo("/api/v1/charge"))
       .withRequestBody(matchingJsonPath("$.amount", equalTo("100.00")))
       .withHeader("Authorization", matching("Bearer .*")));
   ```

8. **Test message queue side effects if applicable.** Use an embedded broker or a Testcontainer for Kafka/RabbitMQ:
   ```java
   @Autowired private KafkaConsumer<String, String> testConsumer;

   @Test
   @DisplayName("should publish order-created event to Kafka")
   void should_publishEvent_when_orderCreated() {
       restTemplate.postForEntity("/api/orders", aCreateOrderRequest(), OrderResponse.class);

       ConsumerRecord<String, String> record = KafkaTestUtils.getSingleRecord(testConsumer, "order-events");
       assertThat(record.value()).contains("ORDER_CREATED");
   }
   ```

9. **Clean up between tests.** Reset WireMock stubs, truncate database tables, drain message queues:
   ```java
   @AfterEach
   void cleanup() {
       WireMock.reset();
       orderRepository.deleteAll();
       paymentRepository.deleteAll();
   }
   ```

10. **Run E2E tests and verify they pass.**
    ```bash
    mvn test -pl <module> -Dtest=*E2ETest -q
    ```
    E2E tests are slower. Ensure Testcontainers and WireMock start/stop cleanly. Fix flaky tests immediately — E2E flakiness is a test design problem, not an acceptable trade-off.

11. **Re-check coverage.** E2E tests should cover the wiring between layers that unit and integration tests miss: HTTP serialization, error handling middleware, transaction propagation across service boundaries, and retry/fallback logic.
