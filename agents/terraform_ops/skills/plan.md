---
name: plan
description: Run terraform init, validate, and plan — review changes before apply
---

## Before Starting

Check [Session Memory] for tf_dir, workspace.

## Workflow

1. **Initialize terraform:**
   ```bash
   curl -sS -X POST ${BASE_URL}/terraform/init -H "Content-Type: application/json" -d '{"working_dir":"TF_DIR"}'
   ```

2. **Validate configuration:**
   ```bash
   curl -sS -X POST ${BASE_URL}/terraform/validate -H "Content-Type: application/json" -d '{"working_dir":"TF_DIR"}'
   ```
   If validation fails, report errors and STOP.

3. **Run plan:**
   ```bash
   curl -sS -X POST ${BASE_URL}/terraform/plan -H "Content-Type: application/json" -d '{"working_dir":"TF_DIR"}'
   ```

4. **Parse plan output:**
   - Count: additions, changes, deletions
   - Flag critical resources (databases, IAM, networking)
   - Flag any deletions prominently

5. **Report to user:**
   ```
   Plan: 3 to add, 1 to change, 0 to destroy
   + aws_s3_bucket.logs
   + aws_s3_bucket_policy.logs
   + aws_cloudwatch_log_group.app
   ~ aws_ecs_service.app (image tag update)
   ```
   → Emit: `[REMEMBER:plan_changes=3 to add, 1 to change, 0 to destroy]`

6. **Ask:** "Apply these changes?"

## Definition of Done

- Plan executed and summarized
- Critical changes flagged
- User informed and ready to decide on apply
