---
name: performance-optimize
description: Performance optimization — N+1 queries, caching, lazy loading, async, connection pooling, pagination, indexes
---

## Before You Start

Identify the performance concern:
- **Slow API endpoint** — user reports or observed latency
- **High DB load** — too many queries, slow queries
- **Memory pressure** — large collections loaded eagerly
- **General optimization** — proactive scan for common issues

Establish a baseline: note current response times or query counts before making changes.

## Workflow

### 1. Identify N+1 Query Problems

Scan for patterns that cause N+1:
- `@OneToMany` / `@ManyToMany` with default `FetchType.LAZY` accessed in a loop
- Repository `findAll()` followed by accessing a collection on each entity
- `findBy*` methods in a loop instead of `findAllByIdIn(ids)`

**Detection:**
```java
// Enable SQL logging in test/dev
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
```
Run the endpoint and count SQL statements. More than 1 query per entity = N+1.

**Fix options:**
```java
// Option 1: @EntityGraph (declarative)
@EntityGraph(attributePaths = {"items", "items.product"})
List<Order> findAllByUserId(Long userId);

// Option 2: JOIN FETCH (JPQL)
@Query("SELECT o FROM Order o JOIN FETCH o.items WHERE o.userId = :userId")
List<Order> findAllByUserIdWithItems(@Param("userId") Long userId);

// Option 3: Batch fetching
@BatchSize(size = 50)
@OneToMany(mappedBy = "order")
private List<OrderItem> items;
```

### 2. Add Caching

Identify candidates: data that is read frequently and changes rarely.

**Spring Cache setup:**
```java
@EnableCaching  // on @Configuration class

@Cacheable(value = "products", key = "#id")
public Product findById(Long id) { ... }

@CacheEvict(value = "products", key = "#product.id")
public Product save(Product product) { ... }

@CacheEvict(value = "products", allEntries = true)
public void deleteAll() { ... }
```

**Cache provider** (add to `application.yml`):
```yaml
spring:
  cache:
    type: caffeine  # or redis
    caffeine:
      spec: maximumSize=1000,expireAfterWrite=10m
```

Cache candidates:
- Configuration/lookup tables (countries, currencies, categories)
- User profile data (if not frequently updated)
- Aggregated counts or statistics
- External API responses (with appropriate TTL)

### 3. Fix Eager Loading

Scan for `FetchType.EAGER` on collections:
```java
// BAD: loads all items every time Order is fetched
@OneToMany(fetch = FetchType.EAGER)
private List<OrderItem> items;

// GOOD: lazy by default, use @EntityGraph when needed
@OneToMany(fetch = FetchType.LAZY)
private List<OrderItem> items;
```

Switch `EAGER` -> `LAZY` for:
- `@OneToMany` collections (almost always should be LAZY)
- `@ManyToMany` collections
- `@ManyToOne` that is not always needed (case by case)

After switching, fix any `LazyInitializationException` by adding `@EntityGraph` or `JOIN FETCH` to the queries that actually need the data.

### 4. Add Async Processing

Identify operations that do not need to block the response:
- Sending emails or notifications
- Audit logging
- Analytics event publishing
- File processing or report generation

```java
@EnableAsync  // on @Configuration class

@Async
@Transactional(propagation = Propagation.REQUIRES_NEW)
public CompletableFuture<Void> sendOrderConfirmation(Order order) {
    // non-blocking — runs in separate thread
    emailService.send(order.getUserEmail(), buildTemplate(order));
    return CompletableFuture.completedFuture(null);
}
```

For Spring Boot 3.2+ with Java 21, consider virtual threads:
```yaml
spring:
  threads:
    virtual:
      enabled: true
```

### 5. Verify Connection Pooling

Check HikariCP configuration in `application.yml`:
```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 20        # default 10, increase for high concurrency
      minimum-idle: 5              # keep connections warm
      idle-timeout: 300000         # 5 min
      max-lifetime: 1800000        # 30 min
      connection-timeout: 30000    # 30 sec
      leak-detection-threshold: 60000  # warn if connection held > 60s
```

Red flags to fix:
- `maximum-pool-size` too low for concurrent load
- No `leak-detection-threshold` configured
- `max-lifetime` exceeding DB server timeout

### 6. Add Pagination to Unbounded Queries

Scan for methods that return `List<Entity>` without bounds:
```java
// BAD: loads entire table
List<Order> findAll();
List<Order> findByStatus(String status);

// GOOD: paginated
Page<Order> findAll(Pageable pageable);
Page<Order> findByStatus(String status, Pageable pageable);
```

Update controller to accept pagination:
```java
@GetMapping("/orders")
public Page<OrderResponse> listOrders(
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size,
        @RequestParam(defaultValue = "createdAt,desc") String[] sort) {
    Pageable pageable = PageRequest.of(page, size, Sort.by(sort));
    return orderService.findAll(pageable).map(mapper::toResponse);
}
```

### 7. Suggest Database Indexes

Analyze queries and suggest indexes for:
- Columns in `WHERE` clauses that filter large tables
- Columns in `ORDER BY` on large result sets
- Foreign key columns (JPA does not auto-create indexes on FK columns)
- Composite indexes for queries with multiple filter conditions

```java
@Entity
@Table(name = "orders", indexes = {
    @Index(name = "idx_orders_user_id", columnList = "user_id"),
    @Index(name = "idx_orders_status_created", columnList = "status, created_at DESC")
})
public class Order { ... }
```

### 8. Benchmark After Changes

Re-run the same operations and compare:
- Query count (before vs after)
- Response time (before vs after)
- Memory usage for collection-heavy endpoints

```bash
# Run tests with SQL logging
mvn test -Dspring.jpa.show-sql=true -q
```

## Definition of Done

- N+1 queries identified and fixed with `@EntityGraph` or `JOIN FETCH`
- Caching added for frequently-read, rarely-changed data
- Eager collections switched to lazy (with targeted fetch where needed)
- Async processing for non-blocking operations
- Connection pool configured with appropriate limits and leak detection
- Unbounded queries paginated
- Index suggestions documented or applied
- All tests green after optimizations
- Measurable improvement in query count or response time
