"""Verbal Architect — English description to architecture design with interfaces."""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.knowledge.verbal_architect")


@dataclass
class Component:
    """An architectural component."""
    name: str = ""
    description: str = ""
    component_type: str = ""  # service, library, database, queue, gateway, ui
    responsibilities: list[str] = field(default_factory=list)
    interfaces: list[dict] = field(default_factory=list)  # {name, input, output, protocol}
    dependencies: list[str] = field(default_factory=list)
    technology: str = ""


@dataclass
class Connection:
    """A connection between components."""
    source: str = ""
    target: str = ""
    protocol: str = ""  # REST, gRPC, message_queue, database, event
    description: str = ""
    sync: bool = True


@dataclass
class ArchitectureDesign:
    """Complete architecture design."""
    name: str = ""
    description: str = ""
    components: list[Component] = field(default_factory=list)
    connections: list[Connection] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    non_functional: dict = field(default_factory=dict)  # scalability, availability, etc.


@dataclass
class ArchitectReport:
    """Complete verbal architect report."""
    design: ArchitectureDesign = field(default_factory=ArchitectureDesign)
    original_description: str = ""
    ambiguities: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


COMPONENT_INDICATORS = {
    "service": ["service", "api", "server", "backend", "endpoint", "microservice"],
    "database": ["database", "db", "store", "storage", "persist", "repository", "cache"],
    "queue": ["queue", "message", "event", "stream", "pubsub", "kafka", "rabbit"],
    "gateway": ["gateway", "proxy", "load balancer", "ingress", "router", "nginx"],
    "ui": ["frontend", "ui", "dashboard", "web app", "client", "mobile", "browser"],
    "library": ["library", "sdk", "module", "package", "util", "helper"],
}

PATTERN_INDICATORS = {
    "microservices": ["microservice", "service mesh", "independently deployable"],
    "event_driven": ["event", "message", "async", "pubsub", "eventual consistency"],
    "layered": ["layer", "tier", "separation", "mvc", "clean architecture"],
    "cqrs": ["cqrs", "command query", "read model", "write model"],
    "saga": ["saga", "distributed transaction", "compensation"],
}

NF_KEYWORDS = {
    "scalability": ["scale", "scalable", "horizontal", "elastic", "high traffic"],
    "availability": ["available", "uptime", "redundant", "failover", "ha"],
    "security": ["secure", "auth", "encrypt", "certificate", "tls"],
    "performance": ["fast", "low latency", "performant", "cached", "optimized"],
}


class VerbalArchitect:
    """Transforms English descriptions into architecture designs."""

    def __init__(self):
        pass

    def analyze(self, description: str,
                constraints: Optional[list[str]] = None) -> ArchitectReport:
        """Transform description into architecture design."""
        logger.info("Designing architecture from description (%d chars)", len(description))
        constraints = constraints or []

        desc_lower = description.lower()

        # Extract components
        components = self._extract_components(desc_lower, description)
        logger.info("Identified %d components", len(components))

        # Infer connections
        connections = self._infer_connections(components, desc_lower)

        # Detect patterns
        patterns = self._detect_patterns(desc_lower)

        # Extract non-functional requirements
        nf = self._extract_nf_requirements(desc_lower)

        # Generate interfaces
        for comp in components:
            comp.interfaces = self._generate_interfaces(comp, connections)

        design = ArchitectureDesign(
            name=self._generate_name(description),
            description=description[:200],
            components=components,
            connections=connections,
            patterns=patterns,
            constraints=constraints,
            non_functional=nf,
        )

        ambiguities = self._find_ambiguities(description, components)
        alternatives = self._suggest_alternatives(patterns, components)

        report = ArchitectReport(
            design=design,
            original_description=description,
            ambiguities=ambiguities,
            alternatives=alternatives,
            warnings=self._generate_warnings(design),
        )
        logger.info("Architecture: %d components, %d connections, %d patterns",
                     len(components), len(connections), len(patterns))
        return report

    def _extract_components(self, desc_lower: str, original: str) -> list[Component]:
        """Extract components from description."""
        components = []
        seen = set()
        for ctype, keywords in COMPONENT_INDICATORS.items():
            for kw in keywords:
                if kw in desc_lower and ctype not in seen:
                    # Find context around the keyword
                    idx = desc_lower.index(kw)
                    context = original[max(0, idx - 30):idx + 50].strip()
                    name = self._derive_name(kw, context)
                    components.append(Component(
                        name=name,
                        component_type=ctype,
                        description=f"Handles {kw}-related functionality",
                        responsibilities=[f"Manage {kw} operations"],
                    ))
                    seen.add(ctype)
                    break

        # If no components found, create a basic monolith
        if not components:
            components.append(Component(
                name="Application",
                component_type="service",
                description="Main application service",
            ))
        return components

    def _derive_name(self, keyword: str, context: str) -> str:
        """Derive a component name from keyword and context."""
        words = re.findall(r"\b[A-Z]?\w+", context)
        relevant = [w for w in words if len(w) > 3 and w.lower() != keyword]
        if relevant:
            return f"{relevant[0].title()}{keyword.title()}"
        return f"{keyword.title()}Service"

    def _infer_connections(self, components: list[Component],
                           desc_lower: str) -> list[Connection]:
        """Infer connections between components."""
        connections = []
        for i, src in enumerate(components):
            for j, tgt in enumerate(components):
                if i >= j:
                    continue
                protocol = self._infer_protocol(src, tgt, desc_lower)
                if protocol:
                    connections.append(Connection(
                        source=src.name,
                        target=tgt.name,
                        protocol=protocol,
                        description=f"{src.name} communicates with {tgt.name}",
                        sync=protocol in ("REST", "gRPC"),
                    ))
        return connections

    def _infer_protocol(self, src: Component, tgt: Component, desc: str) -> str:
        """Infer communication protocol."""
        if tgt.component_type == "database":
            return "database"
        if tgt.component_type == "queue":
            return "message_queue"
        if "grpc" in desc:
            return "gRPC"
        if "event" in desc or "async" in desc:
            return "event"
        return "REST"

    def _detect_patterns(self, desc_lower: str) -> list[str]:
        """Detect architectural patterns."""
        detected = []
        for pattern, keywords in PATTERN_INDICATORS.items():
            if any(kw in desc_lower for kw in keywords):
                detected.append(pattern)
        return detected or ["monolith"]

    def _extract_nf_requirements(self, desc_lower: str) -> dict:
        """Extract non-functional requirements."""
        nf = {}
        for category, keywords in NF_KEYWORDS.items():
            if any(kw in desc_lower for kw in keywords):
                nf[category] = True
        return nf

    def _generate_interfaces(self, comp: Component,
                             connections: list[Connection]) -> list[dict]:
        """Generate interfaces for a component."""
        interfaces = []
        # Input interfaces
        incoming = [c for c in connections if c.target == comp.name]
        for conn in incoming:
            interfaces.append({
                "name": f"receive_from_{conn.source.lower()}",
                "direction": "in",
                "protocol": conn.protocol,
            })
        # Output interfaces
        outgoing = [c for c in connections if c.source == comp.name]
        for conn in outgoing:
            interfaces.append({
                "name": f"send_to_{conn.target.lower()}",
                "direction": "out",
                "protocol": conn.protocol,
            })
        return interfaces

    def _generate_name(self, description: str) -> str:
        """Generate architecture name."""
        words = description.split()[:5]
        return " ".join(words).rstrip(".,") + " Architecture"

    def _find_ambiguities(self, description: str, components: list[Component]) -> list[str]:
        """Find ambiguities in the description."""
        ambs = []
        if len(components) <= 1:
            ambs.append("Could not identify distinct components — provide more detail")
        vague = re.findall(r"\b(should|might|could|somehow|etc)\b", description, re.IGNORECASE)
        if vague:
            ambs.append(f"Vague language detected: {', '.join(set(v.lower() for v in vague))}")
        return ambs

    def _suggest_alternatives(self, patterns: list[str],
                              components: list[Component]) -> list[str]:
        """Suggest alternative approaches."""
        alts = []
        if "monolith" in patterns and len(components) > 3:
            alts.append("Consider microservices for better independent scaling")
        if "microservices" in patterns and len(components) <= 2:
            alts.append("A monolith may be simpler for this scale")
        return alts

    def _generate_warnings(self, design: ArchitectureDesign) -> list[str]:
        """Generate warnings."""
        warnings = []
        if not design.non_functional:
            warnings.append("No non-functional requirements specified — consider scalability and availability")
        if len(design.components) > 10:
            warnings.append("Many components — ensure team capacity for maintenance")
        return warnings


def format_report(report: ArchitectReport) -> str:
    d = report.design
    lines = [f"# {d.name}", f"\n{d.description}\n"]
    lines.append("## Components")
    for c in d.components:
        lines.append(f"  [{c.component_type}] {c.name}: {c.description}")
    if d.connections:
        lines.append("\n## Connections")
        for c in d.connections:
            lines.append(f"  {c.source} -> {c.target} ({c.protocol})")
    if d.patterns:
        lines.append(f"\n## Patterns: {', '.join(d.patterns)}")
    return "\n".join(lines)
