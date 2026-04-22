"""Tests for pipeline — declarative agent chains with conditions."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from code_agents.devops.pipeline import (
    BUILTIN_PIPELINES,
    PipelineConfig,
    PipelineExecutor,
    PipelineLoader,
    PipelineRun,
    PipelineStep,
    StepResult,
    _evaluate_condition,
)


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------


class TestEvaluateCondition:
    """Tests for pipeline step condition evaluation."""

    def test_always(self):
        assert _evaluate_condition("always", []) is True
        assert _evaluate_condition("always", [StepResult(0, "s", "a", status="failed")]) is True

    def test_prev_passed_no_results(self):
        assert _evaluate_condition("prev_passed", []) is True

    def test_prev_passed_true(self):
        results = [StepResult(0, "s", "a", status="passed")]
        assert _evaluate_condition("prev_passed", results) is True

    def test_prev_passed_false(self):
        results = [StepResult(0, "s", "a", status="failed")]
        assert _evaluate_condition("prev_passed", results) is False

    def test_all_passed_empty(self):
        assert _evaluate_condition("all_passed", []) is True

    def test_all_passed_true(self):
        results = [
            StepResult(0, "s1", "a", status="passed"),
            StepResult(1, "s2", "a", status="skipped"),
        ]
        assert _evaluate_condition("all_passed", results) is True

    def test_all_passed_false(self):
        results = [
            StepResult(0, "s1", "a", status="passed"),
            StepResult(1, "s2", "a", status="failed"),
        ]
        assert _evaluate_condition("all_passed", results) is False

    def test_any_failed_true(self):
        results = [
            StepResult(0, "s1", "a", status="passed"),
            StepResult(1, "s2", "a", status="failed"),
        ]
        assert _evaluate_condition("any_failed", results) is True

    def test_any_failed_false(self):
        results = [StepResult(0, "s1", "a", status="passed")]
        assert _evaluate_condition("any_failed", results) is False

    def test_prev_score_gte(self):
        results = [StepResult(0, "s", "a", score=4)]
        assert _evaluate_condition("prev_score >= 3", results) is True
        assert _evaluate_condition("prev_score >= 5", results) is False

    def test_prev_score_gt(self):
        results = [StepResult(0, "s", "a", score=4)]
        assert _evaluate_condition("prev_score > 3", results) is True
        assert _evaluate_condition("prev_score > 4", results) is False

    def test_prev_score_lt(self):
        results = [StepResult(0, "s", "a", score=2)]
        assert _evaluate_condition("prev_score < 3", results) is True

    def test_prev_score_eq(self):
        results = [StepResult(0, "s", "a", score=5)]
        assert _evaluate_condition("prev_score == 5", results) is True
        assert _evaluate_condition("prev_score == 4", results) is False

    def test_prev_score_neq(self):
        results = [StepResult(0, "s", "a", score=3)]
        assert _evaluate_condition("prev_score != 5", results) is True
        assert _evaluate_condition("prev_score != 3", results) is False

    def test_prev_score_no_results(self):
        assert _evaluate_condition("prev_score >= 3", []) is True

    def test_unknown_condition(self):
        assert _evaluate_condition("unknown_thing", []) is True


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class TestPipelineStep:
    """Tests for PipelineStep dataclass."""

    def test_defaults(self):
        s = PipelineStep(agent="code-writer")
        assert s.condition == "always"
        assert s.timeout_s == 300
        assert s.on_failure == "stop"

    def test_custom(self):
        s = PipelineStep(agent="tester", condition="prev_passed", on_failure="skip", name="Test")
        assert s.name == "Test"
        assert s.on_failure == "skip"


class TestStepResult:
    """Tests for StepResult dataclass."""

    def test_defaults(self):
        r = StepResult(step_index=0, step_name="s", agent="a")
        assert r.status == "pending"
        assert r.score == 0
        assert r.error == ""


class TestPipelineConfig:
    """Tests for PipelineConfig dataclass."""

    def test_defaults(self):
        c = PipelineConfig(name="test")
        assert c.steps == []
        assert c.variables == {}

    def test_with_steps(self):
        c = PipelineConfig(
            name="test",
            steps=[PipelineStep(agent="a"), PipelineStep(agent="b")],
        )
        assert len(c.steps) == 2


class TestPipelineRun:
    """Tests for PipelineRun dataclass."""

    def test_defaults(self):
        r = PipelineRun()
        assert r.status == "pending"
        assert r.results == []
        assert r.context == {}


# ---------------------------------------------------------------------------
# Pipeline loader
# ---------------------------------------------------------------------------


class TestPipelineLoader:
    """Tests for PipelineLoader."""

    def test_list_empty(self, tmp_path):
        loader = PipelineLoader(str(tmp_path))
        pipelines = loader.list_pipelines()
        # May include builtins if they exist
        assert isinstance(pipelines, list)

    def test_parse_valid_yaml(self, tmp_path):
        pipelines_dir = tmp_path / ".code-agents" / "pipelines"
        pipelines_dir.mkdir(parents=True)

        config = {
            "name": "test-pipe",
            "description": "A test pipeline",
            "steps": [
                {"agent": "code-writer", "prompt": "Write code", "name": "Write"},
                {"agent": "code-tester", "prompt": "Test code", "condition": "prev_passed", "name": "Test"},
            ],
        }
        (pipelines_dir / "test-pipe.yaml").write_text(yaml.dump(config))

        loader = PipelineLoader(str(tmp_path))
        pipelines = loader.list_pipelines()
        found = [p for p in pipelines if p.name == "test-pipe"]
        assert len(found) == 1
        assert len(found[0].steps) == 2
        assert found[0].steps[0].agent == "code-writer"
        assert found[0].steps[1].condition == "prev_passed"

    def test_parse_invalid_yaml(self, tmp_path):
        pipelines_dir = tmp_path / ".code-agents" / "pipelines"
        pipelines_dir.mkdir(parents=True)
        (pipelines_dir / "bad.yaml").write_text("{{{{invalid yaml")

        loader = PipelineLoader(str(tmp_path))
        # Should not raise, just skip
        pipelines = loader.list_pipelines()
        assert not any(p.name == "bad" for p in pipelines)

    def test_get_pipeline(self, tmp_path):
        pipelines_dir = tmp_path / ".code-agents" / "pipelines"
        pipelines_dir.mkdir(parents=True)
        config = {"name": "findme", "steps": [{"agent": "a", "prompt": "p"}]}
        (pipelines_dir / "findme.yaml").write_text(yaml.dump(config))

        loader = PipelineLoader(str(tmp_path))
        p = loader.get_pipeline("findme")
        assert p is not None
        assert p.name == "findme"

    def test_get_missing_pipeline(self, tmp_path):
        loader = PipelineLoader(str(tmp_path))
        assert loader.get_pipeline("nope") is None

    def test_create_pipeline(self, tmp_path):
        loader = PipelineLoader(str(tmp_path))
        config = PipelineConfig(
            name="new-pipe",
            description="Fresh pipeline",
            steps=[PipelineStep(agent="writer", prompt="do stuff", name="Step 1")],
        )
        path = loader.create_pipeline(config)
        assert path.exists()

        data = yaml.safe_load(path.read_text())
        assert data["name"] == "new-pipe"
        assert len(data["steps"]) == 1


# ---------------------------------------------------------------------------
# Builtin pipelines
# ---------------------------------------------------------------------------


class TestBuiltinPipelines:
    """Tests for built-in pipeline templates."""

    def test_builtins_exist(self):
        assert len(BUILTIN_PIPELINES) > 0

    def test_builtin_structure(self):
        for t in BUILTIN_PIPELINES:
            assert "name" in t
            assert "description" in t
            assert "steps" in t
            assert len(t["steps"]) > 0

    def test_builtin_steps_have_agent(self):
        for t in BUILTIN_PIPELINES:
            for step in t["steps"]:
                assert "agent" in step
                assert step["agent"]

    def test_builtin_names_unique(self):
        names = [t["name"] for t in BUILTIN_PIPELINES]
        assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# Pipeline executor
# ---------------------------------------------------------------------------


class TestPipelineExecutor:
    """Tests for PipelineExecutor."""

    def test_init(self):
        executor = PipelineExecutor("http://localhost:8000")
        assert executor.url == "http://localhost:8000"

    @pytest.mark.asyncio
    async def test_run_step_skipped(self):
        """Step should be skipped when condition fails."""
        executor = PipelineExecutor()
        step = PipelineStep(agent="a", condition="prev_passed")
        prev = [StepResult(0, "s", "a", status="failed")]
        result = await executor._run_step(step, {}, prev)
        assert result.status == "skipped"

    @pytest.mark.asyncio
    async def test_run_step_condition_always(self):
        """Step with 'always' condition should attempt to run."""
        executor = PipelineExecutor("http://localhost:9999")
        step = PipelineStep(agent="a", prompt="test", condition="always", timeout_s=2)
        # Will fail because no server, but should attempt
        result = await executor._run_step(step, {}, [])
        assert result.status in ("failed", "running")

    @pytest.mark.asyncio
    async def test_run_pipeline_all_skipped(self):
        """Pipeline where all steps get skipped should complete."""
        executor = PipelineExecutor()
        pipeline = PipelineConfig(
            name="skip-all",
            steps=[
                PipelineStep(agent="a", condition="prev_passed"),
            ],
        )
        # First step has no prev, so it'll try to run (and fail without server)
        # But we can test the flow
        with patch.object(executor, "_run_step", return_value=StepResult(0, "s", "a", status="skipped")):
            run = await executor.run(pipeline)
            assert run.status == "completed"

    @pytest.mark.asyncio
    async def test_run_pipeline_stops_on_failure(self):
        """Pipeline should stop when a step fails with on_failure=stop."""
        executor = PipelineExecutor()
        pipeline = PipelineConfig(
            name="stop-test",
            steps=[
                PipelineStep(agent="a", on_failure="stop"),
                PipelineStep(agent="b"),
            ],
        )
        with patch.object(executor, "_run_step", return_value=StepResult(0, "s", "a", status="failed")):
            run = await executor.run(pipeline)
            assert run.status == "failed"
            assert len(run.results) == 1  # stopped after first

    @pytest.mark.asyncio
    async def test_run_pipeline_with_progress(self):
        """Progress callback should be called for each step."""
        executor = PipelineExecutor()
        pipeline = PipelineConfig(
            name="progress-test",
            steps=[PipelineStep(agent="a"), PipelineStep(agent="b")],
        )
        progress_calls = []

        with patch.object(executor, "_run_step", return_value=StepResult(0, "s", "a", status="passed", response="ok")):
            run = await executor.run(pipeline, progress_callback=lambda s, t, r: progress_calls.append(s))
            assert len(progress_calls) == 2

    @pytest.mark.asyncio
    async def test_run_accumulates_context(self):
        """Each step's response should be added to context for next steps."""
        executor = PipelineExecutor()
        pipeline = PipelineConfig(
            name="ctx-test",
            steps=[
                PipelineStep(agent="a", name="step1"),
                PipelineStep(agent="b", name="step2"),
            ],
        )
        call_count = [0]

        async def mock_step(step, context, prev):
            call_count[0] += 1
            if call_count[0] == 2:
                assert "step1" in context
            return StepResult(0, step.name or "s", step.agent, status="passed", response=f"resp-{call_count[0]}")

        with patch.object(executor, "_run_step", side_effect=mock_step):
            run = await executor.run(pipeline)
            assert run.status == "completed"
            assert "step1" in run.context


class TestPipelineExecutorPrint:
    """Tests for print_run."""

    def test_print_run_no_error(self, capsys):
        run = PipelineRun(
            run_id="pr1",
            pipeline_name="test",
            status="completed",
            results=[
                StepResult(0, "Review", "reviewer", status="passed", score=4, latency_ms=500),
                StepResult(1, "Test", "tester", status="passed", score=5, latency_ms=300),
            ],
        )
        PipelineExecutor.print_run(run)
        # Just verify no exception
