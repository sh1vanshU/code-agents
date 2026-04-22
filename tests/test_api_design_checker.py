"""Tests for the API design checker module."""

from __future__ import annotations

import os
import pytest

from code_agents.api.api_design_checker import (
    APIDesignChecker, APIDesignResult, APIFinding, check_api_design,
)


class TestAPIDesignChecker:
    """Test APIDesignChecker methods."""

    def test_init(self, tmp_path):
        checker = APIDesignChecker(cwd=str(tmp_path))
        assert checker.cwd == str(tmp_path)

    def test_check_empty_dir(self, tmp_path):
        checker = APIDesignChecker(cwd=str(tmp_path))
        result = checker.check()
        assert isinstance(result, APIDesignResult)
        assert result.endpoints_found == 0

    def test_check_finds_fastapi_endpoints(self, tmp_path):
        code = '''
from fastapi import APIRouter

router = APIRouter()

@router.get("/users")
async def list_users():
    return []

@router.post("/users")
async def create_user():
    return {"id": 1}
'''
        (tmp_path / "routes.py").write_text(code)
        checker = APIDesignChecker(cwd=str(tmp_path))
        result = checker.check()
        assert result.endpoints_found >= 2

    def test_check_response_consistency(self, tmp_path):
        code = '''
from fastapi import APIRouter

router = APIRouter()

@router.get("/items")
async def list_items():
    return []

@router.post("/items")
async def create_item():
    return {"id": 1}
'''
        (tmp_path / "items.py").write_text(code)
        checker = APIDesignChecker(cwd=str(tmp_path))
        result = checker.check(categories=["response"])
        response_findings = [f for f in result.findings if f.category == "response"]
        # Missing response_model
        assert len(response_findings) >= 1

    def test_check_versioning_inconsistency(self, tmp_path):
        code = '''
from fastapi import APIRouter
router = APIRouter()

@router.get("/v1/users")
async def users_v1():
    return []

@router.get("/items")
async def items_no_version():
    return []
'''
        (tmp_path / "mixed.py").write_text(code)
        checker = APIDesignChecker(cwd=str(tmp_path))
        result = checker.check(categories=["versioning"])
        version_findings = [f for f in result.findings if f.category == "versioning"]
        assert len(version_findings) >= 1

    def test_consistency_score(self, tmp_path):
        code = '''
from fastapi import APIRouter
router = APIRouter()

@router.get("/clean", response_model=dict)
async def clean_endpoint():
    try:
        return {"data": []}
    except Exception:
        raise
'''
        (tmp_path / "clean.py").write_text(code)
        checker = APIDesignChecker(cwd=str(tmp_path))
        result = checker.check()
        assert isinstance(result.consistency_score, float)

    def test_convenience_function(self, tmp_path):
        result = check_api_design(cwd=str(tmp_path))
        assert isinstance(result, dict)
        assert "endpoints_found" in result
        assert "consistency_score" in result
