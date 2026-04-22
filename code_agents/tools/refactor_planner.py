"""Refactor Planner — analyzes code smells, suggests refactoring steps, estimates risk."""

import logging
import os
import re
import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.tools.refactor_planner")

# Thresholds
_MAX_METHOD_LINES = 50
_MAX_CLASS_LINES = 300
_MAX_PARAMS = 5
_MAX_NESTING = 4
_MAX_PUBLIC_METHODS = 10


@dataclass
class CodeSmell:
    """A single code smell detected in a file."""

    kind: str           # long_method, large_class, too_many_params, deep_nesting, god_class, duplicate_code, feature_envy, dead_code
    severity: str       # high, medium, low
    description: str
    location: str = ""  # function/class name or line range
    line: int = 0
    details: dict = field(default_factory=dict)


@dataclass
class RefactorSuggestion:
    """A refactoring suggestion for a detected smell."""

    smell: CodeSmell
    technique: str
    description: str
    risk: str       # Low, Medium, High
    effort: str     # e.g. "~30min", "~1h", "~2h"


@dataclass
class RefactorPlan:
    """Complete refactoring analysis for a file."""

    filepath: str
    smells: list[CodeSmell] = field(default_factory=list)
    suggestions: list[RefactorSuggestion] = field(default_factory=list)
    risk_score: int = 0
    dependents: int = 0
    test_files: int = 0
    critical_path: str = ""


# Smell kind -> (technique, description template, risk, effort)
_REFACTORING_MAP = {
    "long_method": ("Extract Method", "Break into smaller focused methods", "Low", "~1h"),
    "large_class": ("Extract Class / Single Responsibility", "Split into cohesive smaller classes", "Medium", "~2h"),
    "too_many_params": ("Parameter Object / Builder", "Group params into a DTO or use builder pattern", "Low", "~1h"),
    "deep_nesting": ("Early Return / Guard Clauses", "Flatten with early returns and guard clauses", "Low", "~30min"),
    "god_class": ("Split into focused services", "Extract logical groups of methods into separate services", "Medium", "~2h"),
    "duplicate_code": ("Extract to shared utility", "Move duplicate block into a helper function", "Low", "~30min"),
    "feature_envy": ("Move Method", "Move method closer to the data it uses", "Medium", "~1h"),
    "dead_code": ("Remove dead code", "Delete unreachable or unused code", "Low", "~15min"),
}


class RefactorPlanner:
    """Analyzes code smells and produces a refactoring plan."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.info("RefactorPlanner initialized — cwd=%s", cwd)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, filepath: str) -> RefactorPlan:
        """Detect code smells in a file and return a full refactoring plan."""
        abspath = self._resolve(filepath)
        if not os.path.isfile(abspath):
            logger.warning("File not found: %s", abspath)
            return RefactorPlan(filepath=filepath)

        content = Path(abspath).read_text(errors="replace")
        lines = content.splitlines()

        plan = RefactorPlan(filepath=filepath)

        # Run detectors
        plan.smells.extend(self._detect_long_methods(lines))
        plan.smells.extend(self._detect_large_classes(lines))
        plan.smells.extend(self._detect_too_many_params(lines))
        plan.smells.extend(self._detect_deep_nesting(lines))
        plan.smells.extend(self._detect_god_classes(lines))
        plan.smells.extend(self._detect_duplicate_code(lines))
        plan.smells.extend(self._detect_feature_envy(lines))
        plan.smells.extend(self._detect_dead_code(lines))

        # Sort by severity: high first
        severity_order = {"high": 0, "medium": 1, "low": 2}
        plan.smells.sort(key=lambda s: severity_order.get(s.severity, 9))

        # Generate suggestions
        plan.suggestions = self.suggest_refactoring(plan.smells)

        # Risk estimation
        risk = self.estimate_risk(filepath)
        plan.risk_score = risk["score"]
        plan.dependents = risk["dependents"]
        plan.test_files = risk["test_files"]
        plan.critical_path = risk["critical_path"]

        return plan

    def suggest_refactoring(self, smells: list[CodeSmell]) -> list[RefactorSuggestion]:
        """For each smell, suggest a refactoring technique."""
        suggestions = []
        for smell in smells:
            mapping = _REFACTORING_MAP.get(smell.kind)
            if mapping:
                technique, desc, risk, effort = mapping
                # Customize description based on smell details
                detail_desc = desc
                if smell.kind == "god_class" and smell.details.get("method_count"):
                    detail_desc = f"Extract logical groups from {smell.details['method_count']} public methods into separate services"
                elif smell.kind == "long_method" and smell.location:
                    detail_desc = f"Extract {smell.location}() into smaller steps"
                elif smell.kind == "too_many_params" and smell.location:
                    detail_desc = f"Create request DTO to replace {smell.details.get('param_count', '?')} params in {smell.location}()"

                suggestions.append(RefactorSuggestion(
                    smell=smell,
                    technique=technique,
                    description=detail_desc,
                    risk=risk,
                    effort=effort,
                ))
        return suggestions

    def estimate_risk(self, filepath: str) -> dict:
        """Estimate risk score: dependents, test coverage, critical path."""
        abspath = self._resolve(filepath)
        basename = os.path.basename(abspath)
        stem = Path(basename).stem

        dependents = 0
        test_files = 0
        critical_path = ""

        # Search for files that import/reference this file
        try:
            for root, dirs, files in os.walk(self.cwd):
                dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', 'node_modules', 'venv', '.venv', 'target', 'dist', 'build'}]
                for fname in files:
                    if not fname.endswith(('.py', '.java', '.ts', '.js', '.go', '.kt')):
                        continue
                    fpath = os.path.join(root, fname)
                    if fpath == abspath:
                        continue
                    try:
                        text = Path(fpath).read_text(errors="replace")
                    except (OSError, UnicodeDecodeError):
                        continue

                    # Check if this file references our target
                    if stem in text:
                        rel_root = os.path.relpath(root, self.cwd)
                        if "test" in fname.lower() or "test" in rel_root.lower():
                            test_files += 1
                        else:
                            dependents += 1
        except OSError:
            logger.debug("Could not walk %s for risk estimation", self.cwd)

        # Heuristic for critical path
        critical_keywords = ["payment", "auth", "login", "checkout", "order", "transaction", "security", "deploy", "database", "migration"]
        lower_stem = stem.lower()
        for kw in critical_keywords:
            if kw in lower_stem:
                critical_path = f"{kw} processing"
                break

        # Score: 0-100
        score = min(100, dependents * 6 + max(0, 30 - test_files * 10) + (30 if critical_path else 0))
        score = max(0, score)

        return {
            "score": score,
            "dependents": dependents,
            "test_files": test_files,
            "critical_path": critical_path,
        }

    def create_plan(self, filepath: str) -> RefactorPlan:
        """Alias for analyze — returns step-by-step refactoring plan."""
        return self.analyze(filepath)

    def format_analysis(self, plan: RefactorPlan) -> str:
        """Format analysis as terminal display string."""
        return format_refactor_plan(plan)

    # ------------------------------------------------------------------
    # Smell detectors
    # ------------------------------------------------------------------

    def _detect_long_methods(self, lines: list[str]) -> list[CodeSmell]:
        """Detect functions/methods longer than threshold."""
        smells = []
        functions = self._find_functions(lines)
        for name, start, end in functions:
            length = end - start + 1
            if length > _MAX_METHOD_LINES:
                smells.append(CodeSmell(
                    kind="long_method",
                    severity="medium",
                    description=f"{name}() is {length} lines (threshold: {_MAX_METHOD_LINES})",
                    location=name,
                    line=start + 1,
                    details={"line_count": length},
                ))
        return smells

    def _detect_large_classes(self, lines: list[str]) -> list[CodeSmell]:
        """Detect classes longer than threshold."""
        smells = []
        classes = self._find_classes(lines)
        for name, start, end in classes:
            length = end - start + 1
            if length > _MAX_CLASS_LINES:
                smells.append(CodeSmell(
                    kind="large_class",
                    severity="high",
                    description=f"{name} is {length} lines (threshold: {_MAX_CLASS_LINES})",
                    location=name,
                    line=start + 1,
                    details={"line_count": length},
                ))
        return smells

    def _detect_too_many_params(self, lines: list[str]) -> list[CodeSmell]:
        """Detect functions with too many parameters."""
        smells = []
        # Python: def func(a, b, c, d, e, f):
        # Java/TS: type func(Type a, Type b, ...){
        pat_py = re.compile(r'def\s+(\w+)\s*\(([^)]*)\)\s*[-:]')
        pat_java = re.compile(r'(?:public|private|protected|static|\s)*\s+\w+\s+(\w+)\s*\(([^)]*)\)\s*\{?')

        for i, line in enumerate(lines):
            for pat in (pat_py, pat_java):
                m = pat.search(line)
                if m:
                    name = m.group(1)
                    params_str = m.group(2).strip()
                    if not params_str or name in ("__init__",):
                        continue
                    # Filter out 'self', 'cls'
                    params = [p.strip() for p in params_str.split(",") if p.strip()]
                    params = [p for p in params if p not in ("self", "cls")]
                    if len(params) > _MAX_PARAMS:
                        smells.append(CodeSmell(
                            kind="too_many_params",
                            severity="low",
                            description=f"{name}({len(params)} params) (threshold: {_MAX_PARAMS})",
                            location=name,
                            line=i + 1,
                            details={"param_count": len(params)},
                        ))
                    break  # Only match first pattern per line
        return smells

    def _detect_deep_nesting(self, lines: list[str]) -> list[CodeSmell]:
        """Detect deeply nested blocks (indentation > threshold levels)."""
        smells = []
        # Track which function we're in
        current_func = None
        current_func_start = 0
        max_depth_per_func: dict[str, int] = {}

        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                continue

            # Track function context
            func_match = re.match(r'\s*def\s+(\w+)', line)
            if func_match:
                current_func = func_match.group(1)
                current_func_start = i

            if current_func:
                indent = len(line) - len(line.lstrip())
                # Estimate nesting level (4 spaces or 1 tab = 1 level)
                tab_size = 4
                level = indent // tab_size
                if level > max_depth_per_func.get(current_func, 0):
                    max_depth_per_func[current_func] = level

        for func_name, depth in max_depth_per_func.items():
            if depth > _MAX_NESTING:
                smells.append(CodeSmell(
                    kind="deep_nesting",
                    severity="medium",
                    description=f"{func_name}() has {depth} nesting levels (threshold: {_MAX_NESTING})",
                    location=func_name,
                    line=0,
                    details={"depth": depth},
                ))
        return smells

    def _detect_god_classes(self, lines: list[str]) -> list[CodeSmell]:
        """Detect classes with too many public methods."""
        smells = []
        classes = self._find_classes(lines)

        for class_name, start, end in classes:
            public_methods = 0
            for i in range(start, min(end + 1, len(lines))):
                line = lines[i].strip()
                # Python public methods
                if re.match(r'def\s+(?!_)\w+\s*\(', line):
                    public_methods += 1
                # Java/TS public methods
                elif re.match(r'public\s+\w+\s+\w+\s*\(', line):
                    public_methods += 1

            if public_methods > _MAX_PUBLIC_METHODS:
                smells.append(CodeSmell(
                    kind="god_class",
                    severity="high",
                    description=f"{class_name} has {public_methods} public methods (threshold: {_MAX_PUBLIC_METHODS})",
                    location=class_name,
                    line=start + 1,
                    details={"method_count": public_methods},
                ))
        return smells

    def _detect_duplicate_code(self, lines: list[str]) -> list[CodeSmell]:
        """Detect similar code blocks using hash-based comparison."""
        smells = []
        block_size = 5  # Lines per block
        seen_hashes: dict[str, int] = {}  # hash -> first occurrence line

        for i in range(len(lines) - block_size + 1):
            block = lines[i:i + block_size]
            # Normalize: strip whitespace, skip blank/comment-only blocks
            normalized = [l.strip() for l in block if l.strip() and not l.strip().startswith(("#", "//", "*", "/*"))]
            if len(normalized) < 3:
                continue
            block_hash = hashlib.md5("\n".join(normalized).encode()).hexdigest()

            if block_hash in seen_hashes:
                first_line = seen_hashes[block_hash]
                # Only report if blocks are far enough apart (not overlapping)
                if i - first_line >= block_size:
                    smells.append(CodeSmell(
                        kind="duplicate_code",
                        severity="low",
                        description=f"lines {first_line + 1}-{first_line + block_size} ~ lines {i + 1}-{i + block_size}",
                        location=f"L{first_line + 1}..L{i + 1}",
                        line=i + 1,
                        details={"first_block": first_line + 1, "second_block": i + 1},
                    ))
                    # Don't double-report the same first block
                    seen_hashes[block_hash] = i
            else:
                seen_hashes[block_hash] = i

        return smells

    def _detect_feature_envy(self, lines: list[str]) -> list[CodeSmell]:
        """Detect methods that access another class's data more than their own."""
        smells = []
        classes = self._find_classes(lines)
        if len(classes) < 2:
            return smells

        class_names = {name for name, _, _ in classes}

        for class_name, start, end in classes:
            functions = self._find_functions(lines[start:end + 1])
            other_names = class_names - {class_name}
            for func_name, fstart, fend in functions:
                abs_start = start + fstart
                abs_end = start + fend
                body = "\n".join(lines[abs_start:abs_end + 1])
                self_refs = len(re.findall(r'self\.', body))
                for other in other_names:
                    other_refs = len(re.findall(re.escape(other) + r'[\.\(]', body))
                    if other_refs > self_refs and other_refs >= 3:
                        smells.append(CodeSmell(
                            kind="feature_envy",
                            severity="medium",
                            description=f"{func_name}() references {other} ({other_refs}x) more than own class ({self_refs}x)",
                            location=func_name,
                            line=abs_start + 1,
                            details={"other_class": other, "other_refs": other_refs, "self_refs": self_refs},
                        ))
        return smells

    def _detect_dead_code(self, lines: list[str]) -> list[CodeSmell]:
        """Detect unreachable returns and unused assignments."""
        smells = []
        in_function = False
        seen_return = False

        for i, line in enumerate(lines):
            stripped = line.strip()

            if re.match(r'def\s+\w+', stripped):
                in_function = True
                seen_return = False
                continue

            if in_function and stripped.startswith("return ") or stripped == "return":
                if seen_return:
                    smells.append(CodeSmell(
                        kind="dead_code",
                        severity="low",
                        description=f"Unreachable code after return at line {i + 1}",
                        location=f"line {i + 1}",
                        line=i + 1,
                    ))
                seen_return = True

            # Reset on new block (dedent or blank line between statements)
            if stripped == "" or (not stripped.startswith(" ") and not stripped.startswith("\t") and stripped and not stripped.startswith("#")):
                in_function = False
                seen_return = False

        return smells

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve(self, filepath: str) -> str:
        """Resolve filepath relative to cwd."""
        p = Path(filepath)
        if p.is_absolute():
            return str(p)
        return str(Path(self.cwd) / filepath)

    def _find_functions(self, lines: list[str]) -> list[tuple[str, int, int]]:
        """Find function/method definitions and their line ranges.

        Returns list of (name, start_line_idx, end_line_idx).
        """
        functions = []
        pat_py = re.compile(r'^(\s*)def\s+(\w+)\s*\(')
        pat_java = re.compile(r'^(\s*)(?:public|private|protected|static|\s)*\s+\w+\s+(\w+)\s*\(')

        for i, line in enumerate(lines):
            m = pat_py.match(line) or pat_java.match(line)
            if m:
                indent = len(m.group(1))
                name = m.group(2)
                # Find end of function: next line at same or less indent (non-blank)
                end = i
                for j in range(i + 1, len(lines)):
                    stripped = lines[j].strip()
                    if not stripped:
                        continue
                    cur_indent = len(lines[j]) - len(lines[j].lstrip())
                    if cur_indent <= indent and stripped and not stripped.startswith("#") and not stripped.startswith("//"):
                        break
                    end = j
                functions.append((name, i, end))

        return functions

    def _find_classes(self, lines: list[str]) -> list[tuple[str, int, int]]:
        """Find class definitions and their line ranges.

        Returns list of (name, start_line_idx, end_line_idx).
        """
        classes = []
        pat_py = re.compile(r'^(\s*)class\s+(\w+)')
        pat_java = re.compile(r'^(\s*)(?:public|private|protected)?\s*class\s+(\w+)')

        for i, line in enumerate(lines):
            m = pat_py.match(line) or pat_java.match(line)
            if m:
                indent = len(m.group(1))
                name = m.group(2)
                end = i
                for j in range(i + 1, len(lines)):
                    stripped = lines[j].strip()
                    if not stripped:
                        continue
                    cur_indent = len(lines[j]) - len(lines[j].lstrip())
                    if cur_indent <= indent and stripped and not stripped.startswith("#") and not stripped.startswith("//"):
                        break
                    end = j
                classes.append((name, i, end))

        return classes


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

_SEVERITY_ICONS = {
    "high": "\U0001f534",     # red circle
    "medium": "\U0001f7e0",   # orange circle
    "low": "\U0001f7e1",      # yellow circle
}

_RISK_LABELS = {
    range(0, 30): "LOW",
    range(30, 60): "MEDIUM",
    range(60, 101): "HIGH",
}


def _risk_label(score: int) -> str:
    for r, label in _RISK_LABELS.items():
        if score in r:
            return label
    return "UNKNOWN"


def format_refactor_plan(plan: RefactorPlan) -> str:
    """Format a RefactorPlan for terminal display."""
    out = []
    fname = os.path.basename(plan.filepath)

    out.append("")
    out.append(f"  Refactor Analysis: {fname}")
    out.append(f"  {'=' * (20 + len(fname))}")
    out.append("")

    if not plan.smells:
        out.append("  No code smells detected. Code looks clean!")
        out.append("")
        return "\n".join(out)

    # Smells
    out.append(f"  Code Smells ({len(plan.smells)}):")
    for smell in plan.smells:
        icon = _SEVERITY_ICONS.get(smell.severity, "  ")
        out.append(f"    {icon} {smell.kind.replace('_', ' ').title()} -- {smell.description}")
    out.append("")

    # Risk
    label = _risk_label(plan.risk_score)
    out.append(f"  Risk: {plan.risk_score}/100 ({label})")
    if plan.dependents:
        out.append(f"    {plan.dependents} files depend on this module")
    if plan.test_files:
        out.append(f"    {plan.test_files} test files cover this module")
    if plan.critical_path:
        out.append(f"    Critical path: {plan.critical_path}")
    out.append("")

    # Suggested plan
    if plan.suggestions:
        out.append("  Suggested Plan:")
        for i, sug in enumerate(plan.suggestions, 1):
            out.append(f"    {i}. {sug.technique}: {sug.description}")
            out.append(f"       Risk: {sug.risk} | Effort: {sug.effort}")
        out.append("")

    return "\n".join(out)
