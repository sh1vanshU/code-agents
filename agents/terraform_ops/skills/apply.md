---
name: apply
description: Apply terraform changes — requires plan approval first
---

## Before Starting

Check [Session Memory] for plan_changes. A plan MUST have been run first.
If no plan exists in session memory, run [SKILL:plan] first.

## Workflow

1. **Confirm plan was reviewed:** Check [Session Memory] for plan_changes.

2. **Apply:**
   ```bash
   curl -sS -X POST ${BASE_URL}/terraform/apply -H "Content-Type: application/json" -d '{"working_dir":"TF_DIR","auto_approve":true}'
   ```

3. **Parse apply output:**
   - Resources created, changed, destroyed
   - Any errors

4. **Verify state:**
   ```bash
   curl -sS "${BASE_URL}/terraform/output?working_dir=TF_DIR"
   ```

5. **Report:** Applied successfully. Show outputs if any.
   → Emit: `[REMEMBER:last_apply=<timestamp>]`

## Definition of Done

- Changes applied successfully
- Outputs reported
- State verified
