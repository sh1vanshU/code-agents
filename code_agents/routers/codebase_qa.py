"""Router for Codebase Q&A."""

from __future__ import annotations

import logging
import os
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("code_agents.routers.codebase_qa")

router = APIRouter(prefix="/explain", tags=["explain"])


class QARequest(BaseModel):
    question: str = Field(..., description="Question about the codebase")


class QAResponse(BaseModel):
    question: str = ""
    answer: str = ""
    confidence: float = 0.0
    sources: list[dict] = []
    relevant_files: list[str] = []
    formatted: str = ""


@router.post("/ask", response_model=QAResponse)
async def ask_question(req: QARequest, request: Request):
    """Ask a question about the codebase."""
    from code_agents.knowledge.codebase_qa import CodebaseQA, format_qa_answer
    from dataclasses import asdict

    cwd = getattr(request.state, "repo_path", os.getcwd())
    qa = CodebaseQA(cwd=cwd)
    answer = qa.ask(req.question)
    return QAResponse(
        question=answer.question,
        answer=answer.answer,
        confidence=answer.confidence,
        sources=[asdict(s) for s in answer.sources],
        relevant_files=answer.context.relevant_files,
        formatted=format_qa_answer(answer),
    )
