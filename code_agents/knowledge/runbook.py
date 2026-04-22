"""Runbook Executor — markdown runbooks → executable steps with safety gates."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.knowledge.runbook")


@dataclass
class RunbookStep:
    index: int
    title: str
    command: str = ""  # shell command
    description: str = ""  # descriptive text
    is_dangerous: bool = False
    expected_output: str = ""
    on_failure: str = "stop"  # stop, continue, rollback
    timeout: int = 60
    is_manual: bool = False  # requires human action


@dataclass
class StepResult:
    step: RunbookStep
    status: str = "pending"  # success, failed, skipped, pending, manual
    output: str = ""
    error: str = ""
    duration_ms: float = 0


@dataclass
class RunbookSpec:
    name: str
    description: str = ""
    steps: list[RunbookStep] = field(default_factory=list)
    source: str = ""  # file path
    tags: list[str] = field(default_factory=list)
    version: str = ""


@dataclass
class RunbookExecution:
    spec: RunbookSpec
    results: list[StepResult] = field(default_factory=list)
    status: str = "pending"  # completed, failed, aborted
    dry_run: bool = False
    total_duration_ms: float = 0

    @property
    def steps_completed(self) -> int:
        return sum(1 for r in self.results if r.status == "success")

    @property
    def steps_failed(self) -> int:
        return sum(1 for r in self.results if r.status == "failed")


# Dangerous command patterns that require confirmation
_DANGEROUS_PATTERNS = [
    r"\brm\s+-r",
    r"\brm\s+-f",
    r"\bdrop\s+(?:table|database|index)",
    r"\bdelete\s+from\b",
    r"\btruncate\b",
    r"\bgit\s+(?:push\s+--force|reset\s+--hard|clean\s+-f)",
    r"\bkubectl\s+(?:delete|drain|cordon)",
    r"\bdocker\s+(?:rm|rmi|system\s+prune)",
    r"\bsystemctl\s+(?:stop|disable|restart)",
    r"\breboot\b",
    r"\bshutdown\b",
    r"\bchmod\s+777",
    r"\bchown\s+-R",
    r"\biptables\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
]
_DANGEROUS_RE = re.compile("|".join(_DANGEROUS_PATTERNS), re.IGNORECASE)

# Common runbook directories to scan
_RUNBOOK_DIRS = ["docs/runbooks", "runbooks", ".runbooks", "docs/playbooks",
                 "playbooks", "docs/operations", "ops"]


class RunbookExecutor:
    """Discovers, loads, and executes runbooks from markdown files."""

    def __init__(self, cwd: str = ".", dry_run: bool = False):
        self.cwd = os.path.abspath(cwd)
        self.dry_run = dry_run

    def list_runbooks(self) -> list[RunbookSpec]:
        """List all available runbooks."""
        paths = self._discover_runbooks()
        specs = []
        for path in paths:
            try:
                spec = self._parse_markdown(path)
                specs.append(spec)
            except Exception as exc:
                logger.warning("Failed to parse runbook %s: %s", path, exc)
        return specs

    def load(self, name: str) -> Optional[RunbookSpec]:
        """Load a runbook by name."""
        # Search by exact name or fuzzy match
        runbooks = self.list_runbooks()
        for rb in runbooks:
            if rb.name.lower() == name.lower():
                return rb
        # Fuzzy match
        for rb in runbooks:
            if name.lower() in rb.name.lower():
                return rb
        # Try as file path
        if os.path.exists(name):
            return self._parse_markdown(name)
        full = os.path.join(self.cwd, name)
        if os.path.exists(full):
            return self._parse_markdown(full)
        return None

    def execute(self, spec: RunbookSpec) -> RunbookExecution:
        """Execute a runbook, step by step."""
        execution = RunbookExecution(spec=spec, dry_run=self.dry_run)
        start_time = time.time()

        for step in spec.steps:
            result = self._execute_step(step)
            execution.results.append(result)

            if result.status == "failed" and step.on_failure == "stop":
                execution.status = "failed"
                break

        if execution.status == "pending":
            if execution.steps_failed > 0:
                execution.status = "failed"
            else:
                execution.status = "completed"

        execution.total_duration_ms = (time.time() - start_time) * 1000
        return execution

    def _discover_runbooks(self) -> list[str]:
        """Scan common directories for runbook files."""
        paths = []
        for d in _RUNBOOK_DIRS:
            full = os.path.join(self.cwd, d)
            if os.path.isdir(full):
                for f in sorted(os.listdir(full)):
                    if f.endswith((".md", ".markdown", ".txt")):
                        paths.append(os.path.join(full, f))
        return paths

    def _parse_markdown(self, path: str) -> RunbookSpec:
        """Parse a markdown file into a RunbookSpec."""
        content = Path(path).read_text(errors="replace")
        lines = content.split("\n")

        name = Path(path).stem.replace("-", " ").replace("_", " ").title()
        description = ""
        tags: list[str] = []
        steps: list[RunbookStep] = []

        # Parse YAML frontmatter if present
        if lines and lines[0].strip() == "---":
            end_idx = -1
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    end_idx = i
                    break
            if end_idx > 0:
                for line in lines[1:end_idx]:
                    if line.startswith("name:"):
                        name = line.split(":", 1)[1].strip().strip('"\'')
                    elif line.startswith("description:"):
                        description = line.split(":", 1)[1].strip().strip('"\'')
                    elif line.startswith("tags:"):
                        tags = [t.strip().strip("-").strip()
                                for t in line.split(":", 1)[1].strip().strip("[]").split(",")]
                lines = lines[end_idx + 1:]

        # Parse steps from headers + code blocks
        current_title = ""
        current_desc_lines: list[str] = []
        step_index = 0
        in_code_block = False
        code_lang = ""
        code_lines: list[str] = []

        for line in lines:
            # Title from H1 (use as name if not set from frontmatter)
            if line.startswith("# ") and not steps:
                if name == Path(path).stem.replace("-", " ").replace("_", " ").title():
                    name = line[2:].strip()
                continue

            # Step headers (H2, H3, numbered headers)
            step_match = re.match(r"^#{2,3}\s+(?:Step\s+\d+[.:]\s*)?(.+)", line, re.IGNORECASE)
            if not step_match:
                step_match = re.match(r"^\d+\.\s+(.+)", line)

            if step_match and not in_code_block:
                # Save previous step
                if current_title:
                    steps.append(self._build_step(
                        step_index, current_title, current_desc_lines, code_lines,
                    ))
                    step_index += 1
                    code_lines = []
                current_title = step_match.group(1).strip()
                current_desc_lines = []
                continue

            # Code blocks
            if line.strip().startswith("```"):
                if in_code_block:
                    in_code_block = False
                else:
                    in_code_block = True
                    code_lang = line.strip()[3:].strip()
                continue

            if in_code_block:
                code_lines.append(line)
            else:
                if current_title:
                    current_desc_lines.append(line)
                elif not description:
                    description += line.strip() + " "

        # Save last step
        if current_title:
            steps.append(self._build_step(
                step_index, current_title, current_desc_lines, code_lines,
            ))

        return RunbookSpec(
            name=name,
            description=description.strip(),
            steps=steps,
            source=path,
            tags=tags,
        )

    def _build_step(self, index: int, title: str, desc_lines: list[str],
                    code_lines: list[str]) -> RunbookStep:
        """Build a RunbookStep from parsed content."""
        command = "\n".join(code_lines).strip()
        description = "\n".join(desc_lines).strip()
        is_dangerous = bool(_DANGEROUS_RE.search(command)) if command else False

        # Check for manual step indicators
        is_manual = bool(re.search(
            r"(?:manual|human|verify|check|confirm|wait for)",
            title + " " + description, re.IGNORECASE,
        )) and not command

        # Determine failure behavior
        on_failure = "stop"
        if re.search(r"(?:optional|skip|ignore)", title + " " + description, re.IGNORECASE):
            on_failure = "continue"

        return RunbookStep(
            index=index,
            title=title,
            command=command,
            description=description,
            is_dangerous=is_dangerous,
            on_failure=on_failure,
            is_manual=is_manual,
        )

    def _execute_step(self, step: RunbookStep) -> StepResult:
        """Execute a single step."""
        result = StepResult(step=step)

        if step.is_manual:
            result.status = "manual"
            result.output = f"Manual step: {step.description or step.title}"
            return result

        if not step.command:
            result.status = "skipped"
            result.output = "No command to execute"
            return result

        if self.dry_run:
            result.status = "skipped"
            result.output = f"[DRY RUN] Would execute: {step.command[:200]}"
            return result

        if step.is_dangerous:
            result.status = "skipped"
            result.output = f"[DANGEROUS] Skipped — requires explicit confirmation: {step.command[:200]}"
            logger.warning("Dangerous step skipped: %s", step.title)
            return result

        start = time.time()
        try:
            proc = subprocess.run(
                step.command,
                shell=True,
                cwd=self.cwd,
                capture_output=True,
                text=True,
                timeout=step.timeout,
            )
            result.duration_ms = (time.time() - start) * 1000
            result.output = proc.stdout[:2000]
            result.error = proc.stderr[:500]

            if proc.returncode == 0:
                result.status = "success"
            else:
                result.status = "failed"

        except subprocess.TimeoutExpired:
            result.status = "failed"
            result.error = f"Timed out after {step.timeout}s"
            result.duration_ms = step.timeout * 1000
        except Exception as exc:
            result.status = "failed"
            result.error = str(exc)[:500]

        return result


def format_runbook_list(runbooks: list[RunbookSpec]) -> str:
    """Format runbook list for display."""
    if not runbooks:
        return "No runbooks found. Create runbooks in docs/runbooks/ or runbooks/ directory."

    lines = ["## Available Runbooks", ""]
    for rb in runbooks:
        tags = f" [{', '.join(rb.tags)}]" if rb.tags else ""
        steps = f"{len(rb.steps)} steps"
        lines.append(f"- **{rb.name}** — {rb.description or 'No description'} ({steps}){tags}")
    return "\n".join(lines)


def format_execution(execution: RunbookExecution) -> str:
    """Format runbook execution results."""
    spec = execution.spec
    lines = [
        "## Runbook Execution",
        "",
        f"**Runbook:** {spec.name}",
        f"**Status:** {execution.status}",
        f"**Mode:** {'Dry Run' if execution.dry_run else 'Live'}",
        f"**Steps:** {execution.steps_completed}/{len(spec.steps)} completed"
        f" ({execution.steps_failed} failed)",
        f"**Duration:** {execution.total_duration_ms:.0f}ms",
        "",
    ]

    if execution.results:
        lines.extend(["### Steps", ""])
        for r in execution.results:
            icon = {
                "success": "✅", "failed": "❌", "skipped": "⏭️",
                "pending": "⏳", "manual": "👤",
            }.get(r.status, "❓")
            lines.append(f"{icon} **Step {r.step.index + 1}: {r.step.title}** — {r.status}")
            if r.step.is_dangerous:
                lines.append(f"  ⚠️  Dangerous command")
            if r.output and r.status != "pending":
                lines.append(f"  Output: {r.output[:200]}")
            if r.error:
                lines.append(f"  Error: {r.error[:200]}")
            if r.duration_ms > 0:
                lines.append(f"  Duration: {r.duration_ms:.0f}ms")

    return "\n".join(lines)
