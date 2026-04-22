"""Pattern Suggester — analyze code and suggest applicable design patterns.

Scans code for structural indicators that suggest a design pattern could
improve maintainability, extensibility, or readability. Provides concrete
refactoring suggestions with before/after examples.

Usage:
    from code_agents.reviews.pattern_suggester import PatternSuggester, PatternSuggesterConfig
    suggester = PatternSuggester(PatternSuggesterConfig(cwd="/path/to/repo"))
    result = suggester.analyze()
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.reviews.pattern_suggester")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PatternSuggesterConfig:
    cwd: str = "."
    max_files: int = 500
    min_confidence: str = "medium"  # low | medium | high


@dataclass
class PatternIndicator:
    """A code signal that suggests a design pattern."""
    file: str
    line: int
    indicator_type: str
    code: str = ""


@dataclass
class PatternSuggestion:
    """A suggested design pattern with refactoring guidance."""
    pattern_name: str
    file: str
    line: int
    confidence: str = "high"
    problem: str = ""
    solution: str = ""
    before_code: str = ""
    after_code: str = ""
    benefits: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)


@dataclass
class PatternSuggesterReport:
    """Full pattern suggestion analysis."""
    files_scanned: int = 0
    indicators_found: int = 0
    suggestions: list[PatternSuggestion] = field(default_factory=list)
    indicators: list[PatternIndicator] = field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------------
# Pattern detection rules
# ---------------------------------------------------------------------------

PATTERN_RULES: list[dict] = [
    # Factory pattern indicators
    {
        "name": "Factory",
        "pattern": re.compile(r"if\s+\w+\s*==\s*['\"](\w+)['\"].*:\s*\n\s*\w+\s*=\s*(\w+)\("),
        "indicator": "type_switch_creation",
        "problem": "Object creation conditional on type — duplicated and fragile",
        "solution": "Use a Factory function or registry dict to map types to constructors",
        "before": "if fmt == 'json':\n    parser = JSONParser()\nelif fmt == 'xml':\n    parser = XMLParser()",
        "after": "PARSERS = {'json': JSONParser, 'xml': XMLParser}\nparser = PARSERS[fmt]()",
        "benefits": ["Open/Closed Principle", "Easy to add new types", "No conditional duplication"],
    },
    # Strategy pattern indicators
    {
        "name": "Strategy",
        "pattern": re.compile(r"if\s+(?:mode|strategy|algorithm|method)\s*=="),
        "indicator": "algorithm_switch",
        "problem": "Algorithm selection via conditionals — hard to extend",
        "solution": "Use Strategy pattern: extract algorithms into interchangeable classes",
        "before": "if mode == 'fast':\n    result = quick_sort(data)\nelif mode == 'stable':\n    result = merge_sort(data)",
        "after": "class SortStrategy(Protocol):\n    def sort(self, data: list) -> list: ...\n\nsorter = strategies[mode]\nresult = sorter.sort(data)",
        "benefits": ["Swappable algorithms", "Testable in isolation", "Open for extension"],
    },
    # Observer pattern indicators
    {
        "name": "Observer",
        "pattern": re.compile(r"(?:notify|emit|fire|trigger|dispatch|publish)\s*\(\s*['\"](\w+)['\"]"),
        "indicator": "event_notification",
        "problem": "Manual event notification — consider formalising with Observer pattern",
        "solution": "Use an event bus or Observer interface for decoupled notification",
        "before": "def save(self):\n    self._db.save(self)\n    send_email(self.owner)\n    update_cache(self)",
        "after": "def save(self):\n    self._db.save(self)\n    self.notify('saved')  # observers handle side-effects",
        "benefits": ["Decoupled components", "Easy to add new reactions", "Single Responsibility"],
    },
    # Builder pattern indicators
    {
        "name": "Builder",
        "pattern": re.compile(r"def\s+\w+\([^)]{120,}\)"),
        "indicator": "many_params",
        "problem": "Constructor/function with many parameters — hard to use correctly",
        "solution": "Use Builder pattern for step-by-step construction",
        "before": "def create_report(title, subtitle, author, date, format, template, logo, footer, pages):",
        "after": "report = ReportBuilder()\\\n    .title('Q4 Report')\\\n    .author('Team')\\\n    .format('pdf')\\\n    .build()",
        "benefits": ["Readable construction", "Optional parameters", "Validation at build time"],
    },
    # Singleton indicators (often anti-pattern)
    {
        "name": "Singleton (caution)",
        "pattern": re.compile(r"_instance\s*=\s*None|__instance\s*=\s*None"),
        "indicator": "singleton_impl",
        "problem": "Manual singleton — consider if module-level instance or DI is simpler",
        "solution": "In Python, a module-level instance is a natural singleton. Use DI for testability.",
        "before": "class DB:\n    _instance = None\n    @classmethod\n    def get(cls):\n        if not cls._instance:\n            cls._instance = cls()\n        return cls._instance",
        "after": "# Module-level singleton\ndb = Database(config)\n\n# Or with DI:\ndef get_db() -> Database:\n    return _db_instance",
        "benefits": ["Simpler code", "Testable via DI", "No hidden global state"],
    },
    # Decorator pattern indicators
    {
        "name": "Decorator",
        "pattern": re.compile(r"class\s+\w+Wrapper|class\s+\w+Decorator|def\s+\w+_wrapper"),
        "indicator": "wrapper_class",
        "problem": "Wrapper/decorator class found — verify it follows the Decorator pattern cleanly",
        "solution": "Ensure the decorator implements the same interface as the wrapped component",
        "before": "class LoggingWrapper:\n    def __init__(self, inner):\n        self.inner = inner\n    def execute(self, *args):\n        log('before')\n        result = self.inner.execute(*args)\n        log('after')\n        return result",
        "after": "# Same pattern, but ensure LoggingWrapper implements the same Protocol as inner",
        "benefits": ["Composable behaviors", "Open/Closed Principle", "Runtime flexibility"],
    },
    # Template Method indicators
    {
        "name": "Template Method",
        "pattern": re.compile(r"raise\s+NotImplementedError"),
        "indicator": "abstract_method",
        "problem": "Abstract methods suggest Template Method or Strategy pattern",
        "solution": "Ensure base class defines the algorithm skeleton, subclasses fill in steps",
        "before": "class BaseProcessor:\n    def process(self):\n        self.validate()  # subclass\n        self.execute()   # subclass\n        self.cleanup()   # shared",
        "after": "# Same structure — make sure process() is final and steps are overridable",
        "benefits": ["Code reuse", "Consistent algorithm structure", "Controlled extension points"],
    },
]


# ---------------------------------------------------------------------------
# PatternSuggester
# ---------------------------------------------------------------------------


class PatternSuggester:
    """Analyze code and suggest applicable design patterns."""

    def __init__(self, config: Optional[PatternSuggesterConfig] = None):
        self.config = config or PatternSuggesterConfig()

    def analyze(self) -> PatternSuggesterReport:
        """Run pattern analysis on codebase."""
        logger.info("Starting pattern analysis in %s", self.config.cwd)
        report = PatternSuggesterReport()
        root = Path(self.config.cwd)

        count = 0
        for ext in ("*.py", "*.js", "*.ts"):
            for fpath in root.rglob(ext):
                if count >= self.config.max_files:
                    break
                count += 1
                if any(p.startswith(".") or p in ("node_modules", "__pycache__", ".venv") for p in fpath.parts):
                    continue
                rel = str(fpath.relative_to(root))
                try:
                    lines = fpath.read_text(errors="replace").splitlines()
                except Exception:
                    continue
                for idx, line in enumerate(lines, 1):
                    for rule in PATTERN_RULES:
                        if rule["pattern"].search(line):
                            report.indicators.append(PatternIndicator(
                                file=rel, line=idx,
                                indicator_type=rule["indicator"],
                                code=line.strip(),
                            ))
                            report.suggestions.append(PatternSuggestion(
                                pattern_name=rule["name"],
                                file=rel, line=idx,
                                confidence="high",
                                problem=rule["problem"],
                                solution=rule["solution"],
                                before_code=rule["before"],
                                after_code=rule["after"],
                                benefits=rule["benefits"],
                            ))

        report.files_scanned = count
        report.indicators_found = len(report.indicators)
        report.summary = (
            f"Scanned {report.files_scanned} files, {report.indicators_found} pattern indicators, "
            f"{len(report.suggestions)} design pattern suggestions."
        )
        logger.info("Pattern analysis complete: %s", report.summary)
        return report


def format_pattern_report(report: PatternSuggesterReport) -> str:
    """Render pattern suggestion report."""
    lines = ["=== Pattern Suggester Report ===", ""]
    lines.append(f"Files scanned:    {report.files_scanned}")
    lines.append(f"Indicators:       {report.indicators_found}")
    lines.append(f"Suggestions:      {len(report.suggestions)}")
    lines.append("")

    for s in report.suggestions:
        lines.append(f"  [{s.pattern_name}] {s.file}:{s.line}")
        lines.append(f"    Problem:  {s.problem}")
        lines.append(f"    Solution: {s.solution}")
        lines.append(f"    Benefits: {', '.join(s.benefits)}")
        if s.before_code:
            lines.append(f"    Before:")
            for bl in s.before_code.splitlines():
                lines.append(f"      {bl}")
        if s.after_code:
            lines.append(f"    After:")
            for al in s.after_code.splitlines():
                lines.append(f"      {al}")
        lines.append("")

    lines.append(report.summary)
    return "\n".join(lines)
