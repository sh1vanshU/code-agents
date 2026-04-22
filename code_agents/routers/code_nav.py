"""API router for code navigation and understanding tools."""

from __future__ import annotations

import logging
import os
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("code_agents.routers.code_nav")

router = APIRouter(prefix="/code-nav", tags=["code-nav"])


# --- Request/Response Models ---

class ExplainRequest(BaseModel):
    target: str = Field(..., description="Target to explain: 'file.py:function' or 'file.py'")
    cwd: Optional[str] = Field(None, description="Working directory")


class UsageTraceRequest(BaseModel):
    symbol: str = Field(..., description="Symbol to trace")
    cwd: Optional[str] = Field(None, description="Working directory")
    include_tests: bool = Field(True, description="Include test files")


class NavSearchRequest(BaseModel):
    query: str = Field(..., description="Natural language query")
    cwd: Optional[str] = Field(None, description="Working directory")
    max_results: int = Field(30, description="Maximum results")


class GitStoryRequest(BaseModel):
    file: str = Field(..., description="File path")
    line: int = Field(..., description="Line number")
    cwd: Optional[str] = Field(None, description="Working directory")


class CallChainRequest(BaseModel):
    target: str = Field(..., description="Function name to analyze")
    cwd: Optional[str] = Field(None, description="Working directory")
    max_depth: int = Field(3, description="Maximum depth")


class CodeExamplesRequest(BaseModel):
    query: str = Field(..., description="What to search for")
    cwd: Optional[str] = Field(None, description="Working directory")
    max_examples: int = Field(20, description="Maximum examples")


class DepGraphRequest(BaseModel):
    module: str = Field(..., description="Module name")
    cwd: Optional[str] = Field(None, description="Working directory")
    format: str = Field("ascii", description="Output format: ascii, mermaid, dot")
    depth: int = Field(3, description="Max depth")


# --- Endpoints ---

def _resolve_cwd(cwd: Optional[str]) -> str:
    return cwd or os.environ.get("TARGET_REPO_PATH") or os.getcwd()


@router.post("/explain")
async def explain_code(req: ExplainRequest):
    """Explain a function, class, or module in plain English."""
    from code_agents.knowledge.explain_code import CodeExplainer, ExplainConfig

    config = ExplainConfig(cwd=_resolve_cwd(req.cwd))
    result = CodeExplainer(config).explain(req.target)
    return asdict(result)


@router.post("/usage-trace")
async def usage_trace(req: UsageTraceRequest):
    """Find all usages of a symbol across the codebase."""
    from code_agents.domain.usage_tracer import UsageTracer, UsageTraceConfig

    config = UsageTraceConfig(
        cwd=_resolve_cwd(req.cwd),
        include_tests=req.include_tests,
    )
    result = UsageTracer(config).trace(req.symbol)
    return {
        "symbol": result.symbol,
        "total_usages": result.total_usages,
        "files_affected": result.files_affected,
        "by_type": {k: [asdict(e) for e in v] for k, v in result.usages_by_type.items()},
    }


@router.post("/search")
async def nav_search(req: NavSearchRequest):
    """Semantic codebase search."""
    from code_agents.knowledge.codebase_nav import CodebaseNavigator, NavConfig

    config = NavConfig(cwd=_resolve_cwd(req.cwd), max_results=req.max_results)
    result = CodebaseNavigator(config).search(req.query)
    return {
        "query": result.query,
        "results": [asdict(r) for r in result.results],
        "concepts": result.concepts_matched,
        "files_scanned": result.total_files_scanned,
    }


@router.post("/git-story")
async def git_story(req: GitStoryRequest):
    """Reconstruct the full story behind a line of code."""
    from code_agents.git_ops.git_story import GitStoryTeller, GitStoryConfig

    config = GitStoryConfig(cwd=_resolve_cwd(req.cwd))
    result = GitStoryTeller(config).tell_story(req.file, req.line)
    return asdict(result)


@router.post("/call-chain")
async def call_chain(req: CallChainRequest):
    """Show full call tree (callers and callees) for a function."""
    from code_agents.observability.call_chain import CallChainAnalyzer, CallChainConfig

    config = CallChainConfig(cwd=_resolve_cwd(req.cwd), max_depth=req.max_depth)
    result = CallChainAnalyzer(config).analyze(req.target)
    return {
        "target": result.target,
        "target_file": result.target_file,
        "callers_count": result.callers_count,
        "callees_count": result.callees_count,
        "direct_callers": result.direct_callers,
        "direct_callees": result.direct_callees,
        "is_entry_point": result.is_entry_point,
        "is_leaf": result.is_leaf,
    }


@router.post("/examples")
async def code_examples(req: CodeExamplesRequest):
    """Find code examples for a concept or library usage."""
    from code_agents.knowledge.code_example import ExampleFinder, ExampleConfig

    config = ExampleConfig(cwd=_resolve_cwd(req.cwd), max_examples=req.max_examples)
    result = ExampleFinder(config).find(req.query)
    return {
        "query": result.query,
        "examples": [asdict(e) for e in result.examples],
        "patterns": result.patterns_found,
        "total_matches": result.total_matches,
    }


@router.post("/dep-graph")
async def dep_graph(req: DepGraphRequest):
    """Generate dependency graph with optional Mermaid/DOT output."""
    from code_agents.analysis.dependency_graph import DependencyGraph

    dg = DependencyGraph(_resolve_cwd(req.cwd))
    dg.build_graph()

    if req.format == "mermaid":
        output = dg.format_mermaid(req.module, depth=req.depth)
    elif req.format == "dot":
        output = dg.format_dot(req.module, depth=req.depth)
    else:
        output = dg.format_tree(req.module, depth=req.depth)

    deps = dg.get_dependencies(req.module)
    dependents = dg.get_dependents(req.module)

    return {
        "module": req.module,
        "format": req.format,
        "output": output,
        "dependencies": sorted(deps),
        "dependents": sorted(dependents),
        "circular": dg.find_circular_deps()[:10],
    }
