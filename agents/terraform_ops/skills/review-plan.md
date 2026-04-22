---
name: review-plan
description: Deep review of a terraform plan — security, cost, blast radius analysis
---

## Workflow

1. **Run plan** (if not already done):
   Use [SKILL:plan] to generate the plan.

2. **Security review:**
   - IAM changes: new policies, role assumptions, permission escalation
   - Network changes: security group rules, VPC peering, public access
   - Encryption: any resources without encryption at rest or in transit

3. **Blast radius analysis:**
   - How many resources affected?
   - Are any stateful resources (databases, queues) being modified?
   - Cross-dependency impact

4. **Cost estimation:**
   - New resources → estimate monthly cost impact
   - Destroyed resources → savings

5. **Report:** Security findings, blast radius, cost impact, go/no-go recommendation.
