"""Debug router — autonomous debugging API endpoints."""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("code_agents.routers.debug")

router = APIRouter(prefix="/debug", tags=["debug"])


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------


class DebugRequest(BaseModel):
    bug_description: str = Field(..., description="Bug description, error message, or failing test")
    auto_fix: bool = Field(True, description="Automatically apply fixes")
    auto_commit: bool = Field(False, description="Auto-commit if fix verified")
    max_attempts: int = Field(3, description="Max fix attempts", ge=1, le=10)


class DebugTraceResponse(BaseModel):
    step: str
    description: str
    output: str = ""
    duration_ms: int = 0
    success: bool = False


class DebugFixResponse(BaseModel):
    file: str
    line: int
    original: str
    replacement: str
    explanation: str


class BlastRadiusResponse(BaseModel):
    files_affected: list[str] = []
    tests_affected: list[str] = []
    risk_level: str = "low"
    notes: str = ""


class DebugResponse(BaseModel):
    bug_description: str
    status: str
    error_type: str = ""
    error_message: str = ""
    error_file: str = ""
    error_line: int = 0
    root_cause: str = ""
    traces: list[DebugTraceResponse] = []
    fixes: list[DebugFixResponse] = []
    blast_radius: BlastRadiusResponse = BlastRadiusResponse()
    verified: bool = False
    attempts: int = 0
    total_duration_ms: int = 0


class ParseErrorRequest(BaseModel):
    error_output: str = Field(..., description="Raw error output to parse")


class ParseErrorResponse(BaseModel):
    error_type: str = ""
    error_message: str = ""
    error_file: str = ""
    error_line: int = 0
    language: str = "unknown"
    stack_frames: list[dict] = []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/run", response_model=DebugResponse)
async def run_debug(req: DebugRequest, request: Request):
    """Run the autonomous debug engine on a bug."""
    from code_agents.observability.debug_engine import DebugEngine

    cwd = getattr(request.state, "repo_path", os.getcwd())

    engine = DebugEngine(
        cwd=cwd,
        max_attempts=req.max_attempts,
        auto_fix=req.auto_fix,
        auto_commit=req.auto_commit,
    )

    result = await engine.run(req.bug_description)

    return DebugResponse(
        bug_description=result.bug_description,
        status=result.status,
        error_type=result.error_type,
        error_message=result.error_message,
        error_file=result.error_file,
        error_line=result.error_line,
        root_cause=result.root_cause,
        traces=[
            DebugTraceResponse(
                step=t.step, description=t.description,
                output=t.output[:2000], duration_ms=t.duration_ms,
                success=t.success,
            )
            for t in result.traces
        ],
        fixes=[
            DebugFixResponse(
                file=f.file, line=f.line,
                original=f.original, replacement=f.replacement,
                explanation=f.explanation,
            )
            for f in result.fixes
        ],
        blast_radius=BlastRadiusResponse(
            files_affected=result.blast_radius.files_affected,
            tests_affected=result.blast_radius.tests_affected,
            risk_level=result.blast_radius.risk_level,
            notes=result.blast_radius.notes,
        ),
        verified=result.verified,
        attempts=result.attempts,
        total_duration_ms=result.total_duration_ms,
    )


@router.post("/parse-error", response_model=ParseErrorResponse)
async def parse_error(req: ParseErrorRequest):
    """Parse raw error output into structured data."""
    from code_agents.observability.debug_engine import ErrorParser

    parsed = ErrorParser.parse(req.error_output)

    return ParseErrorResponse(
        error_type=parsed.get("error_type", ""),
        error_message=parsed.get("error_message", ""),
        error_file=parsed.get("error_file", ""),
        error_line=parsed.get("error_line", 0),
        language=parsed.get("language", "unknown"),
        stack_frames=parsed.get("stack_frames", []),
    )


@router.get("/status")
async def debug_status():
    """Check debug engine availability."""
    return {
        "available": True,
        "features": ["reproduce", "trace", "root_cause", "fix", "verify", "blast_radius"],
        "supported_languages": ["python", "javascript", "java", "go"],
    }
