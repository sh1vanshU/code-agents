---
name: state-inspect
description: Inspect terraform state — list resources, show details, check outputs
---

## Workflow

1. **List all resources in state:**
   ```bash
   curl -sS "${BASE_URL}/terraform/state?working_dir=TF_DIR"
   ```

2. **Show specific resource details:**
   ```bash
   curl -sS "${BASE_URL}/terraform/state/RESOURCE_ADDRESS?working_dir=TF_DIR"
   ```

3. **Show outputs:**
   ```bash
   curl -sS "${BASE_URL}/terraform/output?working_dir=TF_DIR"
   ```

4. **Show providers:**
   ```bash
   curl -sS "${BASE_URL}/terraform/providers?working_dir=TF_DIR"
   ```

5. **Report:** Resource count, key resources, outputs, provider versions.
   → Emit: `[REMEMBER:resources_count=<count>]`
