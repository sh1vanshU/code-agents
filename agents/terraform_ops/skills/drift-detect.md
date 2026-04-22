---
name: drift-detect
description: Detect infrastructure drift — compare actual state vs configuration
---

## Workflow

1. **Initialize:**
   ```bash
   curl -sS -X POST ${BASE_URL}/terraform/init -H "Content-Type: application/json" -d '{"working_dir":"TF_DIR"}'
   ```

2. **Refresh-only plan (drift detection):**
   ```bash
   curl -sS -X POST ${BASE_URL}/terraform/plan -H "Content-Type: application/json" -d '{"working_dir":"TF_DIR","refresh_only":true}'
   ```

3. **Parse drift:**
   - Resources that drifted from config
   - What changed (manual changes, external modifications)

4. **Check state:**
   ```bash
   curl -sS "${BASE_URL}/terraform/state?working_dir=TF_DIR"
   ```

5. **Report:**
   - Drift found: list drifted resources and what changed
   - No drift: "Infrastructure matches configuration"
   → Emit: `[REMEMBER:drift_detected=true/false]`

## Definition of Done

- Drift analysis complete
- Drifted resources identified (if any)
- Recommended action: re-apply to fix drift, or update config to match
