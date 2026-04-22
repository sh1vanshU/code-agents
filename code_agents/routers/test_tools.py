"""API router for testing tools."""

from __future__ import annotations

import logging
import os
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger("code_agents.routers.test_tools")
router = APIRouter(prefix="/test-tools", tags=["test-tools"])


class EdgeCaseRequest(BaseModel):
    target: str = Field(..., description="Target function: file.py:function_name")
    cwd: Optional[str] = None

class MockBuildRequest(BaseModel):
    target: str = Field(..., description="Target class: file.py:ClassName")
    cwd: Optional[str] = None

class TestFixRequest(BaseModel):
    error_output: str = Field(..., description="pytest error output")
    cwd: Optional[str] = None

class IntegrationScaffoldRequest(BaseModel):
    services: list[str] = Field(..., description="Services to scaffold: postgres, redis, kafka, etc.")


def _cwd(cwd: Optional[str]) -> str:
    return cwd or os.environ.get("TARGET_REPO_PATH") or os.getcwd()


@router.post("/edge-cases")
async def edge_cases(req: EdgeCaseRequest):
    from code_agents.testing.edge_case_suggester import EdgeCaseSuggester, EdgeCaseConfig
    result = EdgeCaseSuggester(EdgeCaseConfig(cwd=_cwd(req.cwd))).suggest(req.target)
    return {
        "target": result.target,
        "function": result.function_name,
        "args": result.args,
        "summary": result.summary,
        "edge_cases": [asdict(e) for e in result.edge_cases],
        "existing_checks": result.existing_checks,
    }


@router.post("/mock-build")
async def mock_build(req: MockBuildRequest):
    from code_agents.testing.mock_builder import MockBuilder, MockBuilderConfig
    result = MockBuilder(MockBuilderConfig(cwd=_cwd(req.cwd))).build(req.target)
    return {
        "target": result.target,
        "summary": result.summary,
        "mocks": [asdict(m) for m in result.mocks],
    }


@router.post("/test-fix")
async def test_fix(req: TestFixRequest):
    from code_agents.testing.test_fixer import TestFixer, TestFixerConfig
    result = TestFixer(TestFixerConfig(cwd=_cwd(req.cwd))).diagnose(req.error_output)
    return {
        "summary": result.summary,
        "diagnosis": result.diagnosis,
        "failures": [asdict(f) for f in result.failures],
        "suggestions": [asdict(s) for s in result.suggestions],
    }


@router.post("/integration-scaffold")
async def integration_scaffold(req: IntegrationScaffoldRequest):
    from code_agents.knowledge.integration_scaffold import IntegrationScaffolder
    result = IntegrationScaffolder().generate(req.services)
    return {
        "summary": result.summary,
        "docker_compose": result.docker_compose,
        "conftest_code": result.conftest_code,
        "example_test": result.example_test,
        "env_vars": result.env_vars,
    }
