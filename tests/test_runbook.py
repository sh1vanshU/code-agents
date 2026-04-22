"""Tests for Runbook Executor."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.knowledge.runbook import (
    RunbookExecutor,
    RunbookExecution,
    RunbookSpec,
    RunbookStep,
    StepResult,
    format_execution,
    format_runbook_list,
)


class TestRunbookExecutor:
    """Tests for RunbookExecutor."""

    def test_init_defaults(self):
        executor = RunbookExecutor()
        assert executor.dry_run is False

    def test_init_dry_run(self):
        executor = RunbookExecutor(dry_run=True)
        assert executor.dry_run is True

    def test_parse_markdown_simple(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = os.path.join(tmpdir, "deploy-api.md")
            Path(md_path).write_text(
                "# Deploy API\n\n"
                "Deploy the API service.\n\n"
                "## Step 1: Check status\n\n"
                "Verify the service is running.\n\n"
                "```bash\nkubectl get pods\n```\n\n"
                "## Step 2: Deploy\n\n"
                "Run the deploy command.\n\n"
                "```bash\nkubectl apply -f deploy.yaml\n```\n"
            )
            executor = RunbookExecutor(cwd=tmpdir)
            spec = executor._parse_markdown(md_path)
            assert spec.name == "Deploy API"
            assert len(spec.steps) == 2
            assert "kubectl get pods" in spec.steps[0].command
            assert "kubectl apply" in spec.steps[1].command

    def test_parse_markdown_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = os.path.join(tmpdir, "runbook.md")
            Path(md_path).write_text(
                "---\n"
                'name: "API Rollback"\n'
                'description: "Rollback API to previous version"\n'
                "tags: api, rollback\n"
                "---\n\n"
                "## Check current version\n\n"
                "```\nkubectl get deployment api -o jsonpath='{.spec.template.spec.containers[0].image}'\n```\n"
            )
            executor = RunbookExecutor(cwd=tmpdir)
            spec = executor._parse_markdown(md_path)
            assert spec.name == "API Rollback"
            assert spec.description == "Rollback API to previous version"
            assert len(spec.steps) == 1

    def test_parse_markdown_dangerous_detection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = os.path.join(tmpdir, "cleanup.md")
            Path(md_path).write_text(
                "# Cleanup\n\n"
                "## Remove temp files\n\n"
                "```bash\nrm -rf /tmp/old_data\n```\n"
            )
            executor = RunbookExecutor(cwd=tmpdir)
            spec = executor._parse_markdown(md_path)
            assert spec.steps[0].is_dangerous is True

    def test_execute_step_dry_run(self):
        executor = RunbookExecutor(dry_run=True)
        step = RunbookStep(index=0, title="Test", command="echo hello")
        result = executor._execute_step(step)
        assert result.status == "skipped"
        assert "DRY RUN" in result.output

    def test_execute_step_dangerous_skipped(self):
        executor = RunbookExecutor(dry_run=False)
        step = RunbookStep(index=0, title="Danger", command="rm -rf /tmp/test", is_dangerous=True)
        result = executor._execute_step(step)
        assert result.status == "skipped"
        assert "DANGEROUS" in result.output

    def test_execute_step_manual(self):
        executor = RunbookExecutor()
        step = RunbookStep(index=0, title="Verify", is_manual=True, description="Check logs")
        result = executor._execute_step(step)
        assert result.status == "manual"

    def test_execute_step_no_command(self):
        executor = RunbookExecutor()
        step = RunbookStep(index=0, title="Info", description="Just info")
        result = executor._execute_step(step)
        assert result.status == "skipped"

    def test_execute_step_success(self):
        executor = RunbookExecutor(dry_run=False)
        step = RunbookStep(index=0, title="Echo", command="echo hello")
        result = executor._execute_step(step)
        assert result.status == "success"
        assert "hello" in result.output

    def test_execute_step_failure(self):
        executor = RunbookExecutor(dry_run=False)
        step = RunbookStep(index=0, title="Fail", command="exit 1")
        result = executor._execute_step(step)
        assert result.status == "failed"

    def test_execute_full_runbook_dry_run(self):
        executor = RunbookExecutor(dry_run=True)
        spec = RunbookSpec(
            name="Test",
            steps=[
                RunbookStep(index=0, title="Step 1", command="echo step1"),
                RunbookStep(index=1, title="Step 2", command="echo step2"),
            ],
        )
        execution = executor.execute(spec)
        assert execution.status == "completed"
        assert all(r.status == "skipped" for r in execution.results)

    def test_execute_stops_on_failure(self):
        executor = RunbookExecutor(dry_run=False)
        spec = RunbookSpec(
            name="Test",
            steps=[
                RunbookStep(index=0, title="Fail", command="exit 1", on_failure="stop"),
                RunbookStep(index=1, title="Never", command="echo never"),
            ],
        )
        execution = executor.execute(spec)
        assert execution.status == "failed"
        assert len(execution.results) == 1

    def test_list_runbooks_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = RunbookExecutor(cwd=tmpdir)
            assert executor.list_runbooks() == []

    def test_list_runbooks_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rb_dir = os.path.join(tmpdir, "runbooks")
            os.makedirs(rb_dir)
            Path(os.path.join(rb_dir, "deploy.md")).write_text("# Deploy\n## Step 1\n```\necho deploy\n```")
            executor = RunbookExecutor(cwd=tmpdir)
            runbooks = executor.list_runbooks()
            assert len(runbooks) == 1

    def test_load_by_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rb_dir = os.path.join(tmpdir, "runbooks")
            os.makedirs(rb_dir)
            Path(os.path.join(rb_dir, "deploy.md")).write_text("# Deploy\n## Check\n```\necho ok\n```")
            executor = RunbookExecutor(cwd=tmpdir)
            spec = executor.load("Deploy")
            assert spec is not None
            assert spec.name == "Deploy"

    def test_load_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = RunbookExecutor(cwd=tmpdir)
            assert executor.load("nonexistent") is None


class TestRunbookExecution:
    """Tests for RunbookExecution."""

    def test_properties(self):
        spec = RunbookSpec(name="Test", steps=[])
        execution = RunbookExecution(
            spec=spec,
            results=[
                StepResult(step=RunbookStep(index=0, title="A"), status="success"),
                StepResult(step=RunbookStep(index=1, title="B"), status="failed"),
                StepResult(step=RunbookStep(index=2, title="C"), status="success"),
            ],
        )
        assert execution.steps_completed == 2
        assert execution.steps_failed == 1


class TestFormatRunbook:
    """Tests for format functions."""

    def test_format_runbook_list(self):
        runbooks = [
            RunbookSpec(name="Deploy", description="Deploy API", steps=[RunbookStep(index=0, title="S")]),
        ]
        output = format_runbook_list(runbooks)
        assert "Deploy" in output
        assert "1 steps" in output

    def test_format_runbook_list_empty(self):
        output = format_runbook_list([])
        assert "No runbooks found" in output

    def test_format_execution(self):
        spec = RunbookSpec(name="Test", steps=[RunbookStep(index=0, title="Echo")])
        execution = RunbookExecution(
            spec=spec,
            results=[StepResult(step=spec.steps[0], status="success", output="hello")],
            status="completed",
        )
        output = format_execution(execution)
        assert "Test" in output
        assert "completed" in output
