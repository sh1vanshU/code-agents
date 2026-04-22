---
name: impact-analysis
description: Trace a proposed change — affected modules, broken tests, API changes, downstream services, risk level
---

## Before You Start

- [ ] Get the exact diff or description of the proposed change — vague "we are changing X" is not enough
- [ ] Identify whether this is a forward-only change or if rollback is possible
- [ ] Know the deployment cadence: is this deploying alone or bundled with other changes?
- [ ] Check if the affected area has feature flags that can limit blast radius

## Workflow

1. **Identify the proposed change.** Understand exactly what will change:
   - Which files are being modified and how
   - What functions, classes, or APIs are affected
   - Is this additive (new code) or mutative (changing existing behavior)?

2. **Trace affected modules.** For each changed file, follow the dependency graph:
   - What imports this file? (direct dependents)
   - What do those dependents export? (transitive dependents)
   - Read each dependent to check if the change breaks their assumptions
   - Map the full blast radius: `changed file -> direct dependents -> transitive dependents`

3. **Identify tests that will break.** Check the test suite:
   - Tests that directly test the changed functions
   - Tests that use the changed functions as setup or helpers
   - Integration tests that exercise the affected flow end-to-end
   - Tests that mock the changed interfaces (mock signatures may need updating)

4. **Check for API changes.** If the change affects an API:
   - Request schema changes (new required fields, removed fields, type changes)
   - Response schema changes (new fields, removed fields, changed structure)
   - Status code changes (new error codes, different success codes)
   - Backward compatibility: will existing clients break?

5. **Map downstream service impact.** For changes affecting external interfaces:
   - Which services call this API?
   - Which services consume events or messages from this component?
   - Which database tables are shared with other services?
   - Are there any contracts (OpenAPI specs, protobuf, Avro) that need updating?

6. **Assess risk level.** Rate the change:

   **LOW** — Additive change, no existing behavior modified, no API changes.
   Examples: new endpoint, new utility function, new test.

   **MEDIUM** — Existing behavior modified but backward compatible, tests may need updates.
   Examples: refactored internal logic, added optional parameter, changed error message.

   **HIGH** — Breaking change to API or shared interface, downstream services affected.
   Examples: removed field, changed required parameters, modified database schema.

   **CRITICAL** — Data migration required, multiple services must deploy together, rollback is complex.
   Examples: database schema change, event format change, auth flow change.

7. **Output impact report.**

   ```
   ## Impact Analysis: {change summary}

   ### Risk Level: {LOW|MEDIUM|HIGH|CRITICAL}

   ### Affected Modules
   | Module | Impact | Details |
   |--------|--------|---------|
   | path/to/module.py | DIRECT | Function signature changed |
   | path/to/consumer.py | INDIRECT | Calls changed function |

   ### Tests Affected
   - WILL BREAK: {test names that will fail}
   - NEEDS UPDATE: {tests that need mock changes}
   - UNAFFECTED: {tests that are safe}

   ### API Changes
   - {endpoint}: {description of change, backward compatibility status}

   ### Downstream Services
   - {service}: {impact description}

   ### Recommendations
   - {action items for safe rollout}

   ### Blast Radius Estimation
   - Direct impact: {N files, N functions changed}
   - Indirect impact: {N modules depend on changed code}
   - User-facing impact: {which user flows are affected}
   - Data impact: {database tables, cache keys, config affected}
   - Estimated rollback complexity: {SIMPLE|MODERATE|COMPLEX|REQUIRES-MIGRATION}

   ### Test Coverage Gap Analysis
   | Changed Code Path | Has Unit Test? | Has Integration Test? | Gap |
   |-------------------|---------------|----------------------|-----|
   | {function/method} | YES/NO | YES/NO | {what is missing} |

   ### Rollback Plan
   - Rollback method: {git revert / feature flag / config change / DB migration rollback}
   - Rollback complexity: {one-click / requires coordination / requires data migration}
   - Data reversibility: {no data changes / data is additive only / data is mutated — rollback loses changes}
   - Rollback time estimate: {seconds / minutes / hours}
   ```

## Blast Radius Estimation

Quantify the impact in concrete terms:

1. **Code blast radius**: Count of files, functions, and modules directly and indirectly affected
2. **User blast radius**: Which user-facing features or workflows will behave differently?
3. **Data blast radius**: Which database tables, cache entries, or files will have different data?
4. **Team blast radius**: Which teams own the affected downstream services?

Present as concentric rings:
```
[Changed code] -> [Direct dependents] -> [Transitive dependents] -> [External consumers]
     Core              Ring 1                  Ring 2                    Ring 3
```

Each ring should list specific modules/services with the impact type.

## Rollback Complexity Assessment

| Factor | Simple Rollback | Complex Rollback |
|--------|----------------|------------------|
| **Schema changes** | None | Added/removed columns, changed types |
| **Data mutations** | No data changed | Existing records modified or deleted |
| **API contract** | No external changes | Consumers adapted to new contract |
| **Feature flags** | Change behind flag | No flag, always active |
| **Multi-service** | Single service deploy | Multiple services must roll back together |
| **State machines** | No state transitions | Users mid-flow in new state |

If rollback complexity is COMPLEX or REQUIRES-MIGRATION, recommend a phased rollout with canary deployment.

## Test Coverage Gap Analysis

For every changed function/method, verify:
- Does a unit test exist that exercises the changed logic?
- Does an integration test exist that exercises the changed flow end-to-end?
- Are error paths tested, or only happy paths?
- Are edge cases (null, empty, boundary) tested?

Report gaps as a table with specific recommendations for which tests to add before deploying.

## Definition of Done

- [ ] Risk level assigned with clear justification (not just "feels like MEDIUM")
- [ ] All affected modules traced with dependency direction (direct vs transitive)
- [ ] API changes assessed for backward compatibility
- [ ] Blast radius quantified (code, user, data, team dimensions)
- [ ] Rollback plan documented with complexity and time estimate
- [ ] Test coverage gaps identified for changed code paths
- [ ] Recommendations are actionable — each has a specific owner and timeline
