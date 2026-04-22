"""
Testing API: run test suites, get coverage reports, and identify coverage gaps.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..cicd.testing_client import TestingClient, TestingError

logger = logging.getLogger("code_agents.testing")
router = APIRouter(prefix="/testing", tags=["testing"])


def _resolve_repo_path(repo_path: Optional[str] = None) -> str:
    """Resolve repo path: request param → env var → cwd."""
    path = repo_path or os.getenv("TARGET_REPO_PATH") or os.getcwd()
    if not os.path.isdir(path):
        raise HTTPException(status_code=422, detail=f"Repository path does not exist: {path}")
    return path


def _get_client(repo_path: Optional[str] = None) -> TestingClient:
    """Build TestingClient from request param, env var, or cwd."""
    test_command = os.getenv("TARGET_TEST_COMMAND")
    threshold = float(os.getenv("TARGET_COVERAGE_THRESHOLD", "100"))
    return TestingClient(
        repo_path=_resolve_repo_path(repo_path),
        test_command=test_command,
        coverage_threshold=threshold,
    )


class RunTestsRequest(BaseModel):
    """Request to run the test suite."""
    branch: Optional[str] = Field(None, description="Branch to checkout before running tests")
    test_command: Optional[str] = Field(None, description="Override test command (auto-detected if not set)")
    coverage_threshold: Optional[float] = Field(None, description="Override coverage threshold")
    repo_path: Optional[str] = Field(None, description="Override target repo path")


@router.post("/run")
async def run_tests(req: RunTestsRequest):
    """
    Run the test suite on the target repository.

    Auto-detects the test framework (pytest, jest, maven, gradle, go) if no command is specified.
    Returns test results including pass/fail counts and output.
    """
    try:
        client = _get_client(req.repo_path)
        if req.coverage_threshold is not None:
            client.coverage_threshold = req.coverage_threshold
        result = await client.run_tests(branch=req.branch, test_command=req.test_command)
        logger.info(
            "run_tests: passed=%s total=%d pass=%d fail=%d",
            result["passed"], result["total"], result["passed_count"], result["failed_count"],
        )
        return result
    except TestingError as e:
        logger.error("run_tests failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/coverage")
async def get_coverage(repo_path: Optional[str] = None):
    """
    Get the latest coverage report from coverage.xml.

    Run tests with coverage first (e.g., pytest --cov --cov-report=xml).
    Returns per-file coverage percentages and uncovered line numbers.
    """
    try:
        client = _get_client(repo_path)
        result = await client.get_coverage()
        logger.info("coverage: %.1f%% (threshold: %.1f%%)",
                     result["total_coverage"], result["coverage_threshold"])
        return result
    except TestingError as e:
        logger.error("get_coverage failed: %s", e)
        raise HTTPException(status_code=422, detail=str(e))


class GenTestsRequest(BaseModel):
    """Request to generate tests for source files."""
    target_path: Optional[str] = Field("", description="Relative path to file or directory (empty = entire repo)")
    max_files: int = Field(10, description="Maximum files to generate tests for")
    verify: bool = Field(False, description="Run generated tests and auto-fix failures")
    dry_run: bool = Field(False, description="Analyze only, don't generate")
    repo_path: Optional[str] = Field(None, description="Override target repo path")


@router.post("/gen-tests")
async def gen_tests(req: GenTestsRequest):
    """
    AI-powered test generation — fully automated.

    Scans source files with AST parsers, auto-delegates to code-tester agent,
    writes test files to disk, and optionally runs them with auto-fix loop.
    """
    from code_agents.tools.test_generator import TestGenerator, format_gen_tests_report

    repo = _resolve_repo_path(req.repo_path)
    try:
        gen = TestGenerator(
            repo_path=repo,
            target_path=req.target_path or "",
            max_files=req.max_files,
            verify=req.verify,
            dry_run=req.dry_run,
        )
        report = await gen.run()
        logger.info(
            "gen_tests: analyzed=%d gaps=%d generated=%d tests=%d",
            report.files_analyzed, report.files_with_gaps,
            report.files_generated, report.total_tests_written,
        )
        return {
            "files_analyzed": report.files_analyzed,
            "files_with_gaps": report.files_with_gaps,
            "files_generated": report.files_generated,
            "total_tests_written": report.total_tests_written,
            "total_tests_passed": report.total_tests_passed,
            "total_tests_failed": report.total_tests_failed,
            "results": [
                {
                    "source_file": r.source_file,
                    "test_file": r.test_file,
                    "tests_written": r.tests_written,
                    "tests_passed": r.tests_passed,
                    "tests_failed": r.tests_failed,
                    "error": r.error,
                    "retries": r.retries,
                }
                for r in report.results
            ],
            "errors": report.errors,
        }
    except Exception as e:
        logger.error("gen_tests failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/gaps")
async def get_coverage_gaps(base: str = "main", head: str = "HEAD", repo_path: Optional[str] = None):
    """
    Identify coverage gaps in new/changed code between two branches.

    Cross-references git diff with coverage data to find new lines that lack tests.
    """
    try:
        client = _get_client(repo_path)
        result = await client.get_coverage_gaps(base=base, head=head)
        logger.info(
            "coverage_gaps %s...%s: %d/%d lines covered (%.1f%%)",
            base, head,
            result.get("new_lines_covered", 0),
            result.get("new_lines_total", 0),
            result.get("coverage_pct", 0),
        )
        return result
    except TestingError as e:
        logger.error("get_coverage_gaps failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))
