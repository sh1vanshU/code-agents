"""Router for Test Impact Analyzer."""

from __future__ import annotations

import logging
import os
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("code_agents.routers.test_impact")

router = APIRouter(prefix="/test-impact", tags=["test-impact"])


class TestImpactRequest(BaseModel):
    base: str = Field("main", description="Base branch to diff against")
    run: bool = Field(False, description="Run impacted tests after analysis")


class TestImpactResponse(BaseModel):
    changed_files: list[str] = []
    changed_functions: list[str] = []
    impacted_tests: list[dict] = []
    total_test_files: int = 0
    impacted_test_files: int = 0
    reduction_pct: float = 0.0
    test_framework: str = ""
    run_result: dict = {}
    formatted: str = ""


@router.post("/analyze", response_model=TestImpactResponse)
async def analyze_test_impact(req: TestImpactRequest, request: Request):
    """Analyze which tests are impacted by code changes."""
    from code_agents.testing.test_impact import ImpactAnalyzer, format_test_impact
    from dataclasses import asdict

    cwd = getattr(request.state, "repo_path", os.getcwd())
    analyzer = ImpactAnalyzer(cwd=cwd, base=req.base)

    if req.run:
        report = analyzer.analyze_and_run()
    else:
        report = analyzer.analyze()

    return TestImpactResponse(
        changed_files=report.changed_files,
        changed_functions=report.changed_functions,
        impacted_tests=[asdict(t) for t in report.impacted_tests],
        total_test_files=report.total_test_files,
        impacted_test_files=report.impacted_test_files,
        reduction_pct=report.reduction_pct,
        test_framework=report.test_framework,
        run_result=report.run_result or {},
        formatted=format_test_impact(report),
    )
