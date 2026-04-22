"""Kubernetes Manifest Generator — create K8s resources from service description.

Generates Deployment, Service, HPA, and PDB manifests with sensible defaults
and best-practice annotations.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.devops.k8s_generator")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ServiceSpec:
    """Input specification for a Kubernetes service."""

    name: str
    image: str
    port: int = 8080
    replicas: int = 2
    cpu_request: str = "100m"
    cpu_limit: str = "500m"
    memory_request: str = "128Mi"
    memory_limit: str = "512Mi"
    namespace: str = "default"
    labels: dict[str, str] = field(default_factory=dict)
    env_vars: dict[str, str] = field(default_factory=dict)
    health_path: str = "/health"
    min_replicas: int = 2
    max_replicas: int = 10
    target_cpu_percent: int = 70
    min_available: str = "50%"
    service_type: str = "ClusterIP"
    node_selector: dict[str, str] = field(default_factory=dict)


@dataclass
class GeneratedManifest:
    """A single generated K8s manifest."""

    kind: str
    name: str
    content: str
    filename: str


@dataclass
class GenerationResult:
    """Result of manifest generation."""

    manifests: list[GeneratedManifest] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def combined_yaml(self) -> str:
        """Return all manifests concatenated with --- separators."""
        return "\n---\n".join(m.content for m in self.manifests)


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class K8sGenerator:
    """Generate Kubernetes manifests from a service specification."""

    def __init__(self, cwd: Optional[str] = None):
        self.cwd = cwd or os.getcwd()

    # ── Public API ────────────────────────────────────────────────────────

    def generate(self, spec: ServiceSpec) -> GenerationResult:
        """Generate all K8s manifests for the given service spec."""
        result = GenerationResult()

        # Validate spec
        self._validate(spec, result)

        # Merge default labels
        labels = {"app": spec.name, "managed-by": "code-agents"}
        labels.update(spec.labels)

        result.manifests.append(self._deployment(spec, labels))
        result.manifests.append(self._service(spec, labels))
        result.manifests.append(self._hpa(spec, labels))
        result.manifests.append(self._pdb(spec, labels))

        logger.info("Generated %d manifests for %s", len(result.manifests), spec.name)
        return result

    def write_manifests(self, result: GenerationResult, output_dir: Optional[str] = None) -> list[str]:
        """Write generated manifests to disk and return file paths."""
        out = output_dir or os.path.join(self.cwd, "k8s")
        os.makedirs(out, exist_ok=True)
        paths = []
        for m in result.manifests:
            path = os.path.join(out, m.filename)
            with open(path, "w", encoding="utf-8") as f:
                f.write(m.content)
            paths.append(path)
            logger.info("Wrote %s", path)
        return paths

    # ── Validation ────────────────────────────────────────────────────────

    def _validate(self, spec: ServiceSpec, result: GenerationResult) -> None:
        """Validate the service spec and add warnings."""
        name_re = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
        if not name_re.match(spec.name):
            result.warnings.append(
                f"Service name '{spec.name}' does not match K8s naming convention (lowercase, alphanumeric, hyphens)"
            )
        if spec.replicas < 2:
            result.warnings.append("Running fewer than 2 replicas — no high-availability")
        if ":" not in spec.image:
            result.warnings.append(f"Image '{spec.image}' has no tag — will default to :latest")

    # ── Manifest generators ───────────────────────────────────────────────

    def _deployment(self, spec: ServiceSpec, labels: dict[str, str]) -> GeneratedManifest:
        """Generate Deployment manifest."""
        labels_yaml = self._labels_block(labels, indent=6)
        selector_yaml = self._labels_block({"app": spec.name}, indent=8)
        pod_labels_yaml = self._labels_block(labels, indent=10)
        env_yaml = self._env_block(spec.env_vars, indent=12)
        node_sel_yaml = self._node_selector_block(spec.node_selector, indent=8)

        content = f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {spec.name}
  namespace: {spec.namespace}
  labels:
{labels_yaml}
spec:
  replicas: {spec.replicas}
  selector:
    matchLabels:
{selector_yaml}
  template:
    metadata:
      labels:
{pod_labels_yaml}
    spec:
{node_sel_yaml}      containers:
      - name: {spec.name}
        image: {spec.image}
        ports:
        - containerPort: {spec.port}
        resources:
          requests:
            cpu: "{spec.cpu_request}"
            memory: "{spec.memory_request}"
          limits:
            cpu: "{spec.cpu_limit}"
            memory: "{spec.memory_limit}"
{env_yaml}        readinessProbe:
          httpGet:
            path: {spec.health_path}
            port: {spec.port}
          initialDelaySeconds: 5
          periodSeconds: 10
        livenessProbe:
          httpGet:
            path: {spec.health_path}
            port: {spec.port}
          initialDelaySeconds: 15
          periodSeconds: 20"""

        return GeneratedManifest(
            kind="Deployment",
            name=spec.name,
            content=content,
            filename=f"{spec.name}-deployment.yaml",
        )

    def _service(self, spec: ServiceSpec, labels: dict[str, str]) -> GeneratedManifest:
        """Generate Service manifest."""
        labels_yaml = self._labels_block(labels, indent=4)
        selector_yaml = self._labels_block({"app": spec.name}, indent=4)

        content = f"""apiVersion: v1
kind: Service
metadata:
  name: {spec.name}
  namespace: {spec.namespace}
  labels:
{labels_yaml}
spec:
  type: {spec.service_type}
  selector:
{selector_yaml}
  ports:
  - port: {spec.port}
    targetPort: {spec.port}
    protocol: TCP
    name: http"""

        return GeneratedManifest(
            kind="Service",
            name=spec.name,
            content=content,
            filename=f"{spec.name}-service.yaml",
        )

    def _hpa(self, spec: ServiceSpec, labels: dict[str, str]) -> GeneratedManifest:
        """Generate HorizontalPodAutoscaler manifest."""
        content = f"""apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {spec.name}
  namespace: {spec.namespace}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {spec.name}
  minReplicas: {spec.min_replicas}
  maxReplicas: {spec.max_replicas}
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: {spec.target_cpu_percent}"""

        return GeneratedManifest(
            kind="HorizontalPodAutoscaler",
            name=spec.name,
            content=content,
            filename=f"{spec.name}-hpa.yaml",
        )

    def _pdb(self, spec: ServiceSpec, labels: dict[str, str]) -> GeneratedManifest:
        """Generate PodDisruptionBudget manifest."""
        content = f"""apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: {spec.name}
  namespace: {spec.namespace}
spec:
  minAvailable: "{spec.min_available}"
  selector:
    matchLabels:
      app: {spec.name}"""

        return GeneratedManifest(
            kind="PodDisruptionBudget",
            name=spec.name,
            content=content,
            filename=f"{spec.name}-pdb.yaml",
        )

    # ── YAML helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _labels_block(labels: dict[str, str], indent: int) -> str:
        """Render labels as indented YAML lines."""
        prefix = " " * indent
        return "\n".join(f"{prefix}{k}: {v}" for k, v in sorted(labels.items()))

    @staticmethod
    def _env_block(env_vars: dict[str, str], indent: int) -> str:
        """Render env vars as YAML block."""
        if not env_vars:
            return ""
        prefix = " " * indent
        lines = [f"{prefix}env:"]
        for k, v in sorted(env_vars.items()):
            lines.append(f"{prefix}- name: {k}")
            lines.append(f"{prefix}  value: \"{v}\"")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _node_selector_block(node_selector: dict[str, str], indent: int) -> str:
        """Render nodeSelector if present."""
        if not node_selector:
            return ""
        prefix = " " * indent
        lines = [f"{prefix}nodeSelector:"]
        for k, v in sorted(node_selector.items()):
            lines.append(f"{prefix}  {k}: {v}")
        return "\n".join(lines) + "\n"
