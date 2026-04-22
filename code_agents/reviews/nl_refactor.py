"""NL Refactor — natural language refactoring commands to semantic transforms."""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.reviews.nl_refactor")


@dataclass
class RefactorIntent:
    """Parsed intent from NL refactor command."""
    action: str = ""  # rename, extract, inline, convert, move, restructure
    scope: str = ""  # file, directory, module, class, function
    target_pattern: str = ""
    replacement_pattern: str = ""
    scope_filter: str = ""  # e.g., "in payments module"
    confidence: float = 0.0
    raw_command: str = ""


@dataclass
class RefactorChange:
    """A single refactoring change."""
    file_path: str = ""
    line_number: int = 0
    original: str = ""
    refactored: str = ""
    change_type: str = ""  # rename, restructure, format, extract


@dataclass
class RefactorPlan:
    """Complete refactoring plan."""
    intent: RefactorIntent = field(default_factory=RefactorIntent)
    changes: list[RefactorChange] = field(default_factory=list)
    files_affected: int = 0
    total_changes: int = 0
    preview: list[str] = field(default_factory=list)
    reversible: bool = True


@dataclass
class NLRefactorReport:
    """Report from NL refactor analysis."""
    plan: Optional[RefactorPlan] = None
    parsed_intent: Optional[RefactorIntent] = None
    ambiguities: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    success: bool = True


ACTION_PATTERNS = {
    "rename": re.compile(r"\b(rename|change\s+name|reName)\b", re.IGNORECASE),
    "convert": re.compile(r"\b(convert|transform|change|switch)\b", re.IGNORECASE),
    "extract": re.compile(r"\b(extract|pull\s+out|separate|split)\b", re.IGNORECASE),
    "inline": re.compile(r"\b(inline|merge|combine|flatten)\b", re.IGNORECASE),
    "move": re.compile(r"\b(move|relocate|transfer)\b", re.IGNORECASE),
}

NAMING_CONVENTIONS = {
    "camelCase": re.compile(r"\bcamel\s*case\b", re.IGNORECASE),
    "snake_case": re.compile(r"\bsnake\s*[_-]?\s*case\b", re.IGNORECASE),
    "PascalCase": re.compile(r"\bpascal\s*case\b", re.IGNORECASE),
    "UPPER_CASE": re.compile(r"\bupper\s*(?:_?\s*case|snake)\b", re.IGNORECASE),
    "kebab-case": re.compile(r"\bkebab\s*[_-]?\s*case\b", re.IGNORECASE),
}

SCOPE_PATTERNS = {
    "in": re.compile(r"\bin\s+(?:the\s+)?(\w[\w./]*)", re.IGNORECASE),
    "across": re.compile(r"\bacross\s+(?:the\s+)?(\w[\w./]*)", re.IGNORECASE),
    "under": re.compile(r"\bunder\s+(?:the\s+)?(\w[\w./]*)", re.IGNORECASE),
}


class NLRefactor:
    """Parses NL refactoring commands and generates transform plans."""

    def __init__(self, cwd: str):
        self.cwd = cwd

    def analyze(self, command: str,
                file_contents: Optional[dict[str, str]] = None) -> NLRefactorReport:
        """Parse NL refactor command and generate plan."""
        logger.info("Parsing refactor command: %s", command[:80])
        file_contents = file_contents or {}

        # Phase 1: Parse intent
        intent = self._parse_intent(command)

        # Phase 2: Check ambiguities
        ambiguities = self._check_ambiguities(intent)

        # Phase 3: Generate plan
        plan = None
        if intent.action and not ambiguities:
            plan = self._generate_plan(intent, file_contents)

        report = NLRefactorReport(
            plan=plan,
            parsed_intent=intent,
            ambiguities=ambiguities,
            warnings=self._generate_warnings(intent, plan),
            success=plan is not None and plan.total_changes > 0,
        )
        logger.info("Refactor: action=%s, changes=%d",
                     intent.action, plan.total_changes if plan else 0)
        return report

    def _parse_intent(self, command: str) -> RefactorIntent:
        """Parse NL command into refactor intent."""
        intent = RefactorIntent(raw_command=command)
        confidence = 0.0

        # Detect action
        for action, pattern in ACTION_PATTERNS.items():
            if pattern.search(command):
                intent.action = action
                confidence += 0.3
                break

        # Detect naming convention transforms
        source_conv = None
        target_conv = None
        for conv, pattern in NAMING_CONVENTIONS.items():
            matches = list(pattern.finditer(command))
            if matches:
                if source_conv is None:
                    source_conv = conv
                else:
                    target_conv = conv

        if source_conv and target_conv:
            intent.target_pattern = source_conv
            intent.replacement_pattern = target_conv
            if not intent.action:
                intent.action = "convert"
            confidence += 0.3
        elif source_conv and "to" in command.lower():
            intent.target_pattern = source_conv
            confidence += 0.2

        # Detect scope
        for scope_type, pattern in SCOPE_PATTERNS.items():
            m = pattern.search(command)
            if m:
                intent.scope_filter = m.group(1)
                confidence += 0.2
                break

        intent.confidence = min(1.0, confidence)
        return intent

    def _check_ambiguities(self, intent: RefactorIntent) -> list[str]:
        ambiguities = []
        if not intent.action:
            ambiguities.append("Could not determine refactoring action")
        if intent.action == "convert" and not intent.replacement_pattern:
            ambiguities.append("Target convention not specified (e.g., 'to snake_case')")
        return ambiguities

    def _generate_plan(self, intent: RefactorIntent,
                       files: dict[str, str]) -> RefactorPlan:
        """Generate refactoring plan."""
        changes = []

        # Filter files by scope
        filtered = self._filter_files(files, intent.scope_filter)

        if intent.action == "convert" or intent.action == "rename":
            changes = self._plan_naming_changes(intent, filtered)

        elif intent.action == "extract":
            changes = self._plan_extract(intent, filtered)

        files_affected = len(set(c.file_path for c in changes))
        preview = [f"{c.file_path}:{c.line_number}: {c.original} -> {c.refactored}"
                   for c in changes[:10]]

        return RefactorPlan(
            intent=intent,
            changes=changes,
            files_affected=files_affected,
            total_changes=len(changes),
            preview=preview,
        )

    def _filter_files(self, files: dict[str, str], scope: str) -> dict[str, str]:
        """Filter files by scope pattern."""
        if not scope:
            return files
        return {k: v for k, v in files.items() if scope.lower() in k.lower()}

    def _plan_naming_changes(self, intent: RefactorIntent,
                             files: dict[str, str]) -> list[RefactorChange]:
        """Plan naming convention changes."""
        changes = []
        source = intent.target_pattern
        target = intent.replacement_pattern

        for fpath, content in files.items():
            lines = content.splitlines()
            for i, line in enumerate(lines):
                identifiers = re.findall(r"\b([a-zA-Z_]\w*)\b", line)
                for ident in identifiers:
                    if self._matches_convention(ident, source):
                        converted = self._convert_name(ident, target)
                        if converted != ident:
                            changes.append(RefactorChange(
                                file_path=fpath,
                                line_number=i + 1,
                                original=ident,
                                refactored=converted,
                                change_type="rename",
                            ))
        return changes

    def _plan_extract(self, intent: RefactorIntent,
                      files: dict[str, str]) -> list[RefactorChange]:
        """Plan extraction refactoring."""
        # Simplified: identify long functions to extract from
        changes = []
        for fpath, content in files.items():
            for m in re.finditer(r"def\s+(\w+)", content):
                func_start = content[:m.start()].count("\n") + 1
                changes.append(RefactorChange(
                    file_path=fpath,
                    line_number=func_start,
                    original=m.group(1),
                    refactored=f"extracted_{m.group(1)}",
                    change_type="extract",
                ))
        return changes[:20]

    def _matches_convention(self, name: str, convention: str) -> bool:
        """Check if name matches a naming convention."""
        if convention == "camelCase":
            return bool(re.match(r"^[a-z][a-zA-Z0-9]*$", name)) and any(c.isupper() for c in name)
        if convention == "snake_case":
            return "_" in name and name == name.lower()
        if convention == "PascalCase":
            return bool(re.match(r"^[A-Z][a-zA-Z0-9]*$", name))
        if convention == "UPPER_CASE":
            return "_" in name and name == name.upper()
        return False

    def _convert_name(self, name: str, target: str) -> str:
        """Convert name to target convention."""
        # Split into words
        if "_" in name:
            words = name.lower().split("_")
        else:
            words = re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?=[A-Z][a-z]|\b)", name)
            words = [w.lower() for w in words]

        if not words:
            return name

        if target == "snake_case":
            return "_".join(words)
        if target == "camelCase":
            return words[0] + "".join(w.capitalize() for w in words[1:])
        if target == "PascalCase":
            return "".join(w.capitalize() for w in words)
        if target == "UPPER_CASE":
            return "_".join(w.upper() for w in words)
        if target == "kebab-case":
            return "-".join(words)
        return name

    def _generate_warnings(self, intent: RefactorIntent,
                           plan: Optional[RefactorPlan]) -> list[str]:
        warnings = []
        if plan and plan.total_changes > 100:
            warnings.append(f"Large refactor ({plan.total_changes} changes) — review carefully")
        if intent.confidence < 0.5:
            warnings.append("Low confidence in intent parsing — verify before applying")
        return warnings


def format_report(report: NLRefactorReport) -> str:
    lines = ["# NL Refactor Report"]
    if report.parsed_intent:
        lines.append(f"Action: {report.parsed_intent.action} | Confidence: {report.parsed_intent.confidence:.0%}")
    if report.plan:
        lines.append(f"Changes: {report.plan.total_changes} in {report.plan.files_affected} files")
        lines.append("\n## Preview")
        for p in report.plan.preview:
            lines.append(f"  {p}")
    return "\n".join(lines)
