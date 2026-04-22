"""Dockerfile Optimizer — analyze Dockerfiles for best practices.

Checks layer ordering, multi-stage builds, security (no root), .dockerignore,
COPY vs ADD usage, and caching opportunities.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.devops.dockerfile_optimizer")

# ---------------------------------------------------------------------------
# Severity levels
# ---------------------------------------------------------------------------
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

# ---------------------------------------------------------------------------
# Known base images that run as root by default
# ---------------------------------------------------------------------------
_ROOT_IMAGES = {"ubuntu", "debian", "centos", "amazonlinux", "fedora", "alpine"}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    """A single optimisation finding."""

    rule: str
    severity: str  # "high" | "medium" | "low"
    line: int
    message: str
    suggestion: str


@dataclass
class LayerInfo:
    """Parsed info about a Dockerfile instruction."""

    number: int
    instruction: str
    arguments: str
    raw: str


@dataclass
class OptimizationResult:
    """Overall result of Dockerfile analysis."""

    findings: list[Finding] = field(default_factory=list)
    layers: list[LayerInfo] = field(default_factory=list)
    stages: int = 1
    has_dockerignore: bool = False
    score: int = 100  # 0-100, deducted per finding

    @property
    def summary(self) -> str:
        high = sum(1 for f in self.findings if f.severity == SEVERITY_HIGH)
        med = sum(1 for f in self.findings if f.severity == SEVERITY_MEDIUM)
        low = sum(1 for f in self.findings if f.severity == SEVERITY_LOW)
        return f"Score {self.score}/100 | {high} high, {med} medium, {low} low findings"


# ---------------------------------------------------------------------------
# Optimizer class
# ---------------------------------------------------------------------------


class DockerfileOptimizer:
    """Analyze a Dockerfile for best-practice violations."""

    def __init__(self, cwd: Optional[str] = None):
        self.cwd = cwd or os.getcwd()

    # ── Public API ────────────────────────────────────────────────────────

    def analyze(self, dockerfile_path: Optional[str] = None) -> OptimizationResult:
        """Analyze a Dockerfile and return optimization findings."""
        if dockerfile_path is None:
            dockerfile_path = os.path.join(self.cwd, "Dockerfile")

        result = OptimizationResult()
        result.has_dockerignore = self._check_dockerignore()

        if not os.path.isfile(dockerfile_path):
            logger.warning("Dockerfile not found at %s", dockerfile_path)
            result.findings.append(Finding(
                rule="missing-dockerfile",
                severity=SEVERITY_HIGH,
                line=0,
                message="No Dockerfile found",
                suggestion="Create a Dockerfile in the project root",
            ))
            result.score = 0
            return result

        content = Path(dockerfile_path).read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        result.layers = self._parse_layers(lines)
        result.stages = self._count_stages(lines)

        # Run all checks
        self._check_no_root(lines, result)
        self._check_copy_vs_add(lines, result)
        self._check_layer_ordering(lines, result)
        self._check_multi_stage(lines, result)
        self._check_apt_cleanup(lines, result)
        self._check_dockerignore_findings(result)
        self._check_pinned_versions(lines, result)
        self._check_healthcheck(lines, result)

        # Calculate score
        for f in result.findings:
            if f.severity == SEVERITY_HIGH:
                result.score -= 15
            elif f.severity == SEVERITY_MEDIUM:
                result.score -= 8
            else:
                result.score -= 3
        result.score = max(0, result.score)

        logger.info("Dockerfile analysis complete: %s", result.summary)
        return result

    # ── Parsing ───────────────────────────────────────────────────────────

    def _parse_layers(self, lines: list[str]) -> list[LayerInfo]:
        """Parse Dockerfile lines into LayerInfo objects."""
        layers: list[LayerInfo] = []
        instruction_re = re.compile(r"^(FROM|RUN|COPY|ADD|ENV|EXPOSE|CMD|ENTRYPOINT|WORKDIR|ARG|LABEL|VOLUME|USER|HEALTHCHECK|SHELL|ONBUILD|STOPSIGNAL)\s+(.*)$", re.IGNORECASE)
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            m = instruction_re.match(stripped)
            if m:
                layers.append(LayerInfo(
                    number=i,
                    instruction=m.group(1).upper(),
                    arguments=m.group(2),
                    raw=stripped,
                ))
        return layers

    def _count_stages(self, lines: list[str]) -> int:
        """Count multi-stage build stages."""
        return sum(1 for line in lines if re.match(r"^\s*FROM\s+", line, re.IGNORECASE))

    # ── Checks ────────────────────────────────────────────────────────────

    def _check_no_root(self, lines: list[str], result: OptimizationResult) -> None:
        """Check if the container runs as root (no USER instruction)."""
        has_user = False
        user_line = 0
        for i, line in enumerate(lines, 1):
            if re.match(r"^\s*USER\s+", line, re.IGNORECASE):
                has_user = True
                user_line = i
                user_val = line.strip().split(None, 1)[1] if len(line.strip().split(None, 1)) > 1 else ""
                if user_val.strip() in ("root", "0"):
                    result.findings.append(Finding(
                        rule="user-root",
                        severity=SEVERITY_HIGH,
                        line=i,
                        message="Container explicitly runs as root",
                        suggestion="Use a non-root user: USER appuser",
                    ))

        if not has_user:
            result.findings.append(Finding(
                rule="no-user",
                severity=SEVERITY_HIGH,
                line=0,
                message="No USER instruction — container runs as root by default",
                suggestion="Add USER <non-root-user> before CMD/ENTRYPOINT",
            ))

    def _check_copy_vs_add(self, lines: list[str], result: OptimizationResult) -> None:
        """Flag ADD when COPY would suffice."""
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if re.match(r"^\s*ADD\s+", stripped, re.IGNORECASE):
                args = stripped.split(None, 1)[1] if len(stripped.split(None, 1)) > 1 else ""
                # ADD is OK for URLs and tar extraction
                if not re.search(r"https?://|\.tar|\.gz|\.bz2|\.xz", args, re.IGNORECASE):
                    result.findings.append(Finding(
                        rule="prefer-copy",
                        severity=SEVERITY_LOW,
                        line=i,
                        message="ADD used where COPY would suffice",
                        suggestion="Use COPY instead of ADD for simple file copies",
                    ))

    def _check_layer_ordering(self, lines: list[str], result: OptimizationResult) -> None:
        """Check if dependency installation comes before source copy for caching."""
        copy_source_line = 0
        dep_install_line = 0
        for i, line in enumerate(lines, 1):
            stripped = line.strip().lower()
            # Detect source copy (COPY . . or COPY src/)
            if re.match(r"^copy\s+\.\s+", stripped) or re.match(r"^copy\s+src[/\s]", stripped):
                if copy_source_line == 0:
                    copy_source_line = i
            # Detect dependency install
            if re.match(r"^run\s+.*(pip install|npm install|yarn install|go mod download|poetry install|bundle install)", stripped):
                dep_install_line = i

        if copy_source_line > 0 and dep_install_line > 0 and dep_install_line > copy_source_line:
            result.findings.append(Finding(
                rule="layer-ordering",
                severity=SEVERITY_MEDIUM,
                line=dep_install_line,
                message="Dependency install after full source COPY breaks layer caching",
                suggestion="COPY dependency manifests first, install deps, then COPY source",
            ))

    def _check_multi_stage(self, lines: list[str], result: OptimizationResult) -> None:
        """Suggest multi-stage build if only one FROM and compile tools present."""
        stages = self._count_stages(lines)
        content_lower = "\n".join(lines).lower()
        has_build_tools = any(kw in content_lower for kw in ("gcc", "make", "maven", "gradle", "go build", "cargo build", "tsc"))
        if stages == 1 and has_build_tools:
            result.findings.append(Finding(
                rule="no-multi-stage",
                severity=SEVERITY_MEDIUM,
                line=1,
                message="Build tools found but no multi-stage build — image may be bloated",
                suggestion="Use multi-stage build: compile in builder stage, copy artifacts to slim runtime stage",
            ))

    def _check_apt_cleanup(self, lines: list[str], result: OptimizationResult) -> None:
        """Check for apt-get install without cleanup in the same RUN."""
        for i, line in enumerate(lines, 1):
            stripped = line.strip().lower()
            if "apt-get install" in stripped and "rm -rf /var/lib/apt/lists" not in stripped:
                result.findings.append(Finding(
                    rule="apt-no-cleanup",
                    severity=SEVERITY_MEDIUM,
                    line=i,
                    message="apt-get install without cleanup in same layer",
                    suggestion="Add && rm -rf /var/lib/apt/lists/* in the same RUN",
                ))

    def _check_dockerignore_findings(self, result: OptimizationResult) -> None:
        """Report if .dockerignore is missing."""
        if not result.has_dockerignore:
            result.findings.append(Finding(
                rule="no-dockerignore",
                severity=SEVERITY_LOW,
                line=0,
                message="No .dockerignore file found",
                suggestion="Create .dockerignore to exclude .git, node_modules, __pycache__, etc.",
            ))

    def _check_pinned_versions(self, lines: list[str], result: OptimizationResult) -> None:
        """Check if FROM uses a pinned tag (not 'latest')."""
        for i, line in enumerate(lines, 1):
            m = re.match(r"^\s*FROM\s+(\S+)", line, re.IGNORECASE)
            if m:
                image = m.group(1)
                if ":" not in image or image.endswith(":latest"):
                    result.findings.append(Finding(
                        rule="unpinned-base",
                        severity=SEVERITY_MEDIUM,
                        line=i,
                        message=f"Base image '{image}' is not pinned to a specific version",
                        suggestion="Pin to a specific tag, e.g. python:3.11-slim",
                    ))

    def _check_healthcheck(self, lines: list[str], result: OptimizationResult) -> None:
        """Check if HEALTHCHECK is defined."""
        has_healthcheck = any(
            re.match(r"^\s*HEALTHCHECK\s+", line, re.IGNORECASE)
            for line in lines
        )
        if not has_healthcheck:
            result.findings.append(Finding(
                rule="no-healthcheck",
                severity=SEVERITY_LOW,
                line=0,
                message="No HEALTHCHECK instruction defined",
                suggestion="Add HEALTHCHECK to enable container health monitoring",
            ))

    # ── Helpers ───────────────────────────────────────────────────────────

    def _check_dockerignore(self) -> bool:
        """Check if .dockerignore exists in cwd."""
        return os.path.isfile(os.path.join(self.cwd, ".dockerignore"))
