"""API router for debugging and troubleshooting tools."""

from __future__ import annotations

import logging
import os
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger("code_agents.routers.debug_tools")
router = APIRouter(prefix="/debug-tools", tags=["debug-tools"])


class StackDecodeRequest(BaseModel):
    trace: str = Field(..., description="Stack trace text")
    cwd: Optional[str] = None

class LogAnalyzeRequest(BaseModel):
    logs: str = Field(..., description="Log text to analyze")

class EnvDiffRequest(BaseModel):
    left: dict = Field(..., description="Left environment variables")
    right: dict = Field(..., description="Right environment variables")
    left_name: str = "env1"
    right_name: str = "env2"

class ScanRequest(BaseModel):
    cwd: Optional[str] = None


def _cwd(cwd: Optional[str]) -> str:
    return cwd or os.environ.get("TARGET_REPO_PATH") or os.getcwd()


@router.post("/stack-decode")
async def stack_decode(req: StackDecodeRequest):
    from code_agents.observability.stack_decoder import StackDecoder, StackDecodeConfig
    result = StackDecoder(StackDecodeConfig(cwd=_cwd(req.cwd))).decode(req.trace)
    return asdict(result)


@router.post("/log-analyze")
async def log_analyze(req: LogAnalyzeRequest):
    from code_agents.observability.log_analyzer import LogAnalyzer
    result = LogAnalyzer().analyze(req.logs)
    return {
        "summary": result.summary,
        "total_lines": result.total_lines,
        "error_count": result.error_count,
        "services": result.services_seen,
        "level_distribution": result.level_distribution,
        "root_cause": asdict(result.root_cause) if result.root_cause else None,
        "errors": [asdict(e) for e in result.errors[:20]],
    }


@router.post("/env-diff")
async def env_diff(req: EnvDiffRequest):
    from code_agents.devops.env_differ import EnvDiffer
    result = EnvDiffer().diff_dicts(req.left, req.right, req.left_name, req.right_name)
    return {
        "summary": result.summary,
        "different": result.different,
        "missing_left": result.missing_left,
        "missing_right": result.missing_right,
        "warnings": result.warnings,
        "entries": [asdict(e) for e in result.entries if e.diff_type != "same"],
    }


@router.post("/leak-scan")
async def leak_scan(req: ScanRequest):
    from code_agents.observability.leak_finder import LeakFinder, LeakFinderConfig
    result = LeakFinder(LeakFinderConfig(cwd=_cwd(req.cwd))).scan()
    return {
        "summary": result.summary,
        "files_scanned": result.files_scanned,
        "high": result.high_count,
        "medium": result.medium_count,
        "low": result.low_count,
        "findings": [asdict(f) for f in result.findings[:50]],
    }


@router.post("/deadlock-scan")
async def deadlock_scan(req: ScanRequest):
    from code_agents.observability.deadlock_detector import DeadlockDetector, DeadlockDetectorConfig
    result = DeadlockDetector(DeadlockDetectorConfig(cwd=_cwd(req.cwd))).scan()
    return {
        "summary": result.summary,
        "files_scanned": result.files_scanned,
        "thread_usage": result.thread_usage,
        "async_usage": result.async_usage,
        "findings": [asdict(f) for f in result.findings[:50]],
    }
