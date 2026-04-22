---
name: container-scan
trigger: "docker security, container scan, image vulnerabilities, Dockerfile audit"
---

# Container Security Scan

## Workflow

1. **Dockerfile analysis**
   - Check base image (official? pinned version? not `latest`?)
   - Check for `USER root` (should use non-root)
   - Check for secrets in build args or ENV
   - Verify multi-stage build (minimize attack surface)

2. **Image vulnerability scan**
   ```bash
   # Using trivy (if available)
   trivy image <image-name>
   
   # Or grype
   grype <image-name>
   ```

3. **Runtime security checks**
   - No privileged containers
   - Read-only root filesystem where possible
   - Resource limits set (CPU, memory)
   - No host network/PID namespace sharing

4. **Report findings** with severity (CRITICAL/HIGH/MEDIUM/LOW) and remediation steps
