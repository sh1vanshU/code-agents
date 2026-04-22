"""Teach Mode — explain concepts with alternatives, examples, and guided learning.

Provides structured educational explanations of programming concepts,
design patterns, and architecture decisions with code examples,
alternative approaches, and progressive learning paths.

Usage:
    from code_agents.knowledge.teach_mode import TeachMode, TeachModeConfig
    teacher = TeachMode(TeachModeConfig())
    result = teacher.explain("dependency injection")
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.knowledge.teach_mode")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class TeachModeConfig:
    cwd: str = "."
    level: str = "intermediate"  # "beginner", "intermediate", "advanced"
    include_examples: bool = True
    include_alternatives: bool = True
    max_examples: int = 3


@dataclass
class CodeExample:
    """A code example illustrating a concept."""
    title: str
    language: str = "python"
    code: str = ""
    explanation: str = ""
    when_to_use: str = ""


@dataclass
class Alternative:
    """An alternative approach to the same problem."""
    name: str
    description: str
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)
    best_for: str = ""


@dataclass
class LearningStep:
    """A step in a guided learning path."""
    order: int
    title: str
    description: str
    exercise: str = ""
    resource: str = ""


@dataclass
class Explanation:
    """A structured concept explanation."""
    concept: str
    summary: str
    detailed: str = ""
    level: str = "intermediate"
    examples: list[CodeExample] = field(default_factory=list)
    alternatives: list[Alternative] = field(default_factory=list)
    learning_path: list[LearningStep] = field(default_factory=list)
    related_concepts: list[str] = field(default_factory=list)
    common_mistakes: list[str] = field(default_factory=list)


@dataclass
class TeachModeReport:
    """Full teach mode result."""
    concept: str = ""
    explanation: Optional[Explanation] = None
    codebase_examples: list[str] = field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------------
# Concept knowledge base
# ---------------------------------------------------------------------------

CONCEPTS: dict[str, dict] = {
    "dependency injection": {
        "summary": "Pass dependencies to a component instead of having it create them internally.",
        "detailed": (
            "Dependency Injection (DI) inverts the control of dependency creation. "
            "Instead of a class creating its own dependencies, they are provided (injected) "
            "from outside. This makes code more testable, flexible, and loosely coupled."
        ),
        "examples": [
            CodeExample(
                title="Constructor injection",
                code=(
                    "class OrderService:\n"
                    "    def __init__(self, db: Database, mailer: Mailer):\n"
                    "        self._db = db\n"
                    "        self._mailer = mailer\n\n"
                    "# In production:\n"
                    "svc = OrderService(PostgresDB(), SMTPMailer())\n"
                    "# In tests:\n"
                    "svc = OrderService(FakeDB(), FakeMailer())"
                ),
                explanation="Dependencies are passed via constructor, making them explicit and testable.",
                when_to_use="Most common pattern. Use when dependencies are required for the lifetime of the object.",
            ),
            CodeExample(
                title="Function parameter injection",
                code=(
                    "def process_order(order, send_email=send_real_email):\n"
                    "    # ... process ...\n"
                    "    send_email(order.customer, 'Order confirmed')\n\n"
                    "# In tests:\n"
                    "process_order(order, send_email=mock_send)"
                ),
                explanation="Pass dependencies as function parameters with sensible defaults.",
                when_to_use="For simple functions that need one or two dependencies.",
            ),
        ],
        "alternatives": [
            Alternative(
                name="Service Locator",
                description="Central registry that components query for dependencies.",
                pros=["Simple to implement", "No framework needed"],
                cons=["Hidden dependencies", "Harder to test"],
                best_for="Legacy codebases or simple applications",
            ),
            Alternative(
                name="Module-level injection",
                description="Use module imports as the injection mechanism.",
                pros=["Pythonic", "No extra framework"],
                cons=["Hard to override in tests without monkeypatching"],
                best_for="Small Python projects",
            ),
        ],
        "related": ["inversion of control", "SOLID principles", "factory pattern", "service locator"],
        "mistakes": [
            "Injecting too many dependencies (> 5 suggests the class does too much)",
            "Using a DI framework when simple constructor injection suffices",
            "Not providing default implementations for optional dependencies",
        ],
        "learning_path": [
            LearningStep(1, "Understand the problem", "Write a class with hardcoded dependencies and try to test it."),
            LearningStep(2, "Extract dependencies", "Move dependency creation outside the class."),
            LearningStep(3, "Use interfaces", "Define protocols/ABCs for dependencies."),
            LearningStep(4, "Explore frameworks", "Try a DI container (e.g., dependency-injector, inject)."),
        ],
    },
    "factory pattern": {
        "summary": "Encapsulate object creation logic, letting subclasses or config decide which class to instantiate.",
        "detailed": (
            "The Factory pattern provides an interface for creating objects without specifying "
            "their exact class. It centralises creation logic and supports the Open/Closed Principle."
        ),
        "examples": [
            CodeExample(
                title="Simple factory function",
                code=(
                    "def create_parser(file_type: str) -> Parser:\n"
                    "    parsers = {'json': JSONParser, 'xml': XMLParser, 'csv': CSVParser}\n"
                    "    cls = parsers.get(file_type)\n"
                    "    if not cls:\n"
                    "        raise ValueError(f'Unknown type: {file_type}')\n"
                    "    return cls()"
                ),
                explanation="A function maps type identifiers to concrete classes.",
                when_to_use="When you have a fixed set of types and want clean creation logic.",
            ),
        ],
        "alternatives": [
            Alternative(
                name="Abstract Factory",
                description="Family of related factories for creating groups of objects.",
                pros=["Consistent object families", "Swappable implementations"],
                cons=["More classes to maintain"],
                best_for="When you need to create families of related objects",
            ),
        ],
        "related": ["abstract factory", "builder pattern", "dependency injection"],
        "mistakes": [
            "Over-engineering with factories when a simple constructor suffices",
            "Not using a registry/map — long if/elif chains defeat the purpose",
        ],
        "learning_path": [
            LearningStep(1, "Spot the need", "Notice when creation logic has conditionals on type."),
            LearningStep(2, "Extract to function", "Move creation into a factory function."),
            LearningStep(3, "Use registry", "Replace if/elif with a dictionary mapping."),
        ],
    },
    "strategy pattern": {
        "summary": "Define a family of algorithms, encapsulate each one, and make them interchangeable.",
        "detailed": (
            "The Strategy pattern lets you select an algorithm at runtime. Each strategy "
            "implements a common interface, and the context delegates work to the active strategy."
        ),
        "examples": [
            CodeExample(
                title="Strategy with Protocol",
                code=(
                    "from typing import Protocol\n\n"
                    "class SortStrategy(Protocol):\n"
                    "    def sort(self, data: list) -> list: ...\n\n"
                    "class QuickSort:\n"
                    "    def sort(self, data: list) -> list:\n"
                    "        return sorted(data)  # simplified\n\n"
                    "class BubbleSort:\n"
                    "    def sort(self, data: list) -> list:\n"
                    "        # ... bubble sort impl\n"
                    "        return data\n\n"
                    "class Sorter:\n"
                    "    def __init__(self, strategy: SortStrategy):\n"
                    "        self._strategy = strategy\n\n"
                    "    def execute(self, data: list) -> list:\n"
                    "        return self._strategy.sort(data)"
                ),
                explanation="Different sorting strategies share a Protocol, swappable at runtime.",
                when_to_use="When you have multiple algorithms for the same task.",
            ),
        ],
        "alternatives": [
            Alternative(
                name="Function as strategy",
                description="Pass a callable instead of a class.",
                pros=["Simpler", "Pythonic"],
                cons=["Less structured for complex strategies"],
                best_for="Simple algorithms with no state",
            ),
        ],
        "related": ["template method", "state pattern", "command pattern"],
        "mistakes": ["Using strategy for a single algorithm", "Not defining a clear interface"],
        "learning_path": [
            LearningStep(1, "Identify algorithm families", "Find places where you switch between algorithms."),
            LearningStep(2, "Define interface", "Create a Protocol or ABC."),
            LearningStep(3, "Implement strategies", "One class per algorithm variant."),
        ],
    },
}

# Keyword aliases for concept lookup
CONCEPT_ALIASES: dict[str, str] = {
    "di": "dependency injection",
    "injection": "dependency injection",
    "factory": "factory pattern",
    "strategy": "strategy pattern",
    "observer": "strategy pattern",  # placeholder — would have its own entry
}


# ---------------------------------------------------------------------------
# TeachMode
# ---------------------------------------------------------------------------


class TeachMode:
    """Explain concepts with examples, alternatives, and guided learning."""

    def __init__(self, config: Optional[TeachModeConfig] = None):
        self.config = config or TeachModeConfig()

    def explain(self, concept: str) -> TeachModeReport:
        """Generate a structured explanation for a concept."""
        logger.info("Teaching concept: %s", concept)
        report = TeachModeReport(concept=concept)

        # Normalise and look up
        key = concept.lower().strip()
        key = CONCEPT_ALIASES.get(key, key)

        data = CONCEPTS.get(key)
        if not data:
            # Fuzzy match
            for k in CONCEPTS:
                if key in k or k in key:
                    data = CONCEPTS[k]
                    key = k
                    break

        if not data:
            report.summary = f"Concept '{concept}' not found in knowledge base."
            report.explanation = Explanation(
                concept=concept,
                summary=f"No built-in explanation for '{concept}'. Try a more specific term.",
                level=self.config.level,
            )
            return report

        examples = data.get("examples", [])
        if not self.config.include_examples:
            examples = []
        examples = examples[: self.config.max_examples]

        alternatives = data.get("alternatives", [])
        if not self.config.include_alternatives:
            alternatives = []

        explanation = Explanation(
            concept=key,
            summary=data["summary"],
            detailed=data.get("detailed", ""),
            level=self.config.level,
            examples=examples,
            alternatives=alternatives,
            learning_path=data.get("learning_path", []),
            related_concepts=data.get("related", []),
            common_mistakes=data.get("mistakes", []),
        )
        report.explanation = explanation

        # Search codebase for real examples
        report.codebase_examples = self._find_codebase_examples(key)

        report.summary = (
            f"Explained '{key}' with {len(examples)} examples, "
            f"{len(alternatives)} alternatives, "
            f"{len(explanation.learning_path)} learning steps."
        )
        logger.info("Teach mode complete: %s", report.summary)
        return report

    def _find_codebase_examples(self, concept: str) -> list[str]:
        """Search codebase for files that demonstrate the concept."""
        root = Path(self.config.cwd)
        examples: list[str] = []
        keywords = concept.split()

        count = 0
        for fpath in root.rglob("*.py"):
            if count >= 200:
                break
            if any(p.startswith(".") or p in ("node_modules", "__pycache__", ".venv") for p in fpath.parts):
                continue
            count += 1
            rel = str(fpath.relative_to(root))
            try:
                content = fpath.read_text(errors="replace").lower()
            except Exception:
                continue
            if any(kw in content for kw in keywords):
                examples.append(rel)
            if len(examples) >= 5:
                break
        return examples


def format_teach_report(report: TeachModeReport) -> str:
    """Render teach mode report."""
    lines = ["=== Teach Mode ===", ""]
    exp = report.explanation
    if not exp:
        lines.append(report.summary)
        return "\n".join(lines)

    lines.append(f"Concept: {exp.concept}")
    lines.append(f"Level:   {exp.level}")
    lines.append("")
    lines.append(f"Summary: {exp.summary}")
    if exp.detailed:
        lines.append("")
        lines.append(exp.detailed)

    if exp.examples:
        lines.append("")
        lines.append("--- Examples ---")
        for ex in exp.examples:
            lines.append(f"\n  {ex.title}")
            for cl in ex.code.splitlines():
                lines.append(f"    {cl}")
            if ex.explanation:
                lines.append(f"  {ex.explanation}")

    if exp.alternatives:
        lines.append("")
        lines.append("--- Alternatives ---")
        for alt in exp.alternatives:
            lines.append(f"  {alt.name}: {alt.description}")
            for p in alt.pros:
                lines.append(f"    + {p}")
            for c in alt.cons:
                lines.append(f"    - {c}")

    if exp.common_mistakes:
        lines.append("")
        lines.append("--- Common Mistakes ---")
        for m in exp.common_mistakes:
            lines.append(f"  ! {m}")

    if exp.learning_path:
        lines.append("")
        lines.append("--- Learning Path ---")
        for step in exp.learning_path:
            lines.append(f"  {step.order}. {step.title}: {step.description}")

    if report.codebase_examples:
        lines.append("")
        lines.append("--- Codebase Examples ---")
        for ce in report.codebase_examples:
            lines.append(f"  {ce}")

    lines.append("")
    lines.append(report.summary)
    return "\n".join(lines)
