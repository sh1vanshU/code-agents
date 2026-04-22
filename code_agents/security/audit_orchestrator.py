"""Global Audit Orchestrator — one command to run ALL scanners and produce a unified report.

Runs security, code quality, payment safety, privacy, and other scanners in parallel,
evaluates quality gates from .foundry/casts/, and produces a scored report with trends.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("code_agents.security.audit_orchestrator")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class AuditCategory:
    name: str
    score: int
    max_score: int = 100
    findings_count: int = 0
    critical: int = 0
    high: int = 0
    scanner: str = ""
    error: str = ""


@dataclass
class QualityGate:
    name: str
    source: str  # which foundry cast
    passed: bool
    message: str
    severity: str  # "critical" | "warning" | "info"


@dataclass
class AuditReport:
    overall_score: int  # 0-100
    categories: list[AuditCategory]
    quality_gates: list[QualityGate]
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    timestamp: str
    repo: str
    duration_seconds: float
    trend: dict  # vs last audit


# ---------------------------------------------------------------------------
# Scanner & gate config
# ---------------------------------------------------------------------------

AUDIT_SCANNERS: dict[str, list[tuple[str, str]]] = {
    "security": [("owasp_scanner", "OWASPScanner"), ("pci_scanner", "PCIComplianceScanner")],
    "encryption": [("encryption_audit", "EncryptionAuditor")],
    "code_quality": [("code_smell", "CodeSmellDetector"), ("dead_code_eliminator", "DeadCodeEliminator")],
    "naming": [("naming_audit", "NamingAuditor")],
    "imports": [("import_optimizer", "ImportOptimizer")],
    "payment_safety": [
        ("idempotency_audit", "IdempotencyAuditor"),
        ("state_machine_validator", "StateMachineValidator"),
        ("retry_analyzer", "RetryAnalyzer"),
    ],
    "input_validation": [("input_audit", "InputAuditor")],
    "session_security": [("session_audit", "SessionAuditor")],
    "rate_limiting": [("rate_limit_audit", "RateLimitAuditor")],
    "privacy": [("privacy_scanner", "PrivacyScanner")],
    "testing": [("health_dashboard", "HealthDashboard")],
    "tech_debt": [("tech_debt", "TechDebtTracker")],
}

CATEGORY_WEIGHTS: dict[str, float] = {
    "security": 0.20,
    "encryption": 0.10,
    "code_quality": 0.10,
    "payment_safety": 0.15,
    "input_validation": 0.10,
    "session_security": 0.05,
    "rate_limiting": 0.05,
    "privacy": 0.10,
    "testing": 0.05,
    "tech_debt": 0.05,
    "naming": 0.025,
    "imports": 0.025,
}

QUALITY_GATES: list[dict[str, str]] = [
    {"name": "No secrets in source", "source": "security.yaml", "check": "_gate_no_secrets"},
    {"name": "No SQL concatenation", "source": "security.yaml", "check": "_gate_no_sql_concat"},
    {"name": "No wildcard imports", "source": "code-style.yaml", "check": "_gate_no_wildcard_imports"},
    {"name": "All tests pass", "source": "testing.yaml", "check": "_gate_tests_pass"},
    {"name": "No eval/exec from user input", "source": "security.yaml", "check": "_gate_no_eval"},
    {"name": "Commit message format", "source": "collaboration.yaml", "check": "_gate_commit_format"},
    {"name": "Branch naming convention", "source": "collaboration.yaml", "check": "_gate_branch_naming"},
    {"name": "No force pushes", "source": "collaboration.yaml", "check": "_gate_no_force_push"},
    {"name": "Constructor injection only", "source": "code-style.yaml", "check": "_gate_constructor_injection"},
    {"name": "Log levels correct", "source": "logging.yaml", "check": "_gate_log_levels"},
    {"name": "No PII in logs", "source": "logging.yaml", "check": "_gate_no_pii_logs"},
    {"name": "Env vars documented", "source": "environment.yaml", "check": "_gate_env_documented"},
    {"name": "Security headers configured", "source": "security.yaml", "check": "_gate_security_headers"},
    {"name": "Debug code removed", "source": "agent-protocol.yaml", "check": "_gate_no_debug_code"},
    {"name": "Tests alongside features", "source": "testing.yaml", "check": "_gate_tests_with_features"},
]

# Default foundry casts directory (relative to repo root)
_FOUNDRY_CASTS_DIR = ".foundry/casts"


def load_gates(cwd: str | None = None) -> list[dict[str, str]]:
    """Discover and load quality gate definitions from ``.foundry/casts/`` YAML files.

    Each YAML file contains a ``gates`` list with entries like::

        gates:
          - name: "No secrets in source"
            check: "_gate_no_secrets"
            severity: "critical"
            description: "..."

    Falls back to the built-in ``QUALITY_GATES`` if the directory is missing or
    no YAML files are found.

    Args:
        cwd: Repo root directory. If None, uses the built-in QUALITY_GATES.

    Returns:
        List of gate definition dicts (name, source, check, severity, description).
    """
    if not cwd:
        logger.debug("load_gates: no cwd provided, using built-in QUALITY_GATES")
        return QUALITY_GATES

    casts_dir = Path(cwd) / _FOUNDRY_CASTS_DIR
    if not casts_dir.is_dir():
        logger.debug("load_gates: %s not found, using built-in QUALITY_GATES", casts_dir)
        return QUALITY_GATES

    try:
        import yaml as _yaml
    except ImportError:
        logger.debug("load_gates: PyYAML not available, using built-in QUALITY_GATES")
        return QUALITY_GATES

    gates: list[dict[str, str]] = []
    yaml_files = sorted(casts_dir.glob("*.yaml")) + sorted(casts_dir.glob("*.yml"))

    if not yaml_files:
        logger.debug("load_gates: no YAML files in %s, using built-in QUALITY_GATES", casts_dir)
        return QUALITY_GATES

    for yf in yaml_files:
        try:
            data = _yaml.safe_load(yf.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "gates" not in data:
                continue
            for entry in data["gates"]:
                if not isinstance(entry, dict) or "name" not in entry or "check" not in entry:
                    continue
                gates.append({
                    "name": entry["name"],
                    "source": yf.name,
                    "check": entry["check"],
                    "severity": entry.get("severity", "info"),
                    "description": entry.get("description", ""),
                })
        except Exception as exc:
            logger.warning("load_gates: failed to parse %s: %s", yf, exc)
            continue

    if not gates:
        logger.debug("load_gates: no valid gates in %s, using built-in QUALITY_GATES", casts_dir)
        return QUALITY_GATES

    logger.info("load_gates: loaded %d gates from %d files in %s", len(gates), len(yaml_files), casts_dir)
    return gates

# Slow scanners skipped in --quick mode
_SLOW_CATEGORIES = {"testing", "tech_debt", "payment_safety"}

# Snapshot storage root
_AUDIT_HISTORY_ROOT = Path.home() / ".code-agents" / "audit-history"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _repo_hash(cwd: str) -> str:
    """Deterministic short hash for a repo path."""
    return hashlib.sha256(cwd.encode()).hexdigest()[:12]


def _walk_python_files(cwd: str) -> list[str]:
    """Collect *.py files under *cwd* (max 5000)."""
    files: list[str] = []
    for root, _dirs, names in os.walk(cwd):
        # Skip hidden dirs, node_modules, __pycache__, .git
        parts = root.split(os.sep)
        if any(p.startswith(".") or p in ("node_modules", "__pycache__", "venv", ".venv") for p in parts):
            continue
        for n in names:
            if n.endswith(".py"):
                files.append(os.path.join(root, n))
                if len(files) >= 5000:
                    return files
    return files


def _grep_files(files: list[str], pattern: str, ignore_case: bool = False) -> list[tuple[str, int, str]]:
    """Simple grep returning (filepath, lineno, line) tuples."""
    flags = re.IGNORECASE if ignore_case else 0
    regex = re.compile(pattern, flags)
    hits: list[tuple[str, int, str]] = []
    for fp in files:
        try:
            with open(fp, "r", errors="replace") as f:
                for i, line in enumerate(f, 1):
                    if regex.search(line):
                        hits.append((fp, i, line.rstrip()))
        except (OSError, UnicodeDecodeError):
            continue
    return hits


# ---------------------------------------------------------------------------
# AuditOrchestrator
# ---------------------------------------------------------------------------


class AuditOrchestrator:
    """Run all scanners in parallel, evaluate quality gates, compute scores."""

    def __init__(self, cwd: str) -> None:
        self.cwd = cwd
        self._py_files: list[str] | None = None
        self._history_dir = _AUDIT_HISTORY_ROOT / _repo_hash(cwd)

    @property
    def py_files(self) -> list[str]:
        if self._py_files is None:
            self._py_files = _walk_python_files(self.cwd)
        return self._py_files

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(
        self,
        categories: list[str] | None = None,
        quick: bool = False,
        gates_only: bool = False,
    ) -> AuditReport:
        """Execute full audit pipeline."""
        start = time.monotonic()
        logger.info("Starting audit for %s (quick=%s, gates_only=%s)", self.cwd, quick, gates_only)

        # 1. Run scanners
        cat_results: list[AuditCategory] = []
        if not gates_only:
            cat_results = self._run_all_scanners(categories=categories, quick=quick)

        # 2. Quality gates
        quality_gates = self._run_quality_gates()

        # 3. Aggregate severity counts
        critical_count = sum(c.critical for c in cat_results)
        high_count = sum(c.high for c in cat_results)
        medium_count = sum(max(0, c.findings_count - c.critical - c.high) for c in cat_results)
        low_count = 0  # placeholder — scanners that report low can contribute

        # 4. Overall score
        overall = self._compute_score(cat_results) if cat_results else 0

        # 5. Trend
        previous = self._load_previous()
        trend = self._compute_trend(overall, previous)

        duration = time.monotonic() - start
        report = AuditReport(
            overall_score=overall,
            categories=cat_results,
            quality_gates=quality_gates,
            critical_count=critical_count,
            high_count=high_count,
            medium_count=medium_count,
            low_count=low_count,
            timestamp=datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
            repo=self.cwd,
            duration_seconds=round(duration, 2),
            trend=trend,
        )

        # 6. Persist snapshot
        self._save_snapshot(report)
        logger.info("Audit complete: score=%d duration=%.1fs", overall, duration)
        return report

    # ------------------------------------------------------------------
    # Scanner execution
    # ------------------------------------------------------------------

    def _run_all_scanners(
        self,
        categories: list[str] | None = None,
        quick: bool = False,
    ) -> list[AuditCategory]:
        """Run scanners in parallel using ThreadPoolExecutor(max_workers=4)."""
        targets = categories or list(AUDIT_SCANNERS.keys())
        if quick:
            targets = [t for t in targets if t not in _SLOW_CATEGORIES]

        futures: dict[Any, str] = {}
        results: list[AuditCategory] = []

        with ThreadPoolExecutor(max_workers=4) as pool:
            for cat_name in targets:
                scanners = AUDIT_SCANNERS.get(cat_name, [])
                for module_name, class_name in scanners:
                    fut = pool.submit(self._run_scanner, module_name, class_name)
                    futures[fut] = cat_name

            # Collect per-category
            cat_data: dict[str, list[dict]] = {c: [] for c in targets}
            for fut in as_completed(futures):
                cat_name = futures[fut]
                try:
                    result = fut.result()
                    cat_data[cat_name].append(result)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Scanner future failed for %s: %s", cat_name, exc)
                    cat_data[cat_name].append({"error": str(exc)})

        # Merge per category
        for cat_name in targets:
            scanner_results = cat_data.get(cat_name, [])
            total_findings = 0
            total_critical = 0
            total_high = 0
            errors: list[str] = []
            scanners_used: list[str] = []

            for sr in scanner_results:
                if sr.get("error"):
                    errors.append(sr["error"])
                    continue
                total_findings += sr.get("findings", 0)
                total_critical += sr.get("critical", 0)
                total_high += sr.get("high", 0)
                scanners_used.append(sr.get("scanner", ""))

            # Derive score: start at 100, deduct for findings
            score = 100
            score -= total_critical * 15
            score -= total_high * 8
            score -= max(0, total_findings - total_critical - total_high) * 3
            score = max(0, min(100, score))

            results.append(AuditCategory(
                name=cat_name,
                score=score,
                findings_count=total_findings,
                critical=total_critical,
                high=total_high,
                scanner=", ".join(scanners_used),
                error="; ".join(errors) if errors else "",
            ))

        return results

    def _run_scanner(self, module_name: str, class_name: str) -> dict:
        """Lazy-import a scanner module, instantiate, and run. Never raises."""
        result: dict[str, Any] = {"scanner": f"{module_name}.{class_name}"}
        try:
            import importlib
            mod = importlib.import_module(f"code_agents.{module_name}")
            cls = getattr(mod, class_name)
            instance = cls(self.cwd) if self.cwd else cls()
            # Try common method names
            if hasattr(instance, "scan"):
                data = instance.scan()
            elif hasattr(instance, "audit"):
                data = instance.audit()
            elif hasattr(instance, "run"):
                data = instance.run()
            elif hasattr(instance, "analyze"):
                data = instance.analyze()
            else:
                data = {}

            # Normalize output
            if isinstance(data, dict):
                result["findings"] = data.get("total", data.get("findings", data.get("count", 0)))
                result["critical"] = data.get("critical", 0)
                result["high"] = data.get("high", 0)
            elif isinstance(data, list):
                result["findings"] = len(data)
                result["critical"] = sum(1 for d in data if isinstance(d, dict) and d.get("severity") == "critical")
                result["high"] = sum(1 for d in data if isinstance(d, dict) and d.get("severity") == "high")
            else:
                result["findings"] = 0
        except Exception as exc:  # noqa: BLE001
            logger.debug("Scanner %s.%s failed: %s", module_name, class_name, exc)
            result["error"] = f"{module_name}.{class_name}: {exc}"
        return result

    # ------------------------------------------------------------------
    # Quality gates
    # ------------------------------------------------------------------

    def _run_quality_gates(self) -> list[QualityGate]:
        """Evaluate every quality gate, returning results for each.

        Loads gate definitions from ``.foundry/casts/`` YAML files if available,
        falling back to the built-in ``QUALITY_GATES`` constant.
        """
        gate_defs = load_gates(self.cwd)
        gates: list[QualityGate] = []
        for gdef in gate_defs:
            method_name = gdef["check"]
            method = getattr(self, method_name, None)
            if method is None:
                gates.append(QualityGate(
                    name=gdef["name"], source=gdef["source"],
                    passed=False, message="Gate not implemented",
                    severity="info",
                ))
                continue
            try:
                gate = method()
                gate.source = gdef["source"]
                gates.append(gate)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Gate %s failed: %s", gdef["name"], exc)
                gates.append(QualityGate(
                    name=gdef["name"], source=gdef["source"],
                    passed=False, message=f"Error: {exc}",
                    severity="warning",
                ))
        return gates

    # --- Individual gate implementations ---

    def _gate_no_secrets(self) -> QualityGate:
        """Check for hardcoded secrets / API keys in source."""
        patterns = [
            r'(?i)(api[_-]?key|secret[_-]?key|password|passwd)\s*=\s*["\'][^"\']{8,}',
            r'(?i)AKIA[0-9A-Z]{16}',  # AWS access key
            r'(?i)ghp_[A-Za-z0-9]{36}',  # GitHub PAT
        ]
        hits: list[tuple[str, int, str]] = []
        for pat in patterns:
            hits.extend(_grep_files(self.py_files, pat))
        if hits:
            return QualityGate(
                name="No secrets in source", source="",
                passed=False,
                message=f"Found {len(hits)} potential secret(s) in source",
                severity="critical",
            )
        return QualityGate(name="No secrets in source", source="", passed=True, message="Clean", severity="critical")

    def _gate_no_sql_concat(self) -> QualityGate:
        """Check for SQL string concatenation (injection risk)."""
        patterns = [
            r'(?i)(select|insert|update|delete|drop)\s.*\+\s*(str\(|f["\']|request)',
            r'(?i)execute\(\s*["\'].*%s',
            r'(?i)\.format\(.*\).*(?:select|insert|update|delete)',
        ]
        hits: list[tuple[str, int, str]] = []
        for pat in patterns:
            hits.extend(_grep_files(self.py_files, pat))
        if hits:
            return QualityGate(
                name="No SQL concatenation", source="",
                passed=False,
                message=f"Found {len(hits)} SQL concat pattern(s)",
                severity="critical",
            )
        return QualityGate(name="No SQL concatenation", source="", passed=True, message="Clean", severity="critical")

    def _gate_no_wildcard_imports(self) -> QualityGate:
        """Check for wildcard imports (from X import *)."""
        hits = _grep_files(self.py_files, r'^\s*from\s+\S+\s+import\s+\*')
        if hits:
            return QualityGate(
                name="No wildcard imports", source="",
                passed=False,
                message=f"Found {len(hits)} wildcard import(s)",
                severity="warning",
            )
        return QualityGate(name="No wildcard imports", source="", passed=True, message="Clean", severity="warning")

    def _gate_tests_pass(self) -> QualityGate:
        """Check that test collection succeeds (lightweight --co -q)."""
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "--co", "-q"],
                cwd=self.cwd, capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                lines = result.stdout.strip().splitlines()
                count_line = lines[-1] if lines else ""
                return QualityGate(
                    name="All tests pass", source="",
                    passed=True, message=f"Collection OK: {count_line}",
                    severity="critical",
                )
            return QualityGate(
                name="All tests pass", source="",
                passed=False,
                message=f"pytest --co failed (rc={result.returncode})",
                severity="critical",
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            return QualityGate(
                name="All tests pass", source="",
                passed=False, message=f"Could not run pytest: {exc}",
                severity="critical",
            )

    def _gate_no_eval(self) -> QualityGate:
        """Check for eval/exec usage."""
        hits = _grep_files(self.py_files, r'\b(eval|exec)\s*\(')
        # Filter out safe patterns (e.g. ast.literal_eval)
        dangerous = [(f, l, t) for f, l, t in hits if "literal_eval" not in t]
        if dangerous:
            return QualityGate(
                name="No eval/exec from user input", source="",
                passed=False,
                message=f"Found {len(dangerous)} eval/exec call(s)",
                severity="critical",
            )
        return QualityGate(
            name="No eval/exec from user input", source="",
            passed=True, message="Clean", severity="critical",
        )

    def _gate_commit_format(self) -> QualityGate:
        """Check last 10 commits follow conventional format."""
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "-10", "--format=%s"],
                cwd=self.cwd, capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return QualityGate(
                    name="Commit message format", source="",
                    passed=False, message="git log failed",
                    severity="warning",
                )
            conventional = re.compile(r'^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\(.+\))?!?:')
            lines = [l for l in result.stdout.strip().splitlines() if l.strip()]
            bad = [l for l in lines if not conventional.match(l)]
            if bad:
                return QualityGate(
                    name="Commit message format", source="",
                    passed=False,
                    message=f"{len(bad)} non-conforming commit(s) in last 10",
                    severity="warning",
                )
            return QualityGate(
                name="Commit message format", source="",
                passed=True, message="All conventional", severity="warning",
            )
        except Exception as exc:  # noqa: BLE001
            return QualityGate(
                name="Commit message format", source="",
                passed=False, message=str(exc), severity="warning",
            )

    def _gate_branch_naming(self) -> QualityGate:
        """Check current branch name follows convention."""
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=self.cwd, capture_output=True, text=True, timeout=5,
            )
            branch = result.stdout.strip()
            if not branch:
                return QualityGate(
                    name="Branch naming convention", source="",
                    passed=True, message="Detached HEAD", severity="info",
                )
            ok_pattern = re.compile(r'^(main|master|develop|release/.+|hotfix/.+|feat(ure)?/.+|fix/.+|chore/.+|[a-z0-9._-]+)$')
            if ok_pattern.match(branch):
                return QualityGate(
                    name="Branch naming convention", source="",
                    passed=True, message=f"Branch '{branch}' OK", severity="info",
                )
            return QualityGate(
                name="Branch naming convention", source="",
                passed=False,
                message=f"Branch '{branch}' doesn't match convention",
                severity="info",
            )
        except Exception as exc:  # noqa: BLE001
            return QualityGate(
                name="Branch naming convention", source="",
                passed=False, message=str(exc), severity="info",
            )

    def _gate_no_force_push(self) -> QualityGate:
        """Check git reflog for force pushes in last 50 entries."""
        try:
            result = subprocess.run(
                ["git", "reflog", "-50"],
                cwd=self.cwd, capture_output=True, text=True, timeout=5,
            )
            if "forced-update" in result.stdout:
                count = result.stdout.count("forced-update")
                return QualityGate(
                    name="No force pushes", source="",
                    passed=False,
                    message=f"Found {count} forced-update(s) in reflog",
                    severity="warning",
                )
            return QualityGate(
                name="No force pushes", source="",
                passed=True, message="Clean", severity="warning",
            )
        except Exception as exc:  # noqa: BLE001
            return QualityGate(
                name="No force pushes", source="",
                passed=False, message=str(exc), severity="warning",
            )

    def _gate_constructor_injection(self) -> QualityGate:
        """Check for service locator anti-pattern (global imports of singletons in functions)."""
        # Simplified: look for 'from X import get_instance' or ServiceLocator patterns
        hits = _grep_files(self.py_files, r'ServiceLocator|get_instance\(\)|Container\.resolve', ignore_case=False)
        if hits:
            return QualityGate(
                name="Constructor injection only", source="",
                passed=False,
                message=f"Found {len(hits)} service locator pattern(s)",
                severity="info",
            )
        return QualityGate(
            name="Constructor injection only", source="",
            passed=True, message="Clean", severity="info",
        )

    def _gate_log_levels(self) -> QualityGate:
        """Check for misused log levels (e.g., logger.error for non-errors)."""
        # Heuristic: logger.error("Starting") or logger.warning("Success")
        bad_patterns = [
            r'logger\.error\(.*(start|begin|init|success|ok|done)',
            r'logger\.warning\(.*(success|completed|done)',
        ]
        hits: list[tuple[str, int, str]] = []
        for pat in bad_patterns:
            hits.extend(_grep_files(self.py_files, pat, ignore_case=True))
        if hits:
            return QualityGate(
                name="Log levels correct", source="",
                passed=False,
                message=f"Found {len(hits)} misused log level(s)",
                severity="warning",
            )
        return QualityGate(name="Log levels correct", source="", passed=True, message="Clean", severity="warning")

    def _gate_no_pii_logs(self) -> QualityGate:
        """Check for PII (email, card numbers) in log statements."""
        pii_in_logs = [
            r'log(?:ger)?\.\w+\(.*(?:email|card.?number|ssn|passport|phone.?number)',
            r'log(?:ger)?\.\w+\(.*\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',
        ]
        hits: list[tuple[str, int, str]] = []
        for pat in pii_in_logs:
            hits.extend(_grep_files(self.py_files, pat, ignore_case=True))
        if hits:
            return QualityGate(
                name="No PII in logs", source="",
                passed=False,
                message=f"Found {len(hits)} potential PII in log(s)",
                severity="critical",
            )
        return QualityGate(name="No PII in logs", source="", passed=True, message="Clean", severity="critical")

    def _gate_env_documented(self) -> QualityGate:
        """Check that env vars used in code appear in .env.example or docs."""
        env_example = os.path.join(self.cwd, ".env.example")
        if not os.path.isfile(env_example):
            return QualityGate(
                name="Env vars documented", source="",
                passed=False,
                message="No .env.example found",
                severity="info",
            )
        try:
            with open(env_example, "r") as f:
                documented = set(re.findall(r'^([A-Z][A-Z0-9_]+)', f.read(), re.MULTILINE))
        except OSError:
            documented = set()

        # Find os.environ / os.getenv usage
        used_vars: set[str] = set()
        env_pattern = re.compile(r'(?:os\.environ\.get|os\.getenv|os\.environ\[)\s*\(\s*["\']([A-Z][A-Z0-9_]+)')
        for fp in self.py_files:
            try:
                with open(fp, "r", errors="replace") as f:
                    for match in env_pattern.finditer(f.read()):
                        used_vars.add(match.group(1))
            except OSError:
                continue

        undocumented = used_vars - documented
        if undocumented:
            sample = sorted(undocumented)[:5]
            return QualityGate(
                name="Env vars documented", source="",
                passed=False,
                message=f"{len(undocumented)} undocumented env var(s): {', '.join(sample)}",
                severity="info",
            )
        return QualityGate(
            name="Env vars documented", source="",
            passed=True, message="All documented", severity="info",
        )

    def _gate_security_headers(self) -> QualityGate:
        """Check for security header middleware (CSP, HSTS, X-Frame-Options)."""
        header_patterns = [
            r'(?i)(x-frame-options|x-content-type-options|strict-transport-security|content-security-policy)',
            r'(?i)SecurityMiddleware|helmet|secure_headers',
        ]
        hits: list[tuple[str, int, str]] = []
        for pat in header_patterns:
            hits.extend(_grep_files(self.py_files, pat))
        if hits:
            return QualityGate(
                name="Security headers configured", source="",
                passed=True, message=f"Found {len(hits)} header config(s)",
                severity="warning",
            )
        return QualityGate(
            name="Security headers configured", source="",
            passed=False,
            message="No security header configuration found",
            severity="warning",
        )

    def _gate_no_debug_code(self) -> QualityGate:
        """Check for debug artifacts (breakpoint, debugger, console.log, pdb)."""
        patterns = [
            r'\bbreakpoint\(\)',
            r'\bpdb\.set_trace\(\)',
            r'\bdebugger\b',
            r'\bconsole\.log\(',
            r'\bprint\(.*DEBUG',
        ]
        hits: list[tuple[str, int, str]] = []
        for pat in patterns:
            hits.extend(_grep_files(self.py_files, pat))
        if hits:
            return QualityGate(
                name="Debug code removed", source="",
                passed=False,
                message=f"Found {len(hits)} debug artifact(s)",
                severity="warning",
            )
        return QualityGate(name="Debug code removed", source="", passed=True, message="Clean", severity="warning")

    def _gate_tests_with_features(self) -> QualityGate:
        """Check that source modules have corresponding test files."""
        src_modules: set[str] = set()
        test_modules: set[str] = set()
        for fp in self.py_files:
            basename = os.path.basename(fp)
            if basename.startswith("test_"):
                test_modules.add(basename.replace("test_", "", 1).replace(".py", ""))
            elif not basename.startswith("__"):
                src_modules.add(basename.replace(".py", ""))

        untested = src_modules - test_modules
        # Filter out obvious non-testable (conftest, setup, __init__)
        untested = {m for m in untested if m not in ("conftest", "setup", "__init__", "__main__")}

        if len(untested) > len(src_modules) * 0.5:
            return QualityGate(
                name="Tests alongside features", source="",
                passed=False,
                message=f"{len(untested)} modules without test files",
                severity="info",
            )
        return QualityGate(
            name="Tests alongside features", source="",
            passed=True, message=f"{len(test_modules)} test files found",
            severity="info",
        )

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _compute_score(self, categories: list[AuditCategory]) -> int:
        """Weighted average of category scores."""
        total_weight = 0.0
        weighted_sum = 0.0
        for cat in categories:
            w = CATEGORY_WEIGHTS.get(cat.name, 0.05)
            weighted_sum += cat.score * w
            total_weight += w
        if total_weight <= 0:
            return 0
        return max(0, min(100, round(weighted_sum / total_weight)))

    # ------------------------------------------------------------------
    # Persistence / trend
    # ------------------------------------------------------------------

    def _load_previous(self) -> AuditReport | None:
        """Load most recent snapshot from audit history."""
        if not self._history_dir.is_dir():
            return None
        snapshots = sorted(self._history_dir.glob("audit_*.json"), reverse=True)
        if not snapshots:
            return None
        try:
            data = json.loads(snapshots[0].read_text())
            return AuditReport(
                overall_score=data.get("overall_score", 0),
                categories=[],
                quality_gates=[],
                critical_count=data.get("critical_count", 0),
                high_count=data.get("high_count", 0),
                medium_count=data.get("medium_count", 0),
                low_count=data.get("low_count", 0),
                timestamp=data.get("timestamp", ""),
                repo=data.get("repo", ""),
                duration_seconds=data.get("duration_seconds", 0),
                trend={},
            )
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("Failed to load previous audit: %s", exc)
            return None

    def _save_snapshot(self, report: AuditReport) -> None:
        """Persist audit snapshot to disk."""
        try:
            self._history_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
            path = self._history_dir / f"audit_{ts}.json"
            data = {
                "overall_score": report.overall_score,
                "critical_count": report.critical_count,
                "high_count": report.high_count,
                "medium_count": report.medium_count,
                "low_count": report.low_count,
                "timestamp": report.timestamp,
                "repo": report.repo,
                "duration_seconds": report.duration_seconds,
                "categories": [asdict(c) for c in report.categories],
                "quality_gates": [asdict(g) for g in report.quality_gates],
            }
            path.write_text(json.dumps(data, indent=2))
            logger.debug("Saved audit snapshot to %s", path)
        except OSError as exc:
            logger.warning("Could not save audit snapshot: %s", exc)

    def _compute_trend(self, current_score: int, previous: AuditReport | None) -> dict:
        """Compare current vs previous audit."""
        if previous is None:
            return {"delta": 0, "direction": "none", "previous_score": None}
        delta = current_score - previous.overall_score
        direction = "up" if delta > 0 else ("down" if delta < 0 else "stable")
        return {
            "delta": delta,
            "direction": direction,
            "previous_score": previous.overall_score,
            "previous_timestamp": previous.timestamp,
        }

    # ------------------------------------------------------------------
    # Trend history (multiple snapshots)
    # ------------------------------------------------------------------

    def get_trend_history(self, limit: int = 20) -> list[dict]:
        """Return recent audit snapshots for trend display."""
        if not self._history_dir.is_dir():
            return []
        snapshots = sorted(self._history_dir.glob("audit_*.json"), reverse=True)[:limit]
        history: list[dict] = []
        for sp in reversed(snapshots):
            try:
                data = json.loads(sp.read_text())
                history.append({
                    "timestamp": data.get("timestamp", ""),
                    "score": data.get("overall_score", 0),
                    "critical": data.get("critical_count", 0),
                    "high": data.get("high_count", 0),
                })
            except (json.JSONDecodeError, OSError):
                continue
        return history


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def _score_bar(score: int, width: int = 10) -> str:
    """Generate a bar like '########--' for a score out of 100."""
    filled = round(score / 100 * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


def _gate_icon(gate: QualityGate) -> str:
    if gate.passed:
        return "\u2713"
    if gate.severity == "warning":
        return "\u26a0"
    return "\u2717"


def format_audit_report(report: AuditReport) -> str:
    """Rich terminal box report."""
    w = 56  # inner width
    hr = "\u2500" * w

    lines: list[str] = []
    lines.append(f"\u256d\u2500 Code Agents Audit {'─' * (w - 20)}\u256e")

    # Overall score
    bar = _score_bar(report.overall_score)
    lines.append(f"\u2502 Overall Score: {report.overall_score}/100 {bar}{'':>{w - 29 - len(bar)}}\u2502")

    # Severity summary
    sev = f"Critical: {report.critical_count}  High: {report.high_count}  Medium: {report.medium_count}  Low: {report.low_count}"
    lines.append(f"\u2502 {sev:<{w}}\u2502")

    # Trend
    trend = report.trend
    if trend.get("direction") == "up":
        trend_str = f"\u25b2 +{trend['delta']} from last audit"
    elif trend.get("direction") == "down":
        trend_str = f"\u25bc {trend['delta']} from last audit"
    elif trend.get("direction") == "stable":
        trend_str = "\u2500 No change from last audit"
    else:
        trend_str = "First audit"
    lines.append(f"\u2502 Trend: {trend_str:<{w - 8}}\u2502")

    # Duration
    dur = f"Duration: {report.duration_seconds:.1f}s"
    lines.append(f"\u2502 {dur:<{w}}\u2502")

    # Category scores
    if report.categories:
        lines.append(f"\u251c{hr}\u2524")
        lines.append(f"\u2502 {'Category Scores:':<{w}}\u2502")
        for cat in sorted(report.categories, key=lambda c: c.score):
            bar = _score_bar(cat.score)
            label = f"  {cat.name:<20} {cat.score:>3}/100 {bar}"
            err = f" [{cat.error[:20]}]" if cat.error else ""
            entry = label + err
            lines.append(f"\u2502 {entry:<{w}}\u2502")

    # Quality gates
    if report.quality_gates:
        lines.append(f"\u251c{hr}\u2524")
        lines.append(f"\u2502 {'Quality Gates:':<{w}}\u2502")
        for gate in report.quality_gates:
            icon = _gate_icon(gate)
            detail = f" ({gate.message})" if not gate.passed and gate.message != "Clean" else ""
            entry = f"  {icon} {gate.name}{detail}"
            if len(entry) > w:
                entry = entry[:w - 1] + "\u2026"
            lines.append(f"\u2502 {entry:<{w}}\u2502")

    lines.append(f"\u2570{hr}\u256f")
    return "\n".join(lines)


def format_audit_json(report: AuditReport) -> str:
    """Serialize report to JSON."""
    return json.dumps({
        "overall_score": report.overall_score,
        "critical_count": report.critical_count,
        "high_count": report.high_count,
        "medium_count": report.medium_count,
        "low_count": report.low_count,
        "timestamp": report.timestamp,
        "repo": report.repo,
        "duration_seconds": report.duration_seconds,
        "trend": report.trend,
        "categories": [asdict(c) for c in report.categories],
        "quality_gates": [asdict(g) for g in report.quality_gates],
    }, indent=2)


def format_audit_html(report: AuditReport) -> str:
    """Generate a standalone HTML dashboard for the audit report."""
    cats_json = json.dumps([asdict(c) for c in report.categories])
    gates_json = json.dumps([asdict(g) for g in report.quality_gates])

    gate_rows = ""
    for g in report.quality_gates:
        icon = "&#x2713;" if g.passed else ("&#x26A0;" if g.severity == "warning" else "&#x2717;")
        color = "#22c55e" if g.passed else ("#eab308" if g.severity == "warning" else "#ef4444")
        gate_rows += f'<tr><td style="color:{color};font-size:1.2em">{icon}</td><td>{g.name}</td><td>{g.message}</td></tr>\n'

    cat_rows = ""
    for c in sorted(report.categories, key=lambda x: x.score):
        bar_pct = c.score
        color = "#22c55e" if c.score >= 80 else ("#eab308" if c.score >= 50 else "#ef4444")
        cat_rows += (
            f'<tr><td>{c.name}</td><td>{c.score}/100</td>'
            f'<td><div style="background:#e5e7eb;border-radius:4px;height:16px;width:200px">'
            f'<div style="background:{color};height:100%;width:{bar_pct}%;border-radius:4px"></div>'
            f'</div></td><td>{c.findings_count}</td></tr>\n'
        )

    trend = report.trend
    trend_html = ""
    if trend.get("direction") == "up":
        trend_html = f'<span style="color:#22c55e">&#x25B2; +{trend["delta"]}</span>'
    elif trend.get("direction") == "down":
        trend_html = f'<span style="color:#ef4444">&#x25BC; {trend["delta"]}</span>'
    else:
        trend_html = '<span style="color:#6b7280">First audit</span>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Code Agents Audit Report</title>
<style>
  body {{ font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; background: #0f172a; color: #e2e8f0; }}
  h1 {{ color: #38bdf8; }} h2 {{ color: #94a3b8; border-bottom: 1px solid #334155; padding-bottom: .5rem; }}
  .score-big {{ font-size: 4rem; font-weight: bold; color: {"#22c55e" if report.overall_score >= 80 else "#eab308" if report.overall_score >= 50 else "#ef4444"}; }}
  .meta {{ color: #94a3b8; font-size: .9rem; }}
  table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
  th, td {{ padding: .5rem .75rem; text-align: left; border-bottom: 1px solid #1e293b; }}
  th {{ color: #94a3b8; font-weight: 600; }}
  .card {{ background: #1e293b; border-radius: 8px; padding: 1.5rem; margin: 1rem 0; }}
  .severity {{ display: flex; gap: 2rem; margin: 1rem 0; }}
  .severity span {{ padding: .25rem .75rem; border-radius: 4px; font-weight: 600; }}
  .sev-crit {{ background: #7f1d1d; color: #fca5a5; }} .sev-high {{ background: #78350f; color: #fbbf24; }}
  .sev-med {{ background: #1e3a5f; color: #93c5fd; }} .sev-low {{ background: #14532d; color: #86efac; }}
</style>
</head>
<body>
<h1>Code Agents Audit Report</h1>
<div class="card">
  <div class="score-big">{report.overall_score}/100</div>
  <div>Trend: {trend_html}</div>
  <div class="severity">
    <span class="sev-crit">Critical: {report.critical_count}</span>
    <span class="sev-high">High: {report.high_count}</span>
    <span class="sev-med">Medium: {report.medium_count}</span>
    <span class="sev-low">Low: {report.low_count}</span>
  </div>
  <div class="meta">Repo: {report.repo} | {report.timestamp} | Duration: {report.duration_seconds}s</div>
</div>
<h2>Category Scores</h2>
<table><tr><th>Category</th><th>Score</th><th>Bar</th><th>Findings</th></tr>
{cat_rows}</table>
<h2>Quality Gates</h2>
<table><tr><th></th><th>Gate</th><th>Detail</th></tr>
{gate_rows}</table>
</body>
</html>"""
