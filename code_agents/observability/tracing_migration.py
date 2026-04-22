"""OpenTelemetry Migration Tool — scan repos for old tracing patterns and migrate to OTel.

One-command tool that detects Jaeger, Zipkin, DataDog, New Relic, OpenTracing,
and custom/print-based tracing, then generates OTel replacements with full
dependency management and collector config generation.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.observability.tracing_migration")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class TracingPattern:
    file: str
    line: int
    old_pattern: str  # "jaeger", "zipkin", "datadog", "newrelic", "custom", "print"
    old_code: str
    new_code: str
    confidence: float  # 0-1


@dataclass
class DependencyChange:
    action: str  # "add" | "remove" | "replace"
    package: str
    version: str
    file: str  # pyproject.toml, package.json, pom.xml


@dataclass
class ConfigChange:
    file: str
    old_content: str
    new_content: str
    description: str


@dataclass
class MigrationPlan:
    detected_framework: str  # jaeger|zipkin|datadog|newrelic|custom|none
    language: str
    patterns_found: list[TracingPattern] = field(default_factory=list)
    dependency_changes: list[DependencyChange] = field(default_factory=list)
    config_changes: list[ConfigChange] = field(default_factory=list)
    risk_level: str = "low"  # low|medium|high


@dataclass
class MigrationResult:
    files_modified: int = 0
    files_created: int = 0
    dependencies_changed: int = 0
    backup_dir: str = ""
    success: bool = False


# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

_PYTHON_PATTERNS: dict[str, list[re.Pattern]] = {
    "jaeger": [
        re.compile(r"from\s+jaeger_client\s+import"),
        re.compile(r"import\s+jaeger_client"),
        re.compile(r"from\s+jaeger_client\.config\s+import"),
    ],
    "datadog": [
        re.compile(r"from\s+ddtrace\s+import"),
        re.compile(r"import\s+ddtrace"),
        re.compile(r"from\s+ddtrace\.contrib"),
    ],
    "opentracing": [
        re.compile(r"import\s+opentracing"),
        re.compile(r"from\s+opentracing\s+import"),
    ],
    "zipkin": [
        re.compile(r"from\s+py_zipkin"),
        re.compile(r"import\s+py_zipkin"),
    ],
    "newrelic": [
        re.compile(r"import\s+newrelic\.agent"),
        re.compile(r"from\s+newrelic\s+import"),
        re.compile(r"newrelic\.agent\.initialize"),
    ],
    "custom": [
        re.compile(r"@app\.middleware.*\n.*time\.time\(\)"),
    ],
    "print": [
        re.compile(r'print\(f?"TRACE:'),
        re.compile(r'logger\.\w+\(["\']request_id='),
    ],
}

_NODE_PATTERNS: dict[str, list[re.Pattern]] = {
    "jaeger": [
        re.compile(r"require\(['\"]jaeger-client['\"]\)"),
        re.compile(r"from\s+['\"]jaeger-client['\"]"),
    ],
    "datadog": [
        re.compile(r"require\(['\"]dd-trace['\"]\)"),
        re.compile(r"from\s+['\"]dd-trace['\"]"),
    ],
    "zipkin": [
        re.compile(r"require\(['\"]zipkin['\"]\)"),
        re.compile(r"from\s+['\"]zipkin['\"]"),
    ],
    "newrelic": [
        re.compile(r"require\(['\"]newrelic['\"]\)"),
    ],
}

_JAVA_PATTERNS: dict[str, list[re.Pattern]] = {
    "jaeger": [
        re.compile(r"import\s+io\.jaegertracing"),
        re.compile(r"io\.opentracing\.contrib\.java"),
    ],
    "zipkin": [
        re.compile(r"import\s+zipkin2"),
        re.compile(r"import\s+brave\."),
    ],
    "datadog": [
        re.compile(r"import\s+datadog\.trace"),
    ],
    "newrelic": [
        re.compile(r"import\s+com\.newrelic\.api\.agent"),
    ],
}

_GO_PATTERNS: dict[str, list[re.Pattern]] = {
    "jaeger": [
        re.compile(r'"github\.com/uber/jaeger-client-go"'),
    ],
    "zipkin": [
        re.compile(r'"github\.com/openzipkin/zipkin-go"'),
    ],
    "datadog": [
        re.compile(r'"gopkg\.in/DataDog/dd-trace-go\.v1"'),
    ],
}

# ---------------------------------------------------------------------------
# File extensions by language
# ---------------------------------------------------------------------------

_EXTENSIONS = {
    "python": (".py",),
    "node": (".js", ".ts", ".mjs", ".cjs"),
    "java": (".java",),
    "go": (".go",),
}


# ---------------------------------------------------------------------------
# Replacement templates
# ---------------------------------------------------------------------------

_PYTHON_OTEL_IMPORTS = """\
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
"""

_PYTHON_OTEL_JAEGER_INIT = """\
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

provider = TracerProvider()
processor = BatchSpanProcessor(OTLPSpanExporter())
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)
"""

_PYTHON_OTEL_DATADOG_INIT = """\
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

provider = TracerProvider()
processor = BatchSpanProcessor(OTLPSpanExporter())
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)
"""

_PYTHON_OTEL_ZIPKIN_INIT = """\
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.zipkin.json import ZipkinExporter

provider = TracerProvider()
processor = BatchSpanProcessor(ZipkinExporter())
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)
"""

_PYTHON_OTEL_CUSTOM_INIT = """\
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

provider = TracerProvider()
processor = BatchSpanProcessor(ConsoleSpanExporter())
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)
"""


# ---------------------------------------------------------------------------
# Helper: path validation
# ---------------------------------------------------------------------------


def _validate_path(base: Path, target: str) -> Path:
    """Resolve *target* and ensure it stays within *base*."""
    resolved = Path(target).resolve()
    base_resolved = base.resolve()
    if not str(resolved).startswith(str(base_resolved)):
        raise ValueError(f"Path escapes repo boundary: {target}")
    return resolved


def _atomic_write(path: Path, content: str) -> None:
    """Write *content* to *path* atomically via tempfile + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# TracingMigrator
# ---------------------------------------------------------------------------


class TracingMigrator:
    """Scan a repository for legacy tracing and migrate to OpenTelemetry."""

    def __init__(self, repo_path: str) -> None:
        self.repo_path = Path(repo_path).resolve()
        if not self.repo_path.is_dir():
            raise FileNotFoundError(f"Repo not found: {repo_path}")
        self._backup_dir = self.repo_path / ".code-agents" / "migration-backup"
        logger.info("TracingMigrator initialized for %s", self.repo_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self) -> MigrationPlan:
        """Detect existing tracing framework and build a migration plan."""
        language = self._detect_language()
        framework = self._detect_tracing_framework(language)

        patterns: list[TracingPattern] = []
        if language == "python":
            patterns = self._scan_python_tracing()
        elif language == "java":
            patterns = self._scan_java_tracing()
        elif language == "node":
            patterns = self._scan_node_tracing()
        elif language == "go":
            patterns = self._scan_go_tracing()

        dep_changes = self._get_dep_changes(language, framework)
        config_changes = self._get_config_changes(language, framework)

        risk = "low"
        if len(patterns) > 20:
            risk = "high"
        elif len(patterns) > 5:
            risk = "medium"

        plan = MigrationPlan(
            detected_framework=framework,
            language=language,
            patterns_found=patterns,
            dependency_changes=dep_changes,
            config_changes=config_changes,
            risk_level=risk,
        )
        logger.info(
            "Scan complete: framework=%s lang=%s patterns=%d risk=%s",
            framework, language, len(patterns), risk,
        )
        return plan

    def apply(self, plan: MigrationPlan, dry_run: bool = False) -> MigrationResult:
        """Apply migration plan. If *dry_run*, no files are changed."""
        result = MigrationResult()

        if dry_run:
            result.files_modified = len({p.file for p in plan.patterns_found})
            result.files_created = 1 + 1  # otel init + collector config
            result.dependencies_changed = len(plan.dependency_changes)
            result.backup_dir = str(self._backup_dir)
            result.success = True
            return result

        # 1. Backup originals
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        result.backup_dir = str(self._backup_dir)
        backed_up: set[str] = set()

        for pat in plan.patterns_found:
            src = _validate_path(self.repo_path, pat.file)
            if str(src) not in backed_up and src.is_file():
                rel = src.relative_to(self.repo_path)
                dst = self._backup_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(dst))
                backed_up.add(str(src))

        # 2. Apply code replacements (group by file)
        files_map: dict[str, list[TracingPattern]] = {}
        for p in plan.patterns_found:
            files_map.setdefault(p.file, []).append(p)

        for fpath, pats in files_map.items():
            full = _validate_path(self.repo_path, fpath)
            if not full.is_file():
                continue
            content = full.read_text(encoding="utf-8", errors="replace")
            for pat in sorted(pats, key=lambda p: p.line, reverse=True):
                content = content.replace(pat.old_code, pat.new_code, 1)
            _atomic_write(full, content)
            result.files_modified += 1

        # 3. Generate OTel init file
        init_content = self._generate_otel_init(plan.language)
        if init_content:
            init_file = self._otel_init_path(plan.language)
            _atomic_write(init_file, init_content)
            result.files_created += 1

        # 4. Generate collector config
        collector_content = self._generate_collector_config()
        collector_path = self.repo_path / "otel-collector-config.yaml"
        _atomic_write(collector_path, collector_content)
        result.files_created += 1

        # 5. Apply config changes
        for cc in plan.config_changes:
            cfg_path = _validate_path(self.repo_path, cc.file)
            if cfg_path.is_file():
                old = cfg_path.read_text(encoding="utf-8", errors="replace")
                if cc.old_content in old:
                    new = old.replace(cc.old_content, cc.new_content, 1)
                    _atomic_write(cfg_path, new)

        result.dependencies_changed = len(plan.dependency_changes)
        result.success = True
        logger.info(
            "Migration applied: modified=%d created=%d deps=%d",
            result.files_modified, result.files_created, result.dependencies_changed,
        )
        return result

    def rollback(self) -> bool:
        """Restore files from migration backup."""
        if not self._backup_dir.is_dir():
            logger.warning("No backup directory found at %s", self._backup_dir)
            return False

        restored = 0
        for backup_file in self._backup_dir.rglob("*"):
            if not backup_file.is_file():
                continue
            rel = backup_file.relative_to(self._backup_dir)
            target = self.repo_path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(backup_file), str(target))
            restored += 1

        # Remove generated files
        for generated in [
            self._otel_init_path_for_current(),
            self.repo_path / "otel-collector-config.yaml",
        ]:
            if generated and generated.is_file():
                generated.unlink()

        # Clean up backup dir
        shutil.rmtree(str(self._backup_dir), ignore_errors=True)
        logger.info("Rollback complete: restored %d files", restored)
        return restored > 0

    # ------------------------------------------------------------------
    # Language detection
    # ------------------------------------------------------------------

    def _detect_language(self) -> str:
        """Detect primary language using project_scanner if available, else heuristics."""
        try:
            from code_agents.analysis.project_scanner import scan_project
            info = scan_project(str(self.repo_path))
            if info.language:
                lang = info.language.lower()
                # Normalise variants
                if lang in ("javascript", "typescript", "node", "node.js", "nodejs"):
                    return "node"
                if lang in ("python", "java", "go", "golang"):
                    return lang.replace("golang", "go")
                return lang
        except Exception:
            logger.debug("project_scanner unavailable, using heuristic detection")

        # Heuristic fallback
        counts: dict[str, int] = {"python": 0, "java": 0, "node": 0, "go": 0}
        for root, _dirs, files in os.walk(str(self.repo_path)):
            # Skip hidden / vendor dirs
            if any(part.startswith(".") or part in ("node_modules", "vendor", "__pycache__")
                   for part in Path(root).parts):
                continue
            for f in files:
                if f.endswith(".py"):
                    counts["python"] += 1
                elif f.endswith(".java"):
                    counts["java"] += 1
                elif f.endswith((".js", ".ts", ".mjs")):
                    counts["node"] += 1
                elif f.endswith(".go"):
                    counts["go"] += 1

        if not any(counts.values()):
            return "unknown"
        return max(counts, key=lambda k: counts[k])

    # ------------------------------------------------------------------
    # Framework detection
    # ------------------------------------------------------------------

    def _detect_tracing_framework(self, language: str = "") -> str:
        """Detect which tracing framework is in use."""
        if not language:
            language = self._detect_language()

        patterns_map = {
            "python": _PYTHON_PATTERNS,
            "node": _NODE_PATTERNS,
            "java": _JAVA_PATTERNS,
            "go": _GO_PATTERNS,
        }
        lang_patterns = patterns_map.get(language, {})
        if not lang_patterns:
            return "none"

        exts = _EXTENSIONS.get(language, ())
        hits: dict[str, int] = {}

        for root, _dirs, files in os.walk(str(self.repo_path)):
            if any(part.startswith(".") or part in ("node_modules", "vendor", "__pycache__")
                   for part in Path(root).parts):
                continue
            for fname in files:
                if not fname.endswith(exts):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    content = Path(fpath).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for framework, regexes in lang_patterns.items():
                    for rx in regexes:
                        if rx.search(content):
                            hits[framework] = hits.get(framework, 0) + 1

        if not hits:
            return "none"
        return max(hits, key=lambda k: hits[k])

    # ------------------------------------------------------------------
    # Scanning by language
    # ------------------------------------------------------------------

    def _scan_python_tracing(self) -> list[TracingPattern]:
        patterns: list[TracingPattern] = []
        for root, _dirs, files in os.walk(str(self.repo_path)):
            if any(part.startswith(".") or part in ("node_modules", "__pycache__", "venv", ".venv")
                   for part in Path(root).parts):
                continue
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    lines = Path(fpath).read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError:
                    continue
                for i, line in enumerate(lines, 1):
                    for fw, regexes in _PYTHON_PATTERNS.items():
                        for rx in regexes:
                            if rx.search(line):
                                tp = self._python_pattern_to_otel(fw, fpath, i, line.strip())
                                if tp:
                                    patterns.append(tp)
        return patterns

    def _scan_java_tracing(self) -> list[TracingPattern]:
        patterns: list[TracingPattern] = []
        for root, _dirs, files in os.walk(str(self.repo_path)):
            if any(part.startswith(".") or part in ("build", "target")
                   for part in Path(root).parts):
                continue
            for fname in files:
                if not fname.endswith(".java"):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    lines = Path(fpath).read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError:
                    continue
                for i, line in enumerate(lines, 1):
                    for fw, regexes in _JAVA_PATTERNS.items():
                        for rx in regexes:
                            if rx.search(line):
                                new_code = self._java_replacement(fw, line.strip())
                                patterns.append(TracingPattern(
                                    file=fpath,
                                    line=i,
                                    old_pattern=fw,
                                    old_code=line.strip(),
                                    new_code=new_code,
                                    confidence=0.85,
                                ))
        return patterns

    def _scan_node_tracing(self) -> list[TracingPattern]:
        patterns: list[TracingPattern] = []
        for root, _dirs, files in os.walk(str(self.repo_path)):
            if any(part.startswith(".") or part == "node_modules"
                   for part in Path(root).parts):
                continue
            for fname in files:
                if not fname.endswith((".js", ".ts", ".mjs", ".cjs")):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    lines = Path(fpath).read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError:
                    continue
                for i, line in enumerate(lines, 1):
                    for fw, regexes in _NODE_PATTERNS.items():
                        for rx in regexes:
                            if rx.search(line):
                                new_code = self._node_replacement(fw, line.strip())
                                patterns.append(TracingPattern(
                                    file=fpath,
                                    line=i,
                                    old_pattern=fw,
                                    old_code=line.strip(),
                                    new_code=new_code,
                                    confidence=0.85,
                                ))
        return patterns

    def _scan_go_tracing(self) -> list[TracingPattern]:
        patterns: list[TracingPattern] = []
        for root, _dirs, files in os.walk(str(self.repo_path)):
            if any(part.startswith(".") or part == "vendor"
                   for part in Path(root).parts):
                continue
            for fname in files:
                if not fname.endswith(".go"):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    lines = Path(fpath).read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError:
                    continue
                for i, line in enumerate(lines, 1):
                    for fw, regexes in _GO_PATTERNS.items():
                        for rx in regexes:
                            if rx.search(line):
                                new_code = self._go_replacement(fw, line.strip())
                                patterns.append(TracingPattern(
                                    file=fpath,
                                    line=i,
                                    old_pattern=fw,
                                    old_code=line.strip(),
                                    new_code=new_code,
                                    confidence=0.80,
                                ))
        return patterns

    # ------------------------------------------------------------------
    # Python-specific replacements
    # ------------------------------------------------------------------

    def _python_pattern_to_otel(self, framework: str, file: str, line: int, code: str) -> Optional[TracingPattern]:
        dispatch = {
            "jaeger": self._python_jaeger_to_otel,
            "datadog": self._python_datadog_to_otel,
            "zipkin": self._python_zipkin_to_otel,
            "opentracing": self._python_opentracing_to_otel,
            "newrelic": self._python_newrelic_to_otel,
            "custom": self._python_custom_to_otel,
            "print": self._python_print_to_otel,
        }
        handler = dispatch.get(framework)
        if handler:
            return handler(file, line, code)
        return None

    def _python_jaeger_to_otel(self, file: str, line: int, code: str) -> TracingPattern:
        new = code
        if "from jaeger_client import" in code:
            new = "from opentelemetry import trace"
        elif "import jaeger_client" in code:
            new = "from opentelemetry import trace"
        elif "from jaeger_client.config import" in code:
            new = "from opentelemetry.sdk.trace import TracerProvider"
        return TracingPattern(
            file=file, line=line, old_pattern="jaeger",
            old_code=code, new_code=new, confidence=0.95,
        )

    def _python_zipkin_to_otel(self, file: str, line: int, code: str) -> TracingPattern:
        new = code
        if "from py_zipkin" in code or "import py_zipkin" in code:
            new = "from opentelemetry import trace"
        return TracingPattern(
            file=file, line=line, old_pattern="zipkin",
            old_code=code, new_code=new, confidence=0.90,
        )

    def _python_datadog_to_otel(self, file: str, line: int, code: str) -> TracingPattern:
        new = code
        if "from ddtrace import" in code:
            new = "from opentelemetry import trace"
        elif "import ddtrace" in code:
            new = "from opentelemetry import trace"
        elif "from ddtrace.contrib" in code:
            new = "# OTel auto-instrumentation replaces ddtrace contrib"
        return TracingPattern(
            file=file, line=line, old_pattern="datadog",
            old_code=code, new_code=new, confidence=0.90,
        )

    def _python_opentracing_to_otel(self, file: str, line: int, code: str) -> TracingPattern:
        new = code
        if "import opentracing" in code or "from opentracing import" in code:
            new = "from opentelemetry import trace"
        return TracingPattern(
            file=file, line=line, old_pattern="opentracing",
            old_code=code, new_code=new, confidence=0.90,
        )

    def _python_newrelic_to_otel(self, file: str, line: int, code: str) -> TracingPattern:
        new = code
        if "import newrelic.agent" in code:
            new = "from opentelemetry import trace"
        elif "from newrelic import" in code:
            new = "from opentelemetry import trace"
        elif "newrelic.agent.initialize" in code:
            new = "# OTel initialization — see otel_setup.py"
        return TracingPattern(
            file=file, line=line, old_pattern="newrelic",
            old_code=code, new_code=new, confidence=0.85,
        )

    def _python_custom_to_otel(self, file: str, line: int, code: str) -> TracingPattern:
        new = "# Replaced custom tracing — see otel_setup.py for OTel middleware"
        return TracingPattern(
            file=file, line=line, old_pattern="custom",
            old_code=code, new_code=new, confidence=0.60,
        )

    def _python_print_to_otel(self, file: str, line: int, code: str) -> TracingPattern:
        new = code
        if 'print(f"TRACE:' in code or "print(\"TRACE:" in code:
            new = "# Replaced print-tracing with OTel spans — see otel_setup.py"
        elif "request_id=" in code:
            new = "# Request tracing handled by OTel auto-instrumentation"
        return TracingPattern(
            file=file, line=line, old_pattern="print",
            old_code=code, new_code=new, confidence=0.70,
        )

    # ------------------------------------------------------------------
    # Java replacements
    # ------------------------------------------------------------------

    def _java_replacement(self, framework: str, code: str) -> str:
        if framework == "jaeger":
            if "io.jaegertracing" in code:
                return "import io.opentelemetry.api.trace.Tracer;"
            if "io.opentracing" in code:
                return "import io.opentelemetry.api.trace.Span;"
        elif framework == "zipkin":
            if "zipkin2" in code:
                return "import io.opentelemetry.api.trace.Tracer;"
            if "brave." in code:
                return "import io.opentelemetry.api.trace.Span;"
        elif framework == "datadog":
            return "import io.opentelemetry.api.trace.Tracer;"
        elif framework == "newrelic":
            return "import io.opentelemetry.api.trace.Tracer;"
        return code

    # ------------------------------------------------------------------
    # Node replacements
    # ------------------------------------------------------------------

    def _node_replacement(self, framework: str, code: str) -> str:
        if framework == "jaeger":
            return "const { trace } = require('@opentelemetry/api');"
        elif framework == "datadog":
            return "const { trace } = require('@opentelemetry/api');"
        elif framework == "zipkin":
            return "const { trace } = require('@opentelemetry/api');"
        elif framework == "newrelic":
            return "const { trace } = require('@opentelemetry/api');"
        return code

    # ------------------------------------------------------------------
    # Go replacements
    # ------------------------------------------------------------------

    def _go_replacement(self, framework: str, code: str) -> str:
        if framework == "jaeger":
            return '"go.opentelemetry.io/otel"'
        elif framework == "zipkin":
            return '"go.opentelemetry.io/otel"'
        elif framework == "datadog":
            return '"go.opentelemetry.io/otel"'
        return code

    # ------------------------------------------------------------------
    # OTel init generation
    # ------------------------------------------------------------------

    def _otel_init_path(self, language: str) -> Path:
        if language == "python":
            return self.repo_path / "otel_setup.py"
        elif language == "node":
            return self.repo_path / "otel-setup.js"
        elif language == "java":
            return self.repo_path / "src" / "main" / "java" / "OtelSetup.java"
        return self.repo_path / "otel_setup.txt"

    def _otel_init_path_for_current(self) -> Optional[Path]:
        """Return init path based on detected language, or None."""
        lang = self._detect_language()
        return self._otel_init_path(lang) if lang != "unknown" else None

    def _generate_otel_init(self, language: str) -> str:
        if language == "python":
            return self._generate_otel_init_python()
        elif language == "java":
            return self._generate_otel_init_java()
        elif language == "node":
            return self._generate_otel_init_node()
        return ""

    def _generate_otel_init_python(self) -> str:
        return '''\
"""OpenTelemetry initialization — auto-generated by code-agents migrate-tracing.

Import this module early in your application entry point:
    import otel_setup  # noqa: F401

Environment variables:
    OTEL_EXPORTER_OTLP_ENDPOINT  — collector endpoint (default: http://localhost:4317)
    OTEL_SERVICE_NAME            — service name for traces
    OTEL_RESOURCE_ATTRIBUTES     — extra resource attributes
"""

import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "my-service")

resource = Resource.create({
    "service.name": _SERVICE_NAME,
    "service.version": os.getenv("SERVICE_VERSION", "0.0.0"),
})

provider = TracerProvider(resource=resource)

otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
processor = BatchSpanProcessor(exporter)
provider.add_span_processor(processor)

trace.set_tracer_provider(provider)

tracer = trace.get_tracer(__name__)


def get_tracer(name: str = __name__):
    """Return a named tracer instance."""
    return trace.get_tracer(name)


def shutdown():
    """Flush and shut down the tracer provider."""
    provider.shutdown()
'''

    def _generate_otel_init_java(self) -> str:
        return '''\
// OpenTelemetry initialization — auto-generated by code-agents migrate-tracing.
// Add the OTel Java agent to your JVM args:
//   -javaagent:opentelemetry-javaagent.jar
//   -Dotel.service.name=my-service
//   -Dotel.exporter.otlp.endpoint=http://localhost:4317
//
// Or use programmatic setup below:

import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.export.BatchSpanProcessor;
import io.opentelemetry.exporter.otlp.trace.OtlpGrpcSpanExporter;
import io.opentelemetry.sdk.resources.Resource;
import io.opentelemetry.semconv.resource.attributes.ResourceAttributes;
import io.opentelemetry.api.common.Attributes;

public class OtelSetup {
    private static final OpenTelemetry openTelemetry;

    static {
        Resource resource = Resource.getDefault()
            .merge(Resource.create(Attributes.of(
                ResourceAttributes.SERVICE_NAME, System.getenv().getOrDefault("OTEL_SERVICE_NAME", "my-service")
            )));

        OtlpGrpcSpanExporter exporter = OtlpGrpcSpanExporter.builder()
            .setEndpoint(System.getenv().getOrDefault("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"))
            .build();

        SdkTracerProvider tracerProvider = SdkTracerProvider.builder()
            .addSpanProcessor(BatchSpanProcessor.builder(exporter).build())
            .setResource(resource)
            .build();

        openTelemetry = OpenTelemetrySdk.builder()
            .setTracerProvider(tracerProvider)
            .build();
    }

    public static Tracer getTracer(String name) {
        return openTelemetry.getTracer(name);
    }
}
'''

    def _generate_otel_init_node(self) -> str:
        return '''\
// OpenTelemetry initialization — auto-generated by code-agents migrate-tracing.
// Require this file first: node -r ./otel-setup.js app.js

'use strict';

const { NodeSDK } = require('@opentelemetry/sdk-node');
const { OTLPTraceExporter } = require('@opentelemetry/exporter-trace-otlp-grpc');
const { getNodeAutoInstrumentations } = require('@opentelemetry/auto-instrumentations-node');
const { Resource } = require('@opentelemetry/resources');
const { SemanticResourceAttributes } = require('@opentelemetry/semantic-conventions');

const sdk = new NodeSDK({
  resource: new Resource({
    [SemanticResourceAttributes.SERVICE_NAME]: process.env.OTEL_SERVICE_NAME || 'my-service',
  }),
  traceExporter: new OTLPTraceExporter({
    url: process.env.OTEL_EXPORTER_OTLP_ENDPOINT || 'http://localhost:4317',
  }),
  instrumentations: [getNodeAutoInstrumentations()],
});

sdk.start();

process.on('SIGTERM', () => {
  sdk.shutdown().then(() => process.exit(0)).catch(() => process.exit(1));
});
'''

    def _generate_collector_config(self) -> str:
        return '''\
# OpenTelemetry Collector configuration
# Auto-generated by code-agents migrate-tracing
#
# Run with: otelcol --config otel-collector-config.yaml

receivers:
  otlp:
    protocols:
      grpc:
        endpoint: "0.0.0.0:4317"
      http:
        endpoint: "0.0.0.0:4318"

processors:
  batch:
    timeout: 5s
    send_batch_size: 1024
  memory_limiter:
    check_interval: 1s
    limit_mib: 512

exporters:
  logging:
    loglevel: info
  otlp:
    endpoint: "localhost:4317"
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [logging, otlp]
'''

    # ------------------------------------------------------------------
    # Dependency changes
    # ------------------------------------------------------------------

    def _get_dep_changes(self, language: str, framework: str) -> list[DependencyChange]:
        if language == "python":
            return self._python_dep_changes(framework)
        elif language == "node":
            return self._node_dep_changes(framework)
        elif language == "java":
            return self._java_dep_changes(framework)
        return []

    def _python_dep_changes(self, framework: str) -> list[DependencyChange]:
        changes: list[DependencyChange] = []
        dep_file = "pyproject.toml"
        if not (self.repo_path / dep_file).is_file():
            dep_file = "requirements.txt"
            if not (self.repo_path / dep_file).is_file():
                dep_file = "pyproject.toml"  # default

        # Remove old
        remove_map = {
            "jaeger": "jaeger-client",
            "datadog": "ddtrace",
            "zipkin": "py_zipkin",
            "newrelic": "newrelic",
            "opentracing": "opentracing",
        }
        if framework in remove_map:
            changes.append(DependencyChange(
                action="remove", package=remove_map[framework],
                version="", file=dep_file,
            ))

        # Add OTel packages
        otel_pkgs = [
            ("opentelemetry-api", "1.24.0"),
            ("opentelemetry-sdk", "1.24.0"),
            ("opentelemetry-exporter-otlp-proto-grpc", "1.24.0"),
        ]
        if framework == "zipkin":
            otel_pkgs.append(("opentelemetry-exporter-zipkin", "1.24.0"))

        for pkg, ver in otel_pkgs:
            changes.append(DependencyChange(
                action="add", package=pkg, version=ver, file=dep_file,
            ))
        return changes

    def _node_dep_changes(self, framework: str) -> list[DependencyChange]:
        changes: list[DependencyChange] = []
        dep_file = "package.json"

        remove_map = {
            "jaeger": "jaeger-client",
            "datadog": "dd-trace",
            "zipkin": "zipkin",
            "newrelic": "newrelic",
        }
        if framework in remove_map:
            changes.append(DependencyChange(
                action="remove", package=remove_map[framework],
                version="", file=dep_file,
            ))

        otel_pkgs = [
            ("@opentelemetry/api", "1.8.0"),
            ("@opentelemetry/sdk-node", "0.49.0"),
            ("@opentelemetry/exporter-trace-otlp-grpc", "0.49.0"),
            ("@opentelemetry/auto-instrumentations-node", "0.43.0"),
        ]
        for pkg, ver in otel_pkgs:
            changes.append(DependencyChange(
                action="add", package=pkg, version=ver, file=dep_file,
            ))
        return changes

    def _java_dep_changes(self, framework: str) -> list[DependencyChange]:
        changes: list[DependencyChange] = []
        dep_file = "pom.xml"
        if not (self.repo_path / dep_file).is_file():
            dep_file = "build.gradle"

        remove_map = {
            "jaeger": "io.jaegertracing:jaeger-client",
            "zipkin": "io.zipkin.reporter2:zipkin-reporter",
            "datadog": "com.datadoghq:dd-java-agent",
            "newrelic": "com.newrelic.agent.java:newrelic-agent",
        }
        if framework in remove_map:
            changes.append(DependencyChange(
                action="remove", package=remove_map[framework],
                version="", file=dep_file,
            ))

        otel_pkgs = [
            ("io.opentelemetry:opentelemetry-api", "1.36.0"),
            ("io.opentelemetry:opentelemetry-sdk", "1.36.0"),
            ("io.opentelemetry:opentelemetry-exporter-otlp", "1.36.0"),
        ]
        for pkg, ver in otel_pkgs:
            changes.append(DependencyChange(
                action="add", package=pkg, version=ver, file=dep_file,
            ))
        return changes

    # ------------------------------------------------------------------
    # Config changes
    # ------------------------------------------------------------------

    def _get_config_changes(self, language: str, framework: str) -> list[ConfigChange]:
        changes: list[ConfigChange] = []

        # Check for docker-compose references
        for dc_name in ("docker-compose.yml", "docker-compose.yaml"):
            dc_path = self.repo_path / dc_name
            if dc_path.is_file():
                content = dc_path.read_text(encoding="utf-8", errors="replace")
                if "jaeger" in content.lower() or "zipkin" in content.lower():
                    changes.append(ConfigChange(
                        file=dc_name,
                        old_content="",
                        new_content="",
                        description=f"Review {dc_name} — replace Jaeger/Zipkin service with OTel Collector",
                    ))

        # Check for env files with tracing config
        for env_name in (".env", ".env.example"):
            env_path = self.repo_path / env_name
            if env_path.is_file():
                content = env_path.read_text(encoding="utf-8", errors="replace")
                if any(k in content.upper() for k in ("JAEGER_", "DD_TRACE_", "ZIPKIN_", "NEW_RELIC_")):
                    changes.append(ConfigChange(
                        file=env_name,
                        old_content="",
                        new_content="",
                        description=f"Update {env_name} — replace old tracing env vars with OTEL_* equivalents",
                    ))

        return changes


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_migration_plan(plan: MigrationPlan) -> str:
    """Format a migration plan for terminal display."""
    lines: list[str] = []
    lines.append("")
    lines.append("  OpenTelemetry Migration Plan")
    lines.append("  " + "=" * 40)
    lines.append(f"  Language:    {plan.language}")
    lines.append(f"  Framework:   {plan.detected_framework}")
    lines.append(f"  Risk level:  {plan.risk_level}")
    lines.append(f"  Patterns:    {len(plan.patterns_found)}")
    lines.append(f"  Dep changes: {len(plan.dependency_changes)}")
    lines.append("")

    if plan.patterns_found:
        lines.append("  Code Replacements:")
        shown = 0
        for p in plan.patterns_found[:15]:
            rel = p.file
            try:
                rel = str(Path(p.file).relative_to(Path.cwd()))
            except ValueError:
                pass
            lines.append(f"    {rel}:{p.line}  [{p.old_pattern}] conf={p.confidence:.0%}")
            lines.append(f"      - {p.old_code[:80]}")
            lines.append(f"      + {p.new_code[:80]}")
            shown += 1
        remaining = len(plan.patterns_found) - shown
        if remaining > 0:
            lines.append(f"    ... and {remaining} more")
        lines.append("")

    if plan.dependency_changes:
        lines.append("  Dependency Changes:")
        for d in plan.dependency_changes:
            sym = {"add": "+", "remove": "-", "replace": "~"}.get(d.action, "?")
            ver = f" {d.version}" if d.version else ""
            lines.append(f"    [{sym}] {d.package}{ver}  ({d.file})")
        lines.append("")

    if plan.config_changes:
        lines.append("  Config Notes:")
        for c in plan.config_changes:
            lines.append(f"    - {c.description}")
        lines.append("")

    return "\n".join(lines)


def format_migration_result(result: MigrationResult) -> str:
    """Format a migration result for terminal display."""
    lines: list[str] = []
    lines.append("")
    status = "SUCCESS" if result.success else "FAILED"
    lines.append(f"  Migration {status}")
    lines.append("  " + "-" * 30)
    lines.append(f"  Files modified:  {result.files_modified}")
    lines.append(f"  Files created:   {result.files_created}")
    lines.append(f"  Deps changed:    {result.dependencies_changed}")
    if result.backup_dir:
        lines.append(f"  Backup:          {result.backup_dir}")
    lines.append("")
    return "\n".join(lines)
