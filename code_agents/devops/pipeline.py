"""Agent Pipelines — declarative YAML-defined agent chains with conditions.

Define sequential/conditional agent execution pipelines where each step's
output feeds the next. Like GitHub Actions but for agent chains.

Pipeline YAML format:
    name: review-and-deploy
    description: Review code, run tests, then deploy
    steps:
      - agent: code-reviewer
        prompt: "Review the latest changes"
        condition: "always"
      - agent: code-tester
        prompt: "Run tests on the reviewed code"
        condition: "prev_score >= 3"
      - agent: jenkins-cicd
        prompt: "Deploy to staging"
        condition: "all_passed"

Usage:
    code-agents pipeline run review-and-deploy
    code-agents pipeline list
    code-agents pipeline create <name>
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger("code_agents.devops.pipeline")

PIPELINES_DIR_NAME = ".code-agents/pipelines"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class PipelineStep:
    """A single step in an agent pipeline."""
    agent: str
    prompt: str = ""
    condition: str = "always"  # "always", "prev_passed", "prev_score >= N", "all_passed"
    timeout_s: int = 300
    name: str = ""
    on_failure: str = "stop"  # "stop", "skip", "continue"


@dataclass
class StepResult:
    """Result of executing a pipeline step."""
    step_index: int
    step_name: str
    agent: str
    status: str = "pending"  # "pending", "running", "passed", "failed", "skipped"
    response: str = ""
    score: int = 0  # 1-5 quality/confidence
    latency_ms: int = 0
    error: str = ""
    started_at: str = ""
    finished_at: str = ""


@dataclass
class PipelineConfig:
    """Pipeline definition loaded from YAML."""
    name: str
    description: str = ""
    steps: list[PipelineStep] = field(default_factory=list)
    variables: dict[str, str] = field(default_factory=dict)
    created_at: str = ""
    source_file: str = ""


@dataclass
class PipelineRun:
    """A single execution of a pipeline."""
    run_id: str = ""
    pipeline_name: str = ""
    status: str = "pending"  # "pending", "running", "completed", "failed"
    results: list[StepResult] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    context: dict = field(default_factory=dict)  # accumulated context across steps


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------


def _evaluate_condition(condition: str, results: list[StepResult]) -> bool:
    """Evaluate a step condition based on previous results."""
    condition = condition.strip().lower()

    if condition == "always":
        return True

    if condition == "prev_passed":
        if not results:
            return True
        return results[-1].status == "passed"

    if condition == "all_passed":
        return all(r.status in ("passed", "skipped") for r in results)

    if condition == "any_failed":
        return any(r.status == "failed" for r in results)

    # prev_score >= N
    match = re.match(r"prev_score\s*(>=|>|<=|<|==|!=)\s*(\d+)", condition)
    if match:
        op, val = match.group(1), int(match.group(2))
        if not results:
            return True
        prev_score = results[-1].score
        ops = {
            ">=": prev_score >= val,
            ">": prev_score > val,
            "<=": prev_score <= val,
            "<": prev_score < val,
            "==": prev_score == val,
            "!=": prev_score != val,
        }
        return ops.get(op, True)

    logger.warning("Unknown condition '%s', defaulting to True", condition)
    return True


# ---------------------------------------------------------------------------
# Pipeline loader
# ---------------------------------------------------------------------------


class PipelineLoader:
    """Loads pipeline definitions from YAML files."""

    def __init__(self, repo_path: str | None = None):
        self.repo_path = repo_path or os.getenv("TARGET_REPO_PATH", os.getcwd())
        self._pipelines_dir = Path(self.repo_path) / PIPELINES_DIR_NAME
        self._builtin_dir = Path(__file__).resolve().parent.parent / "pipelines"

    def _parse_yaml(self, path: Path) -> Optional[PipelineConfig]:
        """Parse a pipeline YAML file."""
        try:
            data = yaml.safe_load(path.read_text())
            if not data or not isinstance(data, dict):
                return None

            steps = []
            for s in data.get("steps", []):
                steps.append(PipelineStep(
                    agent=s.get("agent", ""),
                    prompt=s.get("prompt", ""),
                    condition=s.get("condition", "always"),
                    timeout_s=s.get("timeout_s", 300),
                    name=s.get("name", ""),
                    on_failure=s.get("on_failure", "stop"),
                ))

            return PipelineConfig(
                name=data.get("name", path.stem),
                description=data.get("description", ""),
                steps=steps,
                variables=data.get("variables", {}),
                created_at=data.get("created_at", ""),
                source_file=str(path),
            )
        except (yaml.YAMLError, OSError, TypeError) as e:
            logger.warning("Failed to parse pipeline %s: %s", path, e)
            return None

    def list_pipelines(self) -> list[PipelineConfig]:
        """List all available pipelines."""
        pipelines = []
        for d in [self._pipelines_dir, self._builtin_dir]:
            if d.exists():
                for f in sorted(d.glob("*.yaml")) + sorted(d.glob("*.yml")):
                    p = self._parse_yaml(f)
                    if p:
                        pipelines.append(p)
        return pipelines

    def get_pipeline(self, name: str) -> Optional[PipelineConfig]:
        """Get a pipeline by name."""
        for p in self.list_pipelines():
            if p.name == name:
                return p
        return None

    def create_pipeline(self, config: PipelineConfig) -> Path:
        """Save a new pipeline definition to YAML."""
        self._pipelines_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{config.name}.yaml"
        path = self._pipelines_dir / filename

        data = {
            "name": config.name,
            "description": config.description,
            "created_at": datetime.now().isoformat(),
            "steps": [
                {
                    "agent": s.agent,
                    "prompt": s.prompt,
                    "condition": s.condition,
                    "timeout_s": s.timeout_s,
                    "name": s.name or f"Step {i+1}",
                    "on_failure": s.on_failure,
                }
                for i, s in enumerate(config.steps)
            ],
            "variables": config.variables,
        }

        path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
        logger.info("Created pipeline: %s -> %s", config.name, path)
        return path


# ---------------------------------------------------------------------------
# Pipeline executor
# ---------------------------------------------------------------------------


class PipelineExecutor:
    """Executes agent pipelines step by step."""

    def __init__(self, url: str = ""):
        self.url = url or f"http://127.0.0.1:{os.getenv('PORT', '8000')}"

    async def _run_step(
        self, step: PipelineStep, context: dict, prev_results: list[StepResult]
    ) -> StepResult:
        """Execute a single pipeline step."""
        result = StepResult(
            step_index=len(prev_results),
            step_name=step.name or step.agent,
            agent=step.agent,
            started_at=datetime.now().isoformat(),
        )

        # Check condition
        if not _evaluate_condition(step.condition, prev_results):
            result.status = "skipped"
            result.finished_at = datetime.now().isoformat()
            return result

        result.status = "running"

        # Build prompt with context from previous steps
        prompt = step.prompt
        if context:
            context_block = "\n".join(
                f"[Previous Step: {k}]\n{v}" for k, v in context.items()
            )
            prompt = f"{prompt}\n\n## Context from previous steps:\n{context_block}"

        try:
            import httpx

            payload = {
                "model": "auto",
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            }

            start = time.monotonic()
            async with httpx.AsyncClient(timeout=step.timeout_s) as client:
                resp = await client.post(
                    f"{self.url}/v1/chat/completions",
                    json=payload,
                    headers={"X-Agent": step.agent},
                )
                result.latency_ms = int((time.monotonic() - start) * 1000)

                if resp.status_code != 200:
                    result.status = "failed"
                    result.error = f"HTTP {resp.status_code}"
                else:
                    data = resp.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    result.response = content
                    result.status = "passed"

                    # Extract confidence score if agent provides one
                    score_match = re.search(r'\[CONFIDENCE:(\d)\]', content)
                    if score_match:
                        result.score = int(score_match.group(1))
                    else:
                        result.score = 4  # default passing score

        except Exception as e:
            result.status = "failed"
            result.error = str(e)

        result.finished_at = datetime.now().isoformat()
        return result

    async def run(
        self, pipeline: PipelineConfig, progress_callback=None
    ) -> PipelineRun:
        """Execute a full pipeline."""
        run = PipelineRun(
            run_id=str(uuid.uuid4())[:8],
            pipeline_name=pipeline.name,
            status="running",
            started_at=datetime.now().isoformat(),
        )

        context: dict[str, str] = {}

        for i, step in enumerate(pipeline.steps):
            result = await self._run_step(step, context, run.results)
            run.results.append(result)

            # Add response to context for next steps
            if result.response:
                key = step.name or f"step_{i}"
                context[key] = result.response[:2000]  # truncate for context window

            if progress_callback:
                progress_callback(i + 1, len(pipeline.steps), result)

            # Handle failure
            if result.status == "failed":
                if step.on_failure == "stop":
                    run.status = "failed"
                    break
                elif step.on_failure == "skip":
                    continue

        if run.status != "failed":
            run.status = "completed"

        run.finished_at = datetime.now().isoformat()
        run.context = context
        return run

    @staticmethod
    def print_run(run: PipelineRun) -> None:
        """Pretty-print a pipeline run."""
        try:
            from rich.console import Console
            from rich.table import Table
            from rich.panel import Panel

            console = Console()

            # Status color
            status_color = {"completed": "green", "failed": "red", "running": "yellow"}.get(
                run.status, "white"
            )

            console.print(Panel(
                f"Pipeline: [bold]{run.pipeline_name}[/bold]  |  "
                f"Status: [{status_color}]{run.status}[/{status_color}]  |  "
                f"Steps: {len(run.results)}",
                title=f"Pipeline Run {run.run_id}",
                border_style="cyan",
            ))

            table = Table(show_lines=True)
            table.add_column("#", justify="center", width=3)
            table.add_column("Step", style="bold", max_width=20)
            table.add_column("Agent", max_width=15)
            table.add_column("Status", justify="center")
            table.add_column("Score", justify="center")
            table.add_column("Latency", justify="right")
            table.add_column("Notes", max_width=35)

            for r in run.results:
                sc = {"passed": "green", "failed": "red", "skipped": "dim", "running": "yellow"}.get(
                    r.status, "white"
                )
                notes = r.error[:35] if r.error else (r.response[:35].replace("\n", " ") if r.response else "")
                table.add_row(
                    str(r.step_index + 1),
                    r.step_name,
                    r.agent,
                    f"[{sc}]{r.status}[/{sc}]",
                    f"{r.score}/5" if r.score else "—",
                    f"{r.latency_ms:,}ms" if r.latency_ms else "—",
                    notes,
                )
            console.print(table)

        except ImportError:
            print(f"\n=== Pipeline Run {run.run_id} ===")
            print(f"Pipeline: {run.pipeline_name}  Status: {run.status}")
            for r in run.results:
                print(f"  [{r.step_index+1}] {r.step_name:<20} {r.agent:<15} {r.status}")
            print()


# ---------------------------------------------------------------------------
# Built-in pipeline templates
# ---------------------------------------------------------------------------

BUILTIN_PIPELINES = [
    {
        "name": "review-test-deploy",
        "description": "Review code, run tests, deploy if all pass",
        "steps": [
            {"agent": "code-reviewer", "prompt": "Review the latest git diff for code quality, security, and best practices", "name": "Code Review"},
            {"agent": "code-tester", "prompt": "Run the test suite and report results", "condition": "prev_score >= 3", "name": "Test Suite"},
            {"agent": "jenkins-cicd", "prompt": "Deploy to staging environment", "condition": "all_passed", "name": "Deploy"},
        ],
    },
    {
        "name": "full-review",
        "description": "Comprehensive code review: style, security, tests, docs",
        "steps": [
            {"agent": "code-reviewer", "prompt": "Review code for style, patterns, and best practices", "name": "Style Review"},
            {"agent": "security", "prompt": "Security audit of recent changes", "name": "Security Scan"},
            {"agent": "code-tester", "prompt": "Check test coverage and suggest missing tests", "name": "Test Coverage"},
            {"agent": "code-writer", "prompt": "Suggest documentation updates for the changes", "condition": "all_passed", "name": "Doc Updates"},
        ],
    },
    {
        "name": "bug-fix",
        "description": "Investigate, fix, test, and review a bug",
        "steps": [
            {"agent": "code-reasoning", "prompt": "Analyze the bug and identify root cause", "name": "Root Cause"},
            {"agent": "code-writer", "prompt": "Implement the fix based on the analysis", "condition": "prev_passed", "name": "Fix"},
            {"agent": "code-tester", "prompt": "Write tests for the fix and run them", "condition": "prev_passed", "name": "Test Fix"},
            {"agent": "code-reviewer", "prompt": "Review the fix for correctness and side effects", "condition": "all_passed", "name": "Review Fix"},
        ],
    },
]


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def cmd_pipeline_exec(args: list[str] | None = None):
    """CLI handler for `code-agents pipeline`."""
    from code_agents.cli.cli_helpers import _colors, _load_env, _user_cwd, _server_url
    _load_env()

    args = args or []
    bold, green, yellow, red, cyan, dim = _colors()
    subcmd = args[0] if args else "list"
    cwd = _user_cwd()

    loader = PipelineLoader(cwd)

    if subcmd == "list":
        pipelines = loader.list_pipelines()
        if not pipelines:
            print(f"\n  No pipelines found. Create one:")
            print(f"    code-agents pipeline create <name>")
            print(f"\n  Built-in templates: {', '.join(t['name'] for t in BUILTIN_PIPELINES)}")
            print(f"  Install: code-agents pipeline create --template <name>\n")
            return

        print(f"\n  {bold('Available Pipelines:')}")
        for p in pipelines:
            steps = ", ".join(s.agent for s in p.steps)
            print(f"    {bold(p.name):<25} {p.description}")
            print(f"      {dim('Steps: ' + steps)}")
        print()

    elif subcmd == "create":
        name = args[1] if len(args) > 1 else ""
        template_name = ""
        for i, a in enumerate(args):
            if a == "--template" and i + 1 < len(args):
                template_name = args[i + 1]

        if template_name:
            tmpl = next((t for t in BUILTIN_PIPELINES if t["name"] == template_name), None)
            if not tmpl:
                print(f"\n  {red('Template not found:')} {template_name}")
                print(f"  Available: {', '.join(t['name'] for t in BUILTIN_PIPELINES)}\n")
                return
            config = PipelineConfig(
                name=name or tmpl["name"],
                description=tmpl["description"],
                steps=[PipelineStep(**s) for s in tmpl["steps"]],
            )
        else:
            if not name:
                print(f"  {red('Usage:')} code-agents pipeline create <name> [--template <template>]")
                return
            config = PipelineConfig(
                name=name,
                description="Custom pipeline",
                steps=[
                    PipelineStep(agent="code-reviewer", prompt="Review the code", name="Review"),
                    PipelineStep(agent="code-tester", prompt="Run tests", condition="prev_passed", name="Test"),
                ],
            )

        path = loader.create_pipeline(config)
        print(f"\n  {green('Created pipeline:')} {bold(config.name)}")
        print(f"    {dim(str(path))}")
        print(f"    Edit the YAML to customize steps.\n")

    elif subcmd == "run":
        name = args[1] if len(args) > 1 else ""
        if not name:
            print(f"  {red('Usage:')} code-agents pipeline run <name>")
            return

        pipeline = loader.get_pipeline(name)
        if not pipeline:
            print(f"\n  {red('Pipeline not found:')} {name}")
            print(f"  Run `code-agents pipeline list` to see available pipelines.\n")
            return

        url = _server_url()
        executor = PipelineExecutor(url)

        print(f"\n  Running pipeline: {bold(pipeline.name)}")
        print(f"  Steps: {len(pipeline.steps)}\n")

        def progress(step_num, total, result):
            sc = {"passed": green, "failed": red, "skipped": dim}.get(result.status, yellow)
            print(f"  [{step_num}/{total}] {result.step_name:<20} {result.agent:<15} {sc(result.status)}  ({result.latency_ms}ms)")

        run = asyncio.run(executor.run(pipeline, progress_callback=progress))
        print()
        PipelineExecutor.print_run(run)

    elif subcmd == "templates":
        print(f"\n  {bold('Built-in Pipeline Templates:')}")
        for t in BUILTIN_PIPELINES:
            steps = ", ".join(s.get("name", s["agent"]) for s in t["steps"])
            print(f"    {bold(t['name']):<25} {t['description']}")
            print(f"      {dim('Steps: ' + steps)}")
        print(f"\n  Install: code-agents pipeline create --template <name>\n")

    else:
        print(f"  {red('Unknown subcommand:')} {subcmd}")
        print(f"  Usage: code-agents pipeline [list|create|run|templates]")
