"""Tests for the Kubernetes manifest generator."""

from __future__ import annotations

import os
import pytest

from code_agents.devops.k8s_generator import (
    K8sGenerator, ServiceSpec, GeneratedManifest, GenerationResult,
)


class TestServiceSpec:
    """Test ServiceSpec defaults."""

    def test_defaults(self):
        s = ServiceSpec(name="myapp", image="myapp:1.0")
        assert s.port == 8080
        assert s.replicas == 2
        assert s.namespace == "default"
        assert s.service_type == "ClusterIP"

    def test_custom_values(self):
        s = ServiceSpec(name="api", image="api:v2", port=3000, replicas=5, namespace="prod")
        assert s.port == 3000
        assert s.replicas == 5
        assert s.namespace == "prod"


class TestGenerationResult:
    """Test GenerationResult."""

    def test_combined_yaml(self):
        r = GenerationResult(manifests=[
            GeneratedManifest(kind="Deployment", name="a", content="apiVersion: apps/v1", filename="a.yaml"),
            GeneratedManifest(kind="Service", name="a", content="apiVersion: v1", filename="b.yaml"),
        ])
        combined = r.combined_yaml()
        assert "---" in combined
        assert "apps/v1" in combined
        assert "apiVersion: v1" in combined


class TestK8sGenerator:
    """Test K8sGenerator manifest generation."""

    def _make_spec(self, **overrides):
        defaults = {"name": "myapp", "image": "myapp:1.0"}
        defaults.update(overrides)
        return ServiceSpec(**defaults)

    def test_generate_all_manifests(self, tmp_path):
        gen = K8sGenerator(cwd=str(tmp_path))
        result = gen.generate(self._make_spec())
        assert len(result.manifests) == 4
        kinds = {m.kind for m in result.manifests}
        assert kinds == {"Deployment", "Service", "HorizontalPodAutoscaler", "PodDisruptionBudget"}

    def test_deployment_content(self, tmp_path):
        gen = K8sGenerator(cwd=str(tmp_path))
        result = gen.generate(self._make_spec(name="api", image="api:v2", port=3000))
        dep = next(m for m in result.manifests if m.kind == "Deployment")
        assert "api:v2" in dep.content
        assert "containerPort: 3000" in dep.content
        assert "api-deployment.yaml" == dep.filename

    def test_service_content(self, tmp_path):
        gen = K8sGenerator(cwd=str(tmp_path))
        result = gen.generate(self._make_spec(name="web", service_type="LoadBalancer"))
        svc = next(m for m in result.manifests if m.kind == "Service")
        assert "LoadBalancer" in svc.content
        assert "web" in svc.content

    def test_hpa_content(self, tmp_path):
        gen = K8sGenerator(cwd=str(tmp_path))
        result = gen.generate(self._make_spec(min_replicas=3, max_replicas=20, target_cpu_percent=80))
        hpa = next(m for m in result.manifests if m.kind == "HorizontalPodAutoscaler")
        assert "minReplicas: 3" in hpa.content
        assert "maxReplicas: 20" in hpa.content
        assert "averageUtilization: 80" in hpa.content

    def test_pdb_content(self, tmp_path):
        gen = K8sGenerator(cwd=str(tmp_path))
        result = gen.generate(self._make_spec(name="svc", min_available="1"))
        pdb = next(m for m in result.manifests if m.kind == "PodDisruptionBudget")
        assert 'minAvailable: "1"' in pdb.content

    def test_env_vars(self, tmp_path):
        gen = K8sGenerator(cwd=str(tmp_path))
        result = gen.generate(self._make_spec(env_vars={"DB_HOST": "db.local", "LOG_LEVEL": "info"}))
        dep = next(m for m in result.manifests if m.kind == "Deployment")
        assert "DB_HOST" in dep.content
        assert "db.local" in dep.content

    def test_validation_warnings(self, tmp_path):
        gen = K8sGenerator(cwd=str(tmp_path))
        result = gen.generate(self._make_spec(name="MyApp", image="myapp", replicas=1))
        assert len(result.warnings) >= 2  # bad name + no tag + low replicas

    def test_write_manifests(self, tmp_path):
        gen = K8sGenerator(cwd=str(tmp_path))
        result = gen.generate(self._make_spec())
        paths = gen.write_manifests(result, output_dir=str(tmp_path / "k8s"))
        assert len(paths) == 4
        for p in paths:
            assert os.path.isfile(p)

    def test_labels_block(self):
        block = K8sGenerator._labels_block({"app": "test", "env": "prod"}, indent=4)
        assert "    app: test" in block
        assert "    env: prod" in block

    def test_namespace(self, tmp_path):
        gen = K8sGenerator(cwd=str(tmp_path))
        result = gen.generate(self._make_spec(namespace="production"))
        for m in result.manifests:
            assert "namespace: production" in m.content
