"""Benchmark router — agent quality benchmarking API endpoints."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger("code_agents.routers.benchmark")

router = APIRouter(prefix="/benchmark", tags=["benchmark"])


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------


class BenchmarkRunRequest(BaseModel):
    agents: list[str] = Field(["code-writer"], description="Agents to benchmark")
    models: list[str] = Field([], description="Models to test (empty = agent default)")
    judge: bool = Field(True, description="Use LLM judge for quality scoring")
    custom_tasks_path: str = Field("", description="Path to custom tasks YAML")


class BenchmarkResultResponse(BaseModel):
    task_id: str
    task_name: str
    category: str
    agent: str
    model: str
    quality_score: int = 0
    latency_ms: int = 0
    error: str = ""


class BenchmarkRunResponse(BaseModel):
    run_id: str
    status: str
    results: list[BenchmarkResultResponse] = []
    summary: dict = {}
    report_path: str = ""


class CompareRequest(BaseModel):
    baseline_id: str = Field("", description="Baseline run ID (empty = auto-detect)")
    current_id: str = Field("", description="Current run ID (empty = auto-detect)")


class RegressionAlertResponse(BaseModel):
    metric: str
    agent: str
    severity: str
    message: str
    baseline_value: float
    current_value: float
    delta_pct: float


class CompareResponse(BaseModel):
    baseline_id: str
    current_id: str
    passed: bool
    alerts: list[RegressionAlertResponse] = []
    overall: dict = {}
    per_agent: dict = {}


class TrendResponse(BaseModel):
    runs: list[dict] = []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/run", response_model=BenchmarkRunResponse)
async def run_benchmark(req: BenchmarkRunRequest):
    """Run agent benchmarks."""
    import os
    from code_agents.testing.benchmark import BenchmarkRunner
    from code_agents.testing.benchmark_regression import load_custom_tasks

    url = f"http://127.0.0.1:{os.getenv('PORT', '8000')}"

    # Load custom tasks if specified
    tasks = None
    if req.custom_tasks_path:
        custom = load_custom_tasks(req.custom_tasks_path)
        if custom:
            tasks = custom

    runner = BenchmarkRunner(
        agents=req.agents,
        models=req.models,
        tasks=tasks,
        url=url,
        judge=req.judge,
    )

    report = await runner.run()
    path = runner.save_report(report)

    return BenchmarkRunResponse(
        run_id=report.run_id,
        status="completed",
        results=[
            BenchmarkResultResponse(
                task_id=r.task_id, task_name=r.task_name,
                category=r.category, agent=r.agent,
                model=r.model, quality_score=r.quality_score,
                latency_ms=r.latency_ms, error=r.error,
            )
            for r in report.results
        ],
        summary=report.summary,
        report_path=str(path),
    )


@router.post("/compare", response_model=CompareResponse)
async def compare_benchmarks(req: CompareRequest):
    """Compare two benchmark runs for regressions."""
    from code_agents.testing.benchmark_regression import RegressionDetector

    detector = RegressionDetector()
    result = detector.compare(req.baseline_id, req.current_id)

    return CompareResponse(
        baseline_id=result.baseline_id,
        current_id=result.current_id,
        passed=result.passed,
        alerts=[
            RegressionAlertResponse(
                metric=a.metric, agent=a.agent,
                severity=a.severity, message=a.message,
                baseline_value=a.baseline_value,
                current_value=a.current_value,
                delta_pct=a.delta_pct,
            )
            for a in result.alerts
        ],
        overall=result.overall,
        per_agent=result.per_agent,
    )


@router.get("/trend", response_model=TrendResponse)
async def benchmark_trend(n: int = 10):
    """Get quality trend over last N runs."""
    from code_agents.testing.benchmark_regression import RegressionDetector

    detector = RegressionDetector()
    return TrendResponse(runs=detector.trend(n))


@router.get("/reports")
async def list_reports():
    """List all saved benchmark reports."""
    from code_agents.testing.benchmark import BenchmarkRunner
    return {"reports": BenchmarkRunner.list_reports()}


@router.get("/status")
async def benchmark_status():
    """Check benchmark engine availability."""
    from code_agents.testing.benchmark import BENCHMARKS_DIR
    return {
        "available": True,
        "reports_dir": str(BENCHMARKS_DIR),
        "features": [
            "run", "compare", "trend", "regression_detection",
            "custom_tasks", "csv_export", "quality_thresholds",
        ],
    }
