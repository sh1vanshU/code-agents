"""Dead Code Finder — static analysis for unused code."""

import logging
import os
import re
import ast
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.analysis.deadcode")

_SKIP_DIRS = frozenset({
    '.git', '__pycache__', 'venv', '.venv', 'node_modules',
    '.tox', 'dist', 'build', '.eggs', 'target', '.gradle', '.mvn', '.next',
})


@dataclass
class DeadCodeReport:
    """Results from a dead-code scan."""

    repo_path: str
    language: str
    unused_imports: list[dict] = field(default_factory=list)     # file, import, line
    unused_functions: list[dict] = field(default_factory=list)   # file, name, line
    unused_classes: list[dict] = field(default_factory=list)     # file, name, line
    orphan_endpoints: list[dict] = field(default_factory=list)   # file, route, line
    unused_variables: list[dict] = field(default_factory=list)   # file, name, line
    total_dead_lines: int = 0


class DeadCodeFinder:
    """Finds dead code in a repository via static analysis."""

    def __init__(self, cwd: str, language: Optional[str] = None):
        self.cwd = cwd
        self.language = language or self._detect_language()
        self.report = DeadCodeReport(repo_path=cwd, language=self.language)
        logger.info("DeadCodeFinder initialized — repo=%s lang=%s", cwd, self.language)

    # ------------------------------------------------------------------
    # Language detection
    # ------------------------------------------------------------------

    def _detect_language(self) -> str:
        """Auto-detect primary language from build files."""
        markers = {
            "python":     ("pyproject.toml", "setup.py", "requirements.txt"),
            "java":       ("pom.xml", "build.gradle", "build.gradle.kts"),
            "javascript": ("package.json",),
            "go":         ("go.mod",),
        }
        for lang, files in markers.items():
            for f in files:
                if os.path.exists(os.path.join(self.cwd, f)):
                    return lang
        return "unknown"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self) -> DeadCodeReport:
        """Run all dead-code checks and return the report."""
        logger.info("Starting dead-code scan for %s (%s)", self.cwd, self.language)

        if self.language == "python":
            self._scan_python()
        elif self.language == "java":
            self._scan_java()
        elif self.language in ("javascript", "typescript"):
            self._scan_js()

        self._scan_orphan_endpoints()

        self.report.total_dead_lines = (
            len(self.report.unused_imports)
            + len(self.report.unused_functions)
            + len(self.report.unused_classes)
            + len(self.report.orphan_endpoints)
            + len(self.report.unused_variables)
        )
        logger.info("Dead-code scan complete — %d issues found", self.report.total_dead_lines)
        return self.report

    # ------------------------------------------------------------------
    # Python scanner (AST-based)
    # ------------------------------------------------------------------

    def _get_python_files(self) -> list[str]:
        """Collect .py files, excluding tests and virtual envs."""
        files: list[str] = []
        for root, dirs, filenames in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for f in filenames:
                if f.endswith(".py") and not f.startswith("test_"):
                    files.append(os.path.join(root, f))
        return files

    def _scan_python(self):
        """Scan Python files for unused imports and private functions."""
        for fpath in self._get_python_files():
            try:
                with open(fpath) as f:
                    source = f.read()
                tree = ast.parse(source, filename=fpath)
                rel = os.path.relpath(fpath, self.cwd)
                self._check_python_imports(tree, source, rel)
                self._check_python_functions(tree, source, rel)
            except (SyntaxError, Exception) as exc:
                logger.debug("Could not parse %s: %s", fpath, exc)

    def _check_python_imports(self, tree: ast.Module, source: str, rel_path: str):
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name
                    if not self._name_used_in_file(name, source, node.lineno):
                        self.report.unused_imports.append({
                            "file": rel_path, "import": alias.name, "line": node.lineno,
                        })
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname or alias.name
                    if name == "*":
                        continue
                    if not self._name_used_in_file(name, source, node.lineno):
                        module = node.module or ""
                        self.report.unused_imports.append({
                            "file": rel_path,
                            "import": f"from {module} import {alias.name}",
                            "line": node.lineno,
                        })

    def _check_python_functions(self, tree: ast.Module, source: str, rel_path: str):
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Only flag private (single underscore) functions
                if node.name.startswith("_") and not node.name.startswith("__"):
                    if not self._name_used_in_file(node.name, source, node.lineno):
                        self.report.unused_functions.append({
                            "file": rel_path, "name": node.name, "line": node.lineno,
                        })

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _name_used_in_file(name: str, source: str, def_line: int) -> bool:
        """Return True if *name* appears in *source* on any line except *def_line*."""
        pattern = re.compile(r"\b" + re.escape(name) + r"\b")
        for lineno, line in enumerate(source.split("\n"), 1):
            if lineno == def_line:
                continue
            if line.lstrip().startswith("#"):
                continue
            if pattern.search(line):
                return True
        return False

    # ------------------------------------------------------------------
    # Java scanner (regex-based)
    # ------------------------------------------------------------------

    def _scan_java(self):
        """Scan Java files for unused imports and private methods."""
        for root, dirs, filenames in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for f in filenames:
                if not f.endswith(".java") or f.endswith("Test.java"):
                    continue
                fpath = os.path.join(root, f)
                rel = os.path.relpath(fpath, self.cwd)
                try:
                    with open(fpath) as fp:
                        content = fp.read()
                    self._check_java_imports(content, rel)
                    self._check_java_private_methods(content, rel)
                except Exception as exc:
                    logger.debug("Could not scan %s: %s", fpath, exc)

    def _check_java_imports(self, content: str, rel_path: str):
        for match in re.finditer(r"^import\s+([\w.]+);", content, re.MULTILINE):
            import_name = match.group(1)
            short = import_name.split(".")[-1]
            if short != "*" and content.count(short) <= 1:
                line_num = content[: match.start()].count("\n") + 1
                self.report.unused_imports.append({
                    "file": rel_path, "import": import_name, "line": line_num,
                })

    def _check_java_private_methods(self, content: str, rel_path: str):
        for match in re.finditer(r"private\s+\w+\s+(\w+)\s*\(", content):
            method = match.group(1)
            if content.count(method) <= 1:
                line_num = content[: match.start()].count("\n") + 1
                self.report.unused_functions.append({
                    "file": rel_path, "name": method, "line": line_num,
                })

    # ------------------------------------------------------------------
    # JS / TS scanner (regex-based)
    # ------------------------------------------------------------------

    def _scan_js(self):
        """Scan JS/TS files for unused named imports."""
        for root, dirs, filenames in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for f in filenames:
                if not f.endswith((".js", ".ts", ".jsx", ".tsx")):
                    continue
                if ".test." in f or ".spec." in f:
                    continue
                fpath = os.path.join(root, f)
                rel = os.path.relpath(fpath, self.cwd)
                try:
                    with open(fpath) as fp:
                        content = fp.read()
                    for match in re.finditer(r"import\s*\{([^}]+)\}\s*from", content):
                        names = [
                            n.strip().split(" as ")[-1].strip()
                            for n in match.group(1).split(",")
                        ]
                        for name in names:
                            if name and content.count(name) <= 1:
                                line_num = content[: match.start()].count("\n") + 1
                                self.report.unused_imports.append({
                                    "file": rel, "import": name, "line": line_num,
                                })
                except Exception as exc:
                    logger.debug("Could not scan %s: %s", fpath, exc)

    # ------------------------------------------------------------------
    # Orphan endpoint scanner (cross-language)
    # ------------------------------------------------------------------

    def _scan_orphan_endpoints(self):
        """Find route definitions whose path is never referenced in other files."""
        routes: list[dict] = []
        all_content = ""
        code_exts = (".py", ".java", ".js", ".ts", ".yaml", ".yml", ".json")

        for root, dirs, filenames in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for f in filenames:
                fpath = os.path.join(root, f)
                rel = os.path.relpath(fpath, self.cwd)
                try:
                    with open(fpath) as fp:
                        content = fp.read()
                except Exception:
                    continue

                # Accumulate content for reference check
                if f.endswith(code_exts):
                    all_content += content

                # Python decorators: @app.get("/path"), @router.post("/path")
                for m in re.finditer(
                    r"@(?:app|router)\.(get|post|put|delete|patch)\s*\([\"']([^\"']+)",
                    content,
                ):
                    line_num = content[: m.start()].count("\n") + 1
                    routes.append({
                        "file": rel,
                        "route": f"{m.group(1).upper()} {m.group(2)}",
                        "line": line_num,
                        "path": m.group(2),
                    })

                # Java: @GetMapping("/path")
                for m in re.finditer(
                    r"@(Get|Post|Put|Delete|Patch|Request)Mapping\s*\(\s*(?:value\s*=\s*)?[\"']([^\"']+)",
                    content,
                ):
                    line_num = content[: m.start()].count("\n") + 1
                    routes.append({
                        "file": rel,
                        "route": f"{m.group(1).upper()} {m.group(2)}",
                        "line": line_num,
                        "path": m.group(2),
                    })

        # A route is orphan if its path appears at most once across the codebase
        for route in routes:
            if all_content.count(route["path"]) <= 1:
                self.report.orphan_endpoints.append(route)


# ----------------------------------------------------------------------
# Formatting
# ----------------------------------------------------------------------

def format_deadcode_report(report: DeadCodeReport) -> str:
    """Format a DeadCodeReport for terminal display."""
    lines: list[str] = []
    lines.append("  \u2554\u2550\u2550 DEAD CODE REPORT \u2550\u2550\u2557")
    lines.append(f"  \u2551 Repo: {os.path.basename(report.repo_path)}")
    lines.append(f"  \u2551 Language: {report.language}")
    lines.append(f"  \u2551 Issues: {report.total_dead_lines}")
    lines.append("  \u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d")

    if report.unused_imports:
        lines.append(f"\n  Unused Imports ({len(report.unused_imports)}):")
        for item in report.unused_imports[:20]:
            lines.append(f"    \u2717 {item['file']}:{item['line']} \u2014 {item['import']}")
        if len(report.unused_imports) > 20:
            lines.append(f"    ... and {len(report.unused_imports) - 20} more")

    if report.unused_functions:
        lines.append(f"\n  Unused Functions ({len(report.unused_functions)}):")
        for item in report.unused_functions[:20]:
            lines.append(f"    \u2717 {item['file']}:{item['line']} \u2014 {item['name']}()")
        if len(report.unused_functions) > 20:
            lines.append(f"    ... and {len(report.unused_functions) - 20} more")

    if report.unused_classes:
        lines.append(f"\n  Unused Classes ({len(report.unused_classes)}):")
        for item in report.unused_classes[:10]:
            lines.append(f"    \u2717 {item['file']}:{item['line']} \u2014 {item['name']}")

    if report.orphan_endpoints:
        lines.append(f"\n  Orphan Endpoints ({len(report.orphan_endpoints)}):")
        for item in report.orphan_endpoints[:15]:
            lines.append(f"    \u2717 {item['file']}:{item['line']} \u2014 {item['route']}")
        if len(report.orphan_endpoints) > 15:
            lines.append(f"    ... and {len(report.orphan_endpoints) - 15} more")

    if report.total_dead_lines == 0:
        lines.append("\n  \u2713 No dead code detected!")

    return "\n".join(lines)
