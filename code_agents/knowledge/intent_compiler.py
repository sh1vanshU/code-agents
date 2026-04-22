"""Intent compiler — plain English feature description to implementation plan.

Translates a natural-language feature request into a structured implementation
plan spanning UI, API, service, data, and test layers.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("code_agents.knowledge.intent_compiler")

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
}

# Layer keywords for classification
LAYER_KEYWORDS = {
    "ui": {"component", "page", "template", "view", "render", "form", "button", "modal", "display"},
    "api": {"endpoint", "route", "handler", "request", "response", "rest", "graphql", "grpc"},
    "service": {"service", "logic", "business", "process", "workflow", "validate", "calculate"},
    "data": {"model", "schema", "database", "table", "column", "migration", "query", "index"},
    "test": {"test", "spec", "fixture", "mock", "assert", "verify", "expect"},
    "config": {"config", "setting", "env", "environment", "variable", "flag", "toggle"},
}

# Action verb extraction
ACTION_VERBS = {
    "create": "new file/class/function",
    "add": "extend existing module",
    "update": "modify existing code",
    "remove": "delete code/feature",
    "fix": "bug fix in existing code",
    "refactor": "restructure without behavior change",
    "migrate": "data/code migration",
    "integrate": "connect with external system",
}


@dataclass
class PlanStep:
    """A single step in the implementation plan."""

    layer: str = ""  # ui | api | service | data | test | config
    action: str = ""  # create | update | add | remove
    target_file: str = ""  # Suggested file path
    description: str = ""
    dependencies: list[str] = field(default_factory=list)
    estimated_complexity: str = "medium"  # low | medium | high
    order: int = 0


@dataclass
class IntentResult:
    """Result of intent compilation."""

    intent_summary: str = ""
    layers_affected: list[str] = field(default_factory=list)
    steps: list[PlanStep] = field(default_factory=list)
    affected_files: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    estimated_effort: str = "medium"  # small | medium | large | epic


class IntentCompiler:
    """Compile natural-language feature descriptions into implementation plans."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        self._file_index: dict[str, list[str]] | None = None
        logger.debug("IntentCompiler initialized for %s", cwd)

    def compile(self, description: str) -> IntentResult:
        """Compile a feature description into an implementation plan.

        Args:
            description: Plain English feature description.

        Returns:
            IntentResult with layered steps and estimates.
        """
        result = IntentResult()
        logger.info("Compiling intent: %s", description[:80])

        # Parse intent
        result.intent_summary = self._summarize_intent(description)
        result.layers_affected = self._identify_layers(description)
        action = self._identify_action(description)

        # Build file index for matching
        if self._file_index is None:
            self._file_index = self._build_file_index()

        # Generate steps per layer
        order = 0
        for layer in self._plan_order(result.layers_affected):
            order += 1
            step = self._generate_step(description, layer, action, order)
            result.steps.append(step)

        # Find affected files
        result.affected_files = self._find_affected_files(description)

        # Assess risks
        result.risks = self._assess_risks(description, result.layers_affected)

        # Estimate effort
        result.estimated_effort = self._estimate_effort(result.steps, result.risks)

        logger.info(
            "Compiled %d steps across %d layers, effort=%s",
            len(result.steps), len(result.layers_affected), result.estimated_effort,
        )
        return result

    def _summarize_intent(self, description: str) -> str:
        """Create a one-line summary of the intent."""
        # Take first sentence or first 120 chars
        sentences = re.split(r"[.!?]\s", description)
        summary = sentences[0].strip()
        if len(summary) > 120:
            summary = summary[:117] + "..."
        return summary

    def _identify_layers(self, description: str) -> list[str]:
        """Identify which architectural layers are affected."""
        desc_lower = description.lower()
        layers: list[str] = []
        for layer, keywords in LAYER_KEYWORDS.items():
            if any(kw in desc_lower for kw in keywords):
                layers.append(layer)
        # Always include test layer
        if "test" not in layers:
            layers.append("test")
        return layers or ["service", "test"]

    def _identify_action(self, description: str) -> str:
        """Identify the primary action verb."""
        desc_lower = description.lower()
        for verb in ACTION_VERBS:
            if verb in desc_lower:
                return verb
        return "add"

    def _plan_order(self, layers: list[str]) -> list[str]:
        """Order layers for implementation sequence."""
        priority = {"data": 0, "config": 1, "service": 2, "api": 3, "ui": 4, "test": 5}
        return sorted(layers, key=lambda x: priority.get(x, 3))

    def _generate_step(
        self, description: str, layer: str, action: str, order: int,
    ) -> PlanStep:
        """Generate a plan step for a specific layer."""
        target = self._suggest_target_file(description, layer)
        deps = []
        if layer == "api" and "service" in description.lower():
            deps.append("service layer")
        if layer == "test":
            deps.append("implementation layers")

        complexity = "low"
        if layer in ("service", "data"):
            complexity = "medium"
        if "migrate" in description.lower() or "refactor" in description.lower():
            complexity = "high"

        return PlanStep(
            layer=layer,
            action=action,
            target_file=target,
            description=f"{action.capitalize()} {layer} layer: "
                        f"{self._layer_description(description, layer)}",
            dependencies=deps,
            estimated_complexity=complexity,
            order=order,
        )

    def _layer_description(self, description: str, layer: str) -> str:
        """Generate layer-specific description from intent."""
        templates = {
            "ui": "Update UI components/views for the new feature",
            "api": "Add/update API endpoint(s) with request/response models",
            "service": "Implement business logic and validation",
            "data": "Create/update data models and migrations",
            "test": "Add unit and integration tests",
            "config": "Add configuration options and env variables",
        }
        return templates.get(layer, f"Implement {layer} changes")

    def _suggest_target_file(self, description: str, layer: str) -> str:
        """Suggest a target file based on layer and description."""
        if self._file_index is None:
            return f"{layer}/new_module.py"

        # Try to find matching existing file
        desc_words = set(re.findall(r"\b\w{3,}\b", description.lower()))
        best_match = ""
        best_score = 0

        for category, files in self._file_index.items():
            if layer not in category and category not in layer:
                continue
            for fpath in files:
                fname = Path(fpath).stem.lower()
                words = set(fname.split("_"))
                score = len(words & desc_words)
                if score > best_score:
                    best_score = score
                    best_match = fpath

        return best_match or f"{layer}/new_module.py"

    def _build_file_index(self) -> dict[str, list[str]]:
        """Build an index of files grouped by directory."""
        index: dict[str, list[str]] = {}
        for root, dirs, fnames in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in fnames:
                if fname.endswith(".py"):
                    rel = os.path.relpath(os.path.join(root, fname), self.cwd)
                    parts = rel.split(os.sep)
                    if len(parts) > 1:
                        category = parts[-2]
                    else:
                        category = "root"
                    index.setdefault(category, []).append(rel)
        return index

    def _find_affected_files(self, description: str) -> list[str]:
        """Find existing files likely affected by this intent."""
        if not self._file_index:
            return []

        desc_words = set(re.findall(r"\b\w{3,}\b", description.lower()))
        affected: list[str] = []

        for _category, files in self._file_index.items():
            for fpath in files:
                fname = Path(fpath).stem.lower()
                words = set(fname.split("_"))
                if len(words & desc_words) >= 2:
                    affected.append(fpath)

        return affected[:20]

    def _assess_risks(self, description: str, layers: list[str]) -> list[str]:
        """Assess implementation risks."""
        risks: list[str] = []
        desc_lower = description.lower()

        if "data" in layers and ("migrat" in desc_lower or "schema" in desc_lower):
            risks.append("Database migration required — test with production-like data")
        if len(layers) > 3:
            risks.append("Cross-cutting change spanning many layers — coordinate carefully")
        if "security" in desc_lower or "auth" in desc_lower:
            risks.append("Security-sensitive change — requires security review")
        if "performance" in desc_lower or "optimi" in desc_lower:
            risks.append("Performance change — benchmark before and after")
        if not risks:
            risks.append("Standard change — follow normal review process")

        return risks

    def _estimate_effort(self, steps: list[PlanStep], risks: list[str]) -> str:
        """Estimate overall effort."""
        high = sum(1 for s in steps if s.estimated_complexity == "high")
        med = sum(1 for s in steps if s.estimated_complexity == "medium")

        if high >= 2 or len(steps) > 5:
            return "epic"
        if high >= 1 or med >= 3 or len(risks) >= 3:
            return "large"
        if med >= 1 or len(steps) > 2:
            return "medium"
        return "small"


def compile_intent(cwd: str, description: str) -> dict:
    """Convenience function to compile a feature intent.

    Returns:
        Dict with steps, affected files, risks, and effort estimate.
    """
    compiler = IntentCompiler(cwd)
    result = compiler.compile(description)
    return {
        "intent_summary": result.intent_summary,
        "layers_affected": result.layers_affected,
        "steps": [
            {"layer": s.layer, "action": s.action, "target_file": s.target_file,
             "description": s.description, "complexity": s.estimated_complexity,
             "order": s.order}
            for s in result.steps
        ],
        "affected_files": result.affected_files,
        "risks": result.risks,
        "estimated_effort": result.estimated_effort,
    }
