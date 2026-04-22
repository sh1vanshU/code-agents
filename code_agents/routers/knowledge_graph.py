"""Knowledge Graph API — expose project structure index to agents."""

import logging
import os

from fastapi import APIRouter, Query

logger = logging.getLogger("code_agents.routers.knowledge_graph")

router = APIRouter(prefix="/knowledge-graph", tags=["knowledge-graph"])


def _get_kg():
    """Get or build the KnowledgeGraph singleton."""
    from code_agents.knowledge.knowledge_graph import KnowledgeGraph
    repo = os.getenv("TARGET_REPO_PATH", os.getcwd())
    kg = KnowledgeGraph(repo)
    if not kg.is_ready:
        kg.build()
    elif kg.is_stale():
        kg.update()
    return kg


@router.get("/query")
async def query_symbols(keywords: str = Query(..., description="Comma-separated keywords")):
    """Search the knowledge graph for symbols matching keywords."""
    kg = _get_kg()
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
    results = kg.query(kw_list, max_results=20)
    return {"keywords": kw_list, "results": results, "count": len(results)}


@router.get("/blast-radius")
async def blast_radius(file: str = Query(..., description="File path relative to repo root")):
    """Get all files affected by a change to the given file."""
    kg = _get_kg()
    affected = kg.blast_radius(file)
    return {"file": file, "affected": affected, "count": len(affected)}


@router.get("/stats")
async def graph_stats():
    """Return knowledge graph statistics."""
    kg = _get_kg()
    return kg.get_stats()


@router.get("/file/{file_path:path}")
async def file_symbols(file_path: str):
    """Get all symbols in a specific file."""
    kg = _get_kg()
    rel = kg._relative(os.path.join(kg.repo_path, file_path))
    symbol_ids = kg._file_index.get(rel, [])
    symbols = [kg._nodes[sid] for sid in symbol_ids if sid in kg._nodes]
    return {"file": rel, "symbols": symbols, "count": len(symbols)}
