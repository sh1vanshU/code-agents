"""Inverse coder — desired output/behavior to implementation approach.

Given a desired output, behavior, or system characteristic, reverse-engineers
the implementation approach, required components, and code structure.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("code_agents.knowledge.inverse_coder")

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
}

# Output type patterns
OUTPUT_PATTERNS = {
    "json_response": re.compile(r"\bjson\b|\bapi\b|\bresponse\b|\brendpoint\b", re.IGNORECASE),
    "file_output": re.compile(r"\bfile\b|\bwrite\b|\bcsv\b|\bexport\b|\bsave\b", re.IGNORECASE),
    "ui_render": re.compile(r"\bpage\b|\bcomponent\b|\brender\b|\bdisplay\b|\bhtml\b", re.IGNORECASE),
    "cli_output": re.compile(r"\bcommand\b|\bcli\b|\bterminal\b|\bprint\b|\boutput\b", re.IGNORECASE),
    "event": re.compile(r"\bevent\b|\bwebhook\b|\bnotif\b|\bmessage\b|\bqueue\b", re.IGNORECASE),
    "data_transform": re.compile(r"\btransform\b|\bconvert\b|\bparse\b|\bmap\b|\bfilter\b", re.IGNORECASE),
}

# Technology inference
TECH_HINTS = {
    "fastapi": ["FastAPI", "Pydantic", "uvicorn", "async def"],
    "flask": ["Flask", "Blueprint", "render_template"],
    "django": ["Django", "models.Model", "views", "urls"],
    "react": ["React", "useState", "useEffect", "JSX"],
    "cli": ["argparse", "click", "typer", "sys.argv"],
}


@dataclass
class ImplementationComponent:
    """A required implementation component."""

    name: str = ""
    component_type: str = ""  # model | service | handler | util | test
    description: str = ""
    suggested_file: str = ""
    dependencies: list[str] = field(default_factory=list)
    code_skeleton: str = ""
    order: int = 0


@dataclass
class InverseResult:
    """Result of inverse coding analysis."""

    output_type: str = ""
    behavior_summary: str = ""
    components: list[ImplementationComponent] = field(default_factory=list)
    data_flow: list[str] = field(default_factory=list)
    similar_patterns: list[dict] = field(default_factory=list)
    tech_stack: list[str] = field(default_factory=list)
    estimated_files: int = 0
    estimated_complexity: str = "medium"


class InverseCoder:
    """Reverse-engineer implementation from desired output/behavior."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.debug("InverseCoder initialized for %s", cwd)

    def reverse_engineer(
        self,
        desired_output: str,
        constraints: list[str] | None = None,
    ) -> InverseResult:
        """Reverse-engineer implementation from desired output.

        Args:
            desired_output: Description of what the code should produce/do.
            constraints: Technical or business constraints.

        Returns:
            InverseResult with components, data flow, and tech stack.
        """
        result = InverseResult()
        logger.info("Reverse-engineering: %s", desired_output[:80])

        # Classify output type
        result.output_type = self._classify_output(desired_output)
        result.behavior_summary = self._summarize_behavior(desired_output)

        # Detect existing tech stack
        result.tech_stack = self._detect_tech_stack()

        # Generate required components
        result.components = self._generate_components(
            desired_output, result.output_type, result.tech_stack, constraints or [],
        )

        # Build data flow
        result.data_flow = self._build_data_flow(result.components)

        # Find similar patterns in codebase
        result.similar_patterns = self._find_similar_patterns(desired_output)

        # Estimates
        result.estimated_files = len(result.components)
        result.estimated_complexity = self._estimate_complexity(
            result.components, constraints or [],
        )

        logger.info(
            "Reverse-engineered %d components, type=%s, complexity=%s",
            len(result.components), result.output_type, result.estimated_complexity,
        )
        return result

    def _classify_output(self, description: str) -> str:
        """Classify the type of desired output."""
        for output_type, pattern in OUTPUT_PATTERNS.items():
            if pattern.search(description):
                return output_type
        return "general"

    def _summarize_behavior(self, description: str) -> str:
        """Summarize the desired behavior."""
        sentences = re.split(r"[.!?]\s", description)
        return sentences[0].strip()[:150]

    def _detect_tech_stack(self) -> list[str]:
        """Detect the project's tech stack from existing code."""
        stack: list[str] = []
        # Check common indicator files
        indicators = {
            "pyproject.toml": "Python/Poetry",
            "requirements.txt": "Python/pip",
            "package.json": "Node.js",
            "Cargo.toml": "Rust",
            "go.mod": "Go",
            "pom.xml": "Java/Maven",
        }
        for fname, tech in indicators.items():
            if os.path.exists(os.path.join(self.cwd, fname)):
                stack.append(tech)

        # Scan a few source files for framework hints
        sample_files = self._sample_files(5)
        for fpath in sample_files:
            try:
                content = Path(fpath).read_text(errors="replace")[:2000]
            except OSError:
                continue
            for framework, markers in TECH_HINTS.items():
                if any(m in content for m in markers):
                    if framework not in stack:
                        stack.append(framework)

        return stack

    def _sample_files(self, count: int) -> list[str]:
        """Get a sample of source files."""
        files: list[str] = []
        for root, dirs, fnames in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in fnames:
                if fname.endswith(".py"):
                    files.append(os.path.join(root, fname))
                    if len(files) >= count:
                        return files
        return files

    def _generate_components(
        self,
        description: str,
        output_type: str,
        tech_stack: list[str],
        constraints: list[str],
    ) -> list[ImplementationComponent]:
        """Generate required implementation components."""
        components: list[ImplementationComponent] = []
        order = 0

        # Data model
        if any(kw in description.lower() for kw in ("data", "model", "schema", "store", "database")):
            order += 1
            components.append(ImplementationComponent(
                name="data_model",
                component_type="model",
                description="Data model/schema for the feature",
                suggested_file="models.py",
                code_skeleton="@dataclass\nclass FeatureModel:\n    pass",
                order=order,
            ))

        # Service/business logic (always needed)
        order += 1
        components.append(ImplementationComponent(
            name="service",
            component_type="service",
            description=f"Core logic to produce {output_type} output",
            suggested_file="service.py",
            dependencies=["data_model"] if any(c.name == "data_model" for c in components) else [],
            code_skeleton="class FeatureService:\n    def execute(self) -> dict:\n        pass",
            order=order,
        ))

        # Handler/endpoint based on output type
        handler_map = {
            "json_response": ("api_handler", "handler", "API endpoint handler", "router.py"),
            "file_output": ("file_writer", "util", "File output writer", "writer.py"),
            "ui_render": ("view", "handler", "UI view/component", "views.py"),
            "cli_output": ("cli_command", "handler", "CLI command handler", "cli.py"),
            "event": ("event_handler", "handler", "Event/webhook handler", "events.py"),
            "data_transform": ("transformer", "util", "Data transformer", "transformer.py"),
        }
        if output_type in handler_map:
            name, ctype, desc, fpath = handler_map[output_type]
            order += 1
            components.append(ImplementationComponent(
                name=name,
                component_type=ctype,
                description=desc,
                suggested_file=fpath,
                dependencies=["service"],
                order=order,
            ))

        # Tests
        order += 1
        components.append(ImplementationComponent(
            name="tests",
            component_type="test",
            description="Unit tests for the feature",
            suggested_file="test_feature.py",
            dependencies=[c.name for c in components],
            code_skeleton="class TestFeature:\n    def test_basic(self):\n        pass",
            order=order,
        ))

        return components

    def _build_data_flow(self, components: list[ImplementationComponent]) -> list[str]:
        """Build data flow description from components."""
        flow: list[str] = []
        for comp in sorted(components, key=lambda c: c.order):
            if comp.component_type == "test":
                continue
            flow.append(f"{comp.name} ({comp.component_type}): {comp.description}")
        return flow

    def _find_similar_patterns(self, description: str) -> list[dict]:
        """Find similar implementation patterns in the codebase."""
        patterns: list[dict] = []
        desc_words = set(re.findall(r"\b\w{4,}\b", description.lower()))

        for root, dirs, fnames in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in fnames:
                if not fname.endswith(".py"):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    head = Path(fpath).read_text(errors="replace")[:500]
                except OSError:
                    continue

                head_words = set(re.findall(r"\b\w{4,}\b", head.lower()))
                overlap = desc_words & head_words
                if len(overlap) >= 3:
                    rel = os.path.relpath(fpath, self.cwd)
                    patterns.append({
                        "file": rel,
                        "matching_concepts": list(overlap)[:5],
                        "relevance": len(overlap),
                    })

            if len(patterns) >= 10:
                break

        patterns.sort(key=lambda p: p["relevance"], reverse=True)
        return patterns[:5]

    def _estimate_complexity(
        self,
        components: list[ImplementationComponent],
        constraints: list[str],
    ) -> str:
        """Estimate implementation complexity."""
        comp_count = len(components)
        constraint_count = len(constraints)

        if comp_count > 5 or constraint_count > 3:
            return "high"
        if comp_count > 3 or constraint_count > 1:
            return "medium"
        return "low"


def inverse_code(
    cwd: str,
    desired_output: str,
    constraints: list[str] | None = None,
) -> dict:
    """Convenience function for inverse coding.

    Returns:
        Dict with components, data flow, tech stack, and estimates.
    """
    coder = InverseCoder(cwd)
    result = coder.reverse_engineer(desired_output, constraints=constraints)
    return {
        "output_type": result.output_type,
        "behavior_summary": result.behavior_summary,
        "components": [
            {"name": c.name, "type": c.component_type, "description": c.description,
             "suggested_file": c.suggested_file, "code_skeleton": c.code_skeleton}
            for c in result.components
        ],
        "data_flow": result.data_flow,
        "similar_patterns": result.similar_patterns,
        "tech_stack": result.tech_stack,
        "estimated_complexity": result.estimated_complexity,
    }
