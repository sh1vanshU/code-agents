"""Helm Chart Debugger — render templates, diff values, find mismatches.

Diagnoses common Helm issues: template rendering errors, value mismatches
between environments, and chart dependency problems.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.devops.helm_debugger")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ValueMismatch:
    """A mismatch between two values files."""

    key: str
    left_value: str
    right_value: str
    severity: str  # "info" | "warning" | "error"


@dataclass
class RenderError:
    """A template rendering error."""

    template: str
    line: int
    message: str
    suggestion: str


@dataclass
class DebugResult:
    """Result of Helm chart debugging."""

    rendered_templates: dict[str, str] = field(default_factory=dict)
    render_errors: list[RenderError] = field(default_factory=list)
    value_mismatches: list[ValueMismatch] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    success: bool = True

    @property
    def summary(self) -> str:
        return (
            f"{len(self.rendered_templates)} templates, "
            f"{len(self.render_errors)} errors, "
            f"{len(self.value_mismatches)} mismatches"
        )


# ---------------------------------------------------------------------------
# Debugger
# ---------------------------------------------------------------------------


class HelmDebugger:
    """Debug Helm charts: render, diff, diagnose."""

    def __init__(self, cwd: Optional[str] = None):
        self.cwd = cwd or os.getcwd()

    # ── Public API ────────────────────────────────────────────────────────

    def render(self, chart_path: str, values_file: Optional[str] = None,
               release_name: str = "debug") -> DebugResult:
        """Render Helm templates and parse results."""
        result = DebugResult()
        cmd = ["helm", "template", release_name, chart_path]
        if values_file:
            cmd.extend(["-f", values_file])

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, cwd=self.cwd,
            )
        except FileNotFoundError:
            result.success = False
            result.render_errors.append(RenderError(
                template="", line=0,
                message="helm CLI not found",
                suggestion="Install Helm: https://helm.sh/docs/intro/install/",
            ))
            return result
        except subprocess.TimeoutExpired:
            result.success = False
            result.warnings.append("Helm template rendering timed out after 30s")
            return result

        if proc.returncode != 0:
            result.success = False
            result.render_errors.extend(self._parse_render_errors(proc.stderr))
            return result

        result.rendered_templates = self._split_templates(proc.stdout)
        result.warnings.extend(self._check_rendered(result.rendered_templates))
        logger.info("Rendered %d templates for %s", len(result.rendered_templates), chart_path)
        return result

    def diff_values(self, left_file: str, right_file: str) -> list[ValueMismatch]:
        """Diff two Helm values files and return mismatches."""
        left = self._parse_flat_values(left_file)
        right = self._parse_flat_values(right_file)

        mismatches = []
        all_keys = sorted(set(left.keys()) | set(right.keys()))

        for key in all_keys:
            lv = left.get(key, "<missing>")
            rv = right.get(key, "<missing>")
            if lv != rv:
                severity = self._mismatch_severity(key, lv, rv)
                mismatches.append(ValueMismatch(
                    key=key, left_value=str(lv), right_value=str(rv),
                    severity=severity,
                ))

        logger.info("Found %d mismatches between %s and %s", len(mismatches), left_file, right_file)
        return mismatches

    def lint(self, chart_path: str) -> DebugResult:
        """Run helm lint and parse output."""
        result = DebugResult()
        try:
            proc = subprocess.run(
                ["helm", "lint", chart_path],
                capture_output=True, text=True, timeout=30, cwd=self.cwd,
            )
        except FileNotFoundError:
            result.success = False
            result.warnings.append("helm CLI not found")
            return result
        except subprocess.TimeoutExpired:
            result.success = False
            result.warnings.append("Helm lint timed out")
            return result

        if proc.returncode != 0:
            result.success = False

        # Parse lint output
        for line in (proc.stdout + proc.stderr).splitlines():
            line = line.strip()
            if line.startswith("[ERROR]"):
                result.render_errors.append(RenderError(
                    template="", line=0,
                    message=line.replace("[ERROR]", "").strip(),
                    suggestion="Check chart structure and template syntax",
                ))
            elif line.startswith("[WARNING]"):
                result.warnings.append(line.replace("[WARNING]", "").strip())

        return result

    # ── Parsing helpers ───────────────────────────────────────────────────

    def _parse_render_errors(self, stderr: str) -> list[RenderError]:
        """Parse helm template errors into structured objects."""
        errors = []
        # Pattern: Error: template: <name>:<line>:<col>: ...
        pattern = re.compile(r"template:\s*(\S+):(\d+):\d+:\s*(.*)")
        for line in stderr.splitlines():
            m = pattern.search(line)
            if m:
                errors.append(RenderError(
                    template=m.group(1),
                    line=int(m.group(2)),
                    message=m.group(3).strip(),
                    suggestion=self._suggest_fix(m.group(3)),
                ))
            elif "Error:" in line and not errors:
                errors.append(RenderError(
                    template="", line=0,
                    message=line.split("Error:", 1)[1].strip(),
                    suggestion="Check chart structure and values",
                ))
        return errors

    def _split_templates(self, output: str) -> dict[str, str]:
        """Split rendered YAML output by --- source markers."""
        templates: dict[str, str] = {}
        current_name = "unknown"
        current_lines: list[str] = []

        for line in output.splitlines():
            if line.startswith("# Source:"):
                if current_lines:
                    templates[current_name] = "\n".join(current_lines).strip()
                current_name = line.replace("# Source:", "").strip()
                current_lines = []
            elif line.strip() == "---":
                if current_lines:
                    templates[current_name] = "\n".join(current_lines).strip()
                    current_lines = []
            else:
                current_lines.append(line)

        if current_lines:
            templates[current_name] = "\n".join(current_lines).strip()
        return templates

    def _parse_flat_values(self, filepath: str) -> dict[str, str]:
        """Parse a YAML values file into flat dotted key-value pairs."""
        try:
            import yaml
        except ImportError:
            logger.warning("PyYAML not installed, falling back to regex parsing")
            return self._parse_flat_values_regex(filepath)

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as exc:
            logger.warning("Failed to parse %s: %s", filepath, exc)
            return {}

        flat: dict[str, str] = {}
        self._flatten(data, "", flat)
        return flat

    def _parse_flat_values_regex(self, filepath: str) -> dict[str, str]:
        """Fallback regex parser for simple YAML."""
        flat: dict[str, str] = {}
        try:
            content = Path(filepath).read_text(encoding="utf-8")
        except OSError:
            return flat
        for line in content.splitlines():
            m = re.match(r"^(\s*)(\w[\w.-]*):\s+(.+)$", line)
            if m:
                key = m.group(2)
                val = m.group(3).strip()
                flat[key] = val
        return flat

    def _flatten(self, data: dict, prefix: str, out: dict[str, str]) -> None:
        """Recursively flatten nested dict to dotted keys."""
        if not isinstance(data, dict):
            out[prefix] = str(data)
            return
        for k, v in data.items():
            full_key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                self._flatten(v, full_key, out)
            else:
                out[full_key] = str(v)

    def _check_rendered(self, templates: dict[str, str]) -> list[str]:
        """Check rendered templates for common issues."""
        warnings = []
        for name, content in templates.items():
            if "<nil>" in content:
                warnings.append(f"{name}: contains <nil> — missing value?")
            if "RELEASE-NAME" in content:
                warnings.append(f"{name}: contains unreplaced RELEASE-NAME placeholder")
        return warnings

    @staticmethod
    def _suggest_fix(error_msg: str) -> str:
        """Suggest a fix based on error message patterns."""
        msg = error_msg.lower()
        if "nil pointer" in msg or "nil dereference" in msg:
            return "Add a nil check: {{ if .Values.key }}...{{ end }}"
        if "not defined" in msg:
            return "Ensure the value is defined in values.yaml or use 'default'"
        if "wrong type" in msg:
            return "Check the expected type in the template vs the value provided"
        return "Review the template syntax around the reported line"

    @staticmethod
    def _mismatch_severity(key: str, left: str, right: str) -> str:
        """Determine severity of a value mismatch."""
        sensitive = {"password", "secret", "token", "key", "credentials"}
        if any(s in key.lower() for s in sensitive):
            return "error"
        resource = {"replicas", "cpu", "memory", "limit", "request"}
        if any(s in key.lower() for s in resource):
            return "warning"
        return "info"
