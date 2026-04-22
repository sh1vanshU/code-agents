"""Outage topology — map code change to infrastructure to customer impact chain.

Traces the blast radius of a code change through service dependencies,
infrastructure layers, and customer-facing features to predict outage scope.
"""

from __future__ import annotations

import logging
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("code_agents.devops.outage_topology")

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
}

# Infrastructure layer patterns
INFRA_PATTERNS = {
    "database": re.compile(r"\b(sql|db|database|postgres|mysql|mongo|redis|dynamo)\b", re.I),
    "cache": re.compile(r"\b(cache|redis|memcache|cdn)\b", re.I),
    "queue": re.compile(r"\b(queue|kafka|rabbitmq|sqs|celery|worker)\b", re.I),
    "storage": re.compile(r"\b(s3|blob|storage|upload|file_store)\b", re.I),
    "network": re.compile(r"\b(http|grpc|rest|websocket|api_call|external)\b", re.I),
    "auth": re.compile(r"\b(auth|oauth|jwt|token|session|login)\b", re.I),
}

# Customer impact patterns
CUSTOMER_FEATURES = {
    "login": re.compile(r"\b(login|sign.?in|auth|session)\b", re.I),
    "payment": re.compile(r"\b(payment|checkout|billing|charge|refund)\b", re.I),
    "search": re.compile(r"\b(search|filter|query|browse)\b", re.I),
    "notification": re.compile(r"\b(notif|email|sms|push|alert)\b", re.I),
    "data_display": re.compile(r"\b(dashboard|report|chart|list|view|page)\b", re.I),
    "upload": re.compile(r"\b(upload|import|attach|file)\b", re.I),
}


@dataclass
class TopologyNode:
    """A node in the outage topology."""

    name: str = ""
    layer: str = ""  # code | service | infra | customer
    node_type: str = ""  # file | service | database | feature
    risk_score: float = 0.0
    dependencies: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class ImpactChain:
    """A chain from code change to customer impact."""

    code_change: str = ""
    service_path: list[str] = field(default_factory=list)
    infra_affected: list[str] = field(default_factory=list)
    customer_features: list[str] = field(default_factory=list)
    severity: str = "low"  # low | medium | high | critical
    confidence: float = 0.0


@dataclass
class OutageTopologyResult:
    """Result of outage topology mapping."""

    nodes: list[TopologyNode] = field(default_factory=list)
    impact_chains: list[ImpactChain] = field(default_factory=list)
    max_blast_radius: int = 0
    highest_severity: str = "low"
    affected_customers_pct: float = 0.0  # estimated
    summary: dict[str, int] = field(default_factory=dict)


class OutageTopologyMapper:
    """Map code changes to outage topology."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.debug("OutageTopologyMapper initialized for %s", cwd)

    def map_impact(
        self,
        changed_files: list[str],
        service_map: dict[str, list[str]] | None = None,
    ) -> OutageTopologyResult:
        """Map code change impact through the topology.

        Args:
            changed_files: List of changed file paths (relative).
            service_map: Optional mapping of service -> files.

        Returns:
            OutageTopologyResult with nodes, chains, and severity.
        """
        result = OutageTopologyResult()
        logger.info("Mapping outage topology for %d files", len(changed_files))

        # Build service map if not provided
        if service_map is None:
            service_map = self._infer_service_map()

        # Create code-layer nodes
        for f in changed_files:
            result.nodes.append(TopologyNode(
                name=f, layer="code", node_type="file",
            ))

        # Find service-layer impact
        affected_services = self._find_affected_services(changed_files, service_map)
        for svc in affected_services:
            result.nodes.append(TopologyNode(
                name=svc, layer="service", node_type="service",
                dependencies=service_map.get(svc, []),
            ))

        # Find infra-layer impact
        infra_deps = self._find_infra_dependencies(changed_files)
        for infra_type, files in infra_deps.items():
            result.nodes.append(TopologyNode(
                name=infra_type, layer="infra", node_type=infra_type,
                metadata={"files": files},
            ))

        # Find customer-facing impact
        customer_impact = self._find_customer_impact(changed_files)
        for feature, files in customer_impact.items():
            result.nodes.append(TopologyNode(
                name=feature, layer="customer", node_type="feature",
                metadata={"files": files},
            ))

        # Build impact chains
        for f in changed_files:
            chain = self._build_impact_chain(
                f, affected_services, infra_deps, customer_impact,
            )
            if chain.customer_features or chain.infra_affected:
                result.impact_chains.append(chain)

        # Calculate overall metrics
        result.max_blast_radius = len(result.nodes)
        if result.impact_chains:
            severities = [c.severity for c in result.impact_chains]
            severity_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
            result.highest_severity = max(severities, key=lambda s: severity_order.get(s, 0))

        # Estimate customer impact
        result.affected_customers_pct = self._estimate_customer_impact(customer_impact)

        result.summary = {
            "changed_files": len(changed_files),
            "affected_services": len(affected_services),
            "infra_layers": len(infra_deps),
            "customer_features": len(customer_impact),
            "impact_chains": len(result.impact_chains),
            "blast_radius": result.max_blast_radius,
        }
        logger.info("Topology mapped: blast_radius=%d, severity=%s",
                     result.max_blast_radius, result.highest_severity)
        return result

    def _infer_service_map(self) -> dict[str, list[str]]:
        """Infer service boundaries from directory structure."""
        services: dict[str, list[str]] = defaultdict(list)
        for root, dirs, fnames in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in fnames:
                if not fname.endswith(".py"):
                    continue
                rel = os.path.relpath(os.path.join(root, fname), self.cwd)
                parts = rel.split(os.sep)
                if len(parts) >= 2:
                    service = parts[0] if parts[0] not in ("src", "lib") else parts[1]
                    services[service].append(rel)
        return dict(services)

    def _find_affected_services(
        self, changed_files: list[str], service_map: dict[str, list[str]],
    ) -> list[str]:
        """Find services affected by changed files."""
        affected: set[str] = set()
        for svc, files in service_map.items():
            for changed in changed_files:
                if changed in files or any(changed.startswith(f.split("/")[0]) for f in files):
                    affected.add(svc)
        return list(affected)

    def _find_infra_dependencies(
        self, changed_files: list[str],
    ) -> dict[str, list[str]]:
        """Find infrastructure dependencies in changed files."""
        infra: dict[str, list[str]] = defaultdict(list)
        for rel in changed_files:
            fpath = os.path.join(self.cwd, rel)
            try:
                content = Path(fpath).read_text(errors="replace")
            except OSError:
                continue
            for infra_type, pattern in INFRA_PATTERNS.items():
                if pattern.search(content):
                    infra[infra_type].append(rel)
        return dict(infra)

    def _find_customer_impact(
        self, changed_files: list[str],
    ) -> dict[str, list[str]]:
        """Find customer-facing features affected."""
        impact: dict[str, list[str]] = defaultdict(list)
        for rel in changed_files:
            fpath = os.path.join(self.cwd, rel)
            try:
                content = Path(fpath).read_text(errors="replace")
            except OSError:
                continue
            for feature, pattern in CUSTOMER_FEATURES.items():
                if pattern.search(content) or pattern.search(rel):
                    impact[feature].append(rel)
        return dict(impact)

    def _build_impact_chain(
        self,
        changed_file: str,
        services: list[str],
        infra: dict[str, list[str]],
        customer: dict[str, list[str]],
    ) -> ImpactChain:
        """Build an impact chain for a single file."""
        chain = ImpactChain(code_change=changed_file)

        # Service path
        for svc in services:
            chain.service_path.append(svc)

        # Infra affected
        for infra_type, files in infra.items():
            if changed_file in files:
                chain.infra_affected.append(infra_type)

        # Customer features
        for feature, files in customer.items():
            if changed_file in files:
                chain.customer_features.append(feature)

        # Determine severity
        if "payment" in chain.customer_features or "auth" in chain.infra_affected:
            chain.severity = "critical"
        elif "database" in chain.infra_affected or "login" in chain.customer_features:
            chain.severity = "high"
        elif chain.customer_features:
            chain.severity = "medium"
        else:
            chain.severity = "low"

        chain.confidence = 0.6 + 0.1 * len(chain.infra_affected)
        return chain

    def _estimate_customer_impact(self, features: dict[str, list[str]]) -> float:
        """Estimate percentage of customers affected."""
        feature_reach = {
            "login": 100.0, "payment": 80.0, "search": 60.0,
            "data_display": 50.0, "notification": 30.0, "upload": 20.0,
        }
        if not features:
            return 0.0
        max_reach = max(feature_reach.get(f, 10.0) for f in features)
        return min(100.0, max_reach)


def map_outage_topology(
    cwd: str,
    changed_files: list[str],
    service_map: dict[str, list[str]] | None = None,
) -> dict:
    """Convenience function for outage topology mapping.

    Returns:
        Dict with nodes, impact chains, and severity.
    """
    mapper = OutageTopologyMapper(cwd)
    result = mapper.map_impact(changed_files=changed_files, service_map=service_map)
    return {
        "highest_severity": result.highest_severity,
        "affected_customers_pct": result.affected_customers_pct,
        "impact_chains": [
            {"code_change": c.code_change, "services": c.service_path,
             "infra": c.infra_affected, "features": c.customer_features,
             "severity": c.severity}
            for c in result.impact_chains
        ],
        "nodes": [
            {"name": n.name, "layer": n.layer, "type": n.node_type}
            for n in result.nodes
        ],
        "summary": result.summary,
    }
