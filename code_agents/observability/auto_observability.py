"""Auto-Observability — inject structured logging, tracing, and metrics into code."""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.observability.auto_observability")


@dataclass
class InjectionPoint:
    """A point in code where observability should be added."""
    file_path: str = ""
    line_number: int = 0
    kind: str = ""  # "logging", "tracing", "metric"
    code_snippet: str = ""
    injection_code: str = ""
    reason: str = ""


@dataclass
class ObservabilityPlan:
    """Plan for adding observability to a codebase."""
    injections: list[InjectionPoint] = field(default_factory=list)
    files_analyzed: int = 0
    functions_found: int = 0
    already_instrumented: int = 0
    coverage_before: float = 0.0
    coverage_after: float = 0.0
    warnings: list[str] = field(default_factory=list)


FUNC_PATTERN = re.compile(
    r"^(\s*)(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)\s*(?:->\s*\S+)?\s*:", re.MULTILINE
)
CLASS_PATTERN = re.compile(r"^class\s+(\w+)", re.MULTILINE)
LOGGER_PATTERN = re.compile(r"logger\.\w+\(|logging\.\w+\(|log\.\w+\(")
TRACE_PATTERN = re.compile(r"@trace|tracer\.start_span|with\s+tracer")
METRIC_PATTERN = re.compile(r"counter\.|histogram\.|gauge\.|metrics?\.")


class AutoObservability:
    """Analyzes code and generates observability injection plan."""

    def __init__(self, cwd: str):
        self.cwd = cwd

    def analyze(self, file_contents: dict[str, str],
                include_logging: bool = True,
                include_tracing: bool = True,
                include_metrics: bool = True) -> ObservabilityPlan:
        """Analyze source files and produce an observability injection plan."""
        logger.info("Analyzing %d files for observability gaps", len(file_contents))

        plan = ObservabilityPlan(files_analyzed=len(file_contents))
        total_funcs = 0
        instrumented = 0

        for fpath, content in file_contents.items():
            funcs = self._find_functions(content)
            total_funcs += len(funcs)

            for func in funcs:
                func_body = self._get_function_body(content, func["start"], func["indent"])
                has_log = bool(LOGGER_PATTERN.search(func_body))
                has_trace = bool(TRACE_PATTERN.search(func_body))
                has_metric = bool(METRIC_PATTERN.search(func_body))

                if has_log or has_trace or has_metric:
                    instrumented += 1

                if include_logging and not has_log:
                    inj = self._suggest_logging(fpath, func, func_body)
                    if inj:
                        plan.injections.append(inj)

                if include_tracing and not has_trace:
                    inj = self._suggest_tracing(fpath, func)
                    if inj:
                        plan.injections.append(inj)

                if include_metrics and not has_metric:
                    inj = self._suggest_metrics(fpath, func, func_body)
                    if inj:
                        plan.injections.append(inj)

        plan.functions_found = total_funcs
        plan.already_instrumented = instrumented
        plan.coverage_before = (instrumented / total_funcs * 100) if total_funcs else 0.0
        potential = instrumented + len(set(i.file_path + str(i.line_number) for i in plan.injections))
        plan.coverage_after = (potential / total_funcs * 100) if total_funcs else 0.0

        logger.info(
            "Plan: %d injections, coverage %.1f%% -> %.1f%%",
            len(plan.injections), plan.coverage_before, plan.coverage_after,
        )
        return plan

    def _find_functions(self, content: str) -> list[dict]:
        """Find all function definitions in content."""
        functions = []
        for m in FUNC_PATTERN.finditer(content):
            indent = len(m.group(1))
            name = m.group(2)
            params = m.group(3)
            line_num = content[:m.start()].count("\n") + 1
            functions.append({
                "name": name,
                "params": params,
                "line": line_num,
                "start": m.start(),
                "indent": indent,
                "is_private": name.startswith("_"),
            })
        return functions

    def _get_function_body(self, content: str, start: int, indent: int) -> str:
        """Extract function body from start position."""
        lines = content[start:].split("\n")
        body_lines = [lines[0]] if lines else []
        for line in lines[1:]:
            stripped = line.lstrip()
            if stripped and not line.startswith(" " * (indent + 1)) and not stripped.startswith("#"):
                if not stripped.startswith("@"):
                    break
            body_lines.append(line)
        return "\n".join(body_lines[:50])

    def _suggest_logging(self, fpath: str, func: dict, body: str) -> Optional[InjectionPoint]:
        """Suggest logging injection for a function."""
        if func["is_private"] and "self" not in func["params"]:
            return None
        indent = " " * (func["indent"] + 4)
        params = [p.strip().split(":")[0].strip() for p in func["params"].split(",")
                  if p.strip() and p.strip() != "self" and p.strip() != "cls"]
        param_log = ", ".join(f"{p}=%s" for p in params[:3])
        param_args = ", ".join(params[:3])
        if param_log:
            code = f'{indent}logger.info("{func["name"]} called: {param_log}", {param_args})'
        else:
            code = f'{indent}logger.info("{func["name"]} called")'

        return InjectionPoint(
            file_path=fpath,
            line_number=func["line"] + 1,
            kind="logging",
            code_snippet=f"def {func['name']}({func['params']}):",
            injection_code=code,
            reason=f"Function {func['name']} has no logging",
        )

    def _suggest_tracing(self, fpath: str, func: dict) -> Optional[InjectionPoint]:
        """Suggest tracing span for a function."""
        if func["is_private"]:
            return None
        indent = " " * func["indent"]
        code = f'{indent}@tracer.start_as_current_span("{func["name"]}")'
        return InjectionPoint(
            file_path=fpath,
            line_number=func["line"],
            kind="tracing",
            code_snippet=f"def {func['name']}({func['params']}):",
            injection_code=code,
            reason=f"Function {func['name']} has no tracing span",
        )

    def _suggest_metrics(self, fpath: str, func: dict, body: str) -> Optional[InjectionPoint]:
        """Suggest metrics for a function if it looks like it processes data."""
        indicator_patterns = [
            re.compile(r"(for|while)\s"),
            re.compile(r"(request|response|query|process|handle)"),
            re.compile(r"(db|database|cache|queue|api)"),
        ]
        is_data_func = any(p.search(body) for p in indicator_patterns)
        if not is_data_func or func["is_private"]:
            return None
        indent = " " * (func["indent"] + 4)
        code = f'{indent}metrics.counter("{func["name"]}_calls_total").inc()'
        return InjectionPoint(
            file_path=fpath,
            line_number=func["line"] + 1,
            kind="metric",
            code_snippet=f"def {func['name']}({func['params']}):",
            injection_code=code,
            reason=f"Data-processing function {func['name']} lacks metrics",
        )


def format_plan(plan: ObservabilityPlan) -> str:
    """Format plan as human-readable text."""
    lines = [
        "# Auto-Observability Plan",
        f"Files analyzed: {plan.files_analyzed}",
        f"Functions found: {plan.functions_found}",
        f"Already instrumented: {plan.already_instrumented}",
        f"Coverage: {plan.coverage_before:.1f}% -> {plan.coverage_after:.1f}%",
        f"Injections proposed: {len(plan.injections)}",
        "",
    ]
    for inj in plan.injections:
        lines.append(f"[{inj.kind}] {inj.file_path}:{inj.line_number} - {inj.reason}")
        lines.append(f"  + {inj.injection_code.strip()}")
        lines.append("")
    return "\n".join(lines)
