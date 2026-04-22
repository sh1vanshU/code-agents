---
name: capacity-planning
description: Analyze system capacity — load patterns, bottlenecks, scaling limits. Recommend scaling strategy, caching, sharding, async processing
---

## Before You Start

- [ ] Clarify the system under analysis: which services, databases, and infrastructure components
- [ ] Gather current traffic numbers if available (RPS, concurrent users, data volume)
- [ ] Identify the growth trajectory: steady, seasonal spikes, or rapid scaling expected
- [ ] Understand SLA requirements: latency targets, uptime, throughput guarantees

## Workflow

1. **Profile the current architecture.** Read the codebase and deployment config to map:
   - **Compute**: number of instances, CPU/memory allocation, auto-scaling rules
   - **Data stores**: database type (SQL/NoSQL), instance size, replication setup
   - **Caches**: what is cached, TTL policies, cache size, eviction strategy
   - **Queues**: message broker type, partition count, consumer group config
   - **External APIs**: rate limits, timeout settings, retry policies

2. **Identify load patterns.** Analyze the code to understand:
   - **Read vs write ratio**: which endpoints are read-heavy vs write-heavy
   - **Hot paths**: which code paths handle the most traffic (API endpoints, background jobs)
   - **Batch vs real-time**: which operations are synchronous vs async/scheduled
   - **Payload sizes**: typical request/response sizes, file uploads, bulk operations
   - **Connection patterns**: connection pooling config, keep-alive settings

3. **Map resource consumption per request.** For each critical endpoint:
   ```
   Endpoint: POST /v1/chat/completions
   - CPU: high (LLM call orchestration, SSE streaming)
   - Memory: medium (conversation history in memory)
   - DB queries: 0 (stateless)
   - External calls: 1 (backend LLM API, latency: 2-30s)
   - Network I/O: high (streaming response)
   ```

4. **Identify current bottlenecks.** Look for:
   | Bottleneck Type | What to Check | Code Evidence |
   |----------------|---------------|---------------|
   | **CPU-bound** | Complex computation in request path | Loops, serialization, encryption |
   | **Memory-bound** | Large objects held in memory | Unbounded caches, full result sets loaded |
   | **I/O-bound** | Waiting on external resources | Synchronous HTTP calls, unindexed queries |
   | **Connection-bound** | Connection pool exhaustion | Fixed pool size, no backpressure |
   | **Storage-bound** | Disk filling up or slow writes | Log volume, temp files, large uploads |
   | **Single-threaded** | GIL contention (Python), event loop blocking | CPU work in async context |

5. **Calculate scaling limits.** Estimate when the system hits its ceiling:
   - **Vertical limit**: max instance size before diminishing returns
   - **Horizontal limit**: what prevents adding more instances (shared state, DB connections, sticky sessions)
   - **Data limit**: when the database becomes the bottleneck (table size, query latency, replication lag)
   - **Cost limit**: when scaling becomes economically unsustainable

6. **Recommend scaling strategy.** For each bottleneck, propose a solution:

   **Horizontal scaling:**
   - Stateless services: add instances behind a load balancer
   - Requirements: no in-memory state, no local file dependencies, idempotent operations

   **Vertical scaling:**
   - When: single-threaded workloads, database with limited connection support
   - Limit: maximum instance size, diminishing returns on cost/performance

   **Caching strategy:**
   - What to cache: expensive computations, frequently read data, external API responses
   - Where: application-level (in-memory), distributed (Redis/Memcached), CDN (static assets)
   - Invalidation: TTL-based, event-driven, write-through

   **Database optimization:**
   - Read replicas for read-heavy workloads
   - Sharding strategy: by tenant, by date range, by hash
   - Connection pooling: pgbouncer, ProxySQL
   - Query optimization: indexes, materialized views, denormalization

   **Async processing:**
   - Move non-critical work off the request path: notifications, analytics, reports
   - Queue-based: produce message, consume async, retry on failure
   - Batch processing: aggregate small writes, process in bulk on schedule

7. **Output the capacity plan.**
   ```
   ## Capacity Plan: {system name}

   ### Current State
   | Resource | Current Config | Utilization | Headroom |
   |----------|---------------|-------------|----------|

   ### Load Profile
   | Endpoint/Job | RPS/Frequency | Latency p50/p99 | Resource Intensity |
   |-------------|--------------|-----------------|-------------------|

   ### Bottleneck Analysis
   | Bottleneck | Type | Impact | Scaling Limit |
   |-----------|------|--------|--------------|

   ### Scaling Recommendations
   | # | Recommendation | Type | Effort | Impact | Priority |
   |---|---------------|------|--------|--------|----------|

   ### Capacity Roadmap
   | Timeline | Action | Trigger Metric | Expected Outcome |
   |----------|--------|---------------|-----------------|
   | Now | {quick wins} | — | {improvement} |
   | 3 months | {medium-term} | {metric threshold} | {improvement} |
   | 6-12 months | {long-term} | {metric threshold} | {improvement} |

   ### Trade-offs
   | Option A | Option B | When to Choose A | When to Choose B |
   |----------|----------|-----------------|-----------------|
   ```

## Definition of Done

- [ ] Current architecture profiled: compute, data stores, caches, queues
- [ ] Load patterns identified: read/write ratio, hot paths, payload sizes
- [ ] Resource consumption mapped per critical endpoint
- [ ] Bottlenecks identified with type, impact, and code evidence
- [ ] Scaling limits estimated (vertical, horizontal, data, cost)
- [ ] Recommendations provided with effort and priority
- [ ] Trade-offs between approaches explicitly stated
- [ ] Capacity roadmap with timeline, triggers, and expected outcomes
