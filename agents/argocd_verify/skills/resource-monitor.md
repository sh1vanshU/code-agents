---
name: resource-monitor
description: Monitor CPU/memory per pod, HPA status, OOM risk, right-sizing recommendations
---

## Workflow

1. **List pods:**
   ```bash
   curl -sS "${BASE_URL}/k8s/pods?namespace=NS&label=app=SVC"
   ```

2. **Check resource requests/limits** via describe:
   ```bash
   curl -sS "${BASE_URL}/k8s/pods/{pod_name}/describe?namespace=NS"
   ```
   Extract: CPU request/limit, memory request/limit, QoS class.

3. **Check deployment replicas:**
   ```bash
   curl -sS "${BASE_URL}/k8s/deployments?namespace=NS"
   ```
   Verify: desired vs available vs ready. If available < desired, pods failing to start.

4. **Check events for resource issues:**
   ```bash
   curl -sS "${BASE_URL}/k8s/events?namespace=NS&limit=50"
   ```
   Look for: OOMKilled, Evicted, FailedScheduling, BackOff, Unhealthy.

5. **Assess OOM risk:**

   | Memory vs Limit | Risk | Action |
   |----------------|------|--------|
   | < 60% | Low | Normal |
   | 60-80% | Medium | Monitor |
   | 80-90% | High | Increase limit |
   | > 90% | Critical | Increase immediately |
   | OOMKilled event | Active | Increase limit + restart |

6. **Assess CPU pressure:**

   | CPU vs Limit | Impact | Action |
   |-------------|--------|--------|
   | < 50% | None | Normal |
   | 50-80% | Possible throttling | Monitor response times |
   | > 80% | Likely throttling | Increase limit or scale out |

7. **Generate resource report** with per-pod table and alerts.

## Right-Sizing Guide

| Observation | Recommendation |
|------------|---------------|
| CPU usage < 20% of request | Reduce CPU request |
| CPU usage > 80% of limit | Increase limit or scale out |
| Memory < 40% of request | Reduce memory request |
| Memory growing without plateau | Possible memory leak |
| Frequent OOMKilled | Increase memory limit by 50% |
| Pods Pending | Check node capacity |
