---
name: dependency-map
description: Ticket dependency mapping — graph, circular detection, critical path, unblocking order
---

## Before You Start

- [ ] Confirm the Jira project key or specific epic/sprint to scope the analysis
- [ ] Verify that issue links are used in the project (blocks/is-blocked-by, relates-to)
- [ ] Determine scope: single ticket and its dependencies, or full sprint/epic dependency graph

## Workflow

1. **Fetch tickets with links.** Query all tickets in scope with their issue links:
   ```bash
   curl -sS -X POST BASE_URL/jira/search \
     -H "Content-Type: application/json" \
     -d '{"jql": "project = PROJECT_KEY AND sprint in openSprints()", "max_results": 200}'
   ```
   For each ticket, extract: key, summary, status, assignee, and issue links (type + linked ticket key).

2. **Build dependency graph.** Create an adjacency list:
   - **blocks / is-blocked-by**: directed edge (blocker -> blocked)
   - **relates-to**: undirected edge (co-dependency)
   - Track: ticket key, status, assignee for each node

3. **Detect circular dependencies.** Walk the directed graph looking for cycles:
   - If cycle found: report the exact chain (e.g., A blocks B, B blocks C, C blocks A)
   - Flag as CRITICAL — circular dependencies will stall the sprint

4. **Calculate critical path.** Find the longest chain of blocking dependencies:
   - The critical path determines the minimum time to complete all work
   - Report: ticket chain, total story points on the path, estimated completion based on velocity

5. **Suggest unblocking order.** Prioritize tickets that unblock the most others:
   ```
   ## Unblocking Priority
   | Rank | Ticket | Blocks | Status | Assignee | Action |
   |------|--------|--------|--------|----------|--------|
   | 1 | TICKET-123 | 3 others | In Progress | Alice | Complete ASAP — unblocks TICKET-124, 125, 126 |
   | 2 | TICKET-130 | 2 others | To Do | Bob | Start immediately — on critical path |
   | 3 | TICKET-140 | 1 other | Blocked | — | Blocked by TICKET-123 — will auto-unblock |
   ```

6. **Present the dependency map:**
   ```
   ## Dependency Map — Sprint {name}

   ### Critical Path
   TICKET-100 -> TICKET-123 -> TICKET-150 -> TICKET-180
   (4 tickets, 21 story points, estimated 8 days)

   ### Circular Dependencies
   NONE (or list cycles)

   ### Blocking Summary
   - 5 tickets have blockers
   - 3 tickets are blocking others
   - 2 tickets have no dependencies (can be worked in parallel)
   ```

## Definition of Done

- [ ] All issue links fetched and dependency graph constructed
- [ ] Circular dependencies detected and reported (or confirmed none exist)
- [ ] Critical path identified with ticket chain and estimated duration
- [ ] Unblocking priority list generated with actionable recommendations
- [ ] Parallel-safe tickets identified (no dependencies, can start immediately)
