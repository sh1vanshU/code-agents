---
name: contract-validation
description: Validate API contracts — detect breaking changes in request/response schemas
---

## Before You Start
- Endpoints discovered
- Contract baseline exists (.code-agents/{repo}.contracts.json)

## Workflow

1. **For each REST endpoint, call and capture response.**

2. **Extract response structure:** field names, types, required/optional.

3. **Compare with saved contract baseline:**
   - BREAKING: field removed, type changed, required field added
   - COMPATIBLE: new optional field added, field made optional

4. **Report:**
   ```
   Contract Validation:
     GET /api/v1/payments — ✅ Compatible
     POST /api/v1/orders — ❌ BREAKING (field 'orderId' type changed: int → string)
     GET /api/v1/users — ✅ Compatible (new field 'email' added)
   ```

5. **For BREAKING changes:** Flag for review — downstream services may break.

## Definition of Done
- No unintentional breaking changes
- All breaking changes documented and approved
