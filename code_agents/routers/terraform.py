"""
Terraform: plan, apply, and manage infrastructure via terraform CLI.

Requires terraform binary in PATH.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..cicd.terraform_client import TerraformClient, TerraformError

logger = logging.getLogger("code_agents.routers.terraform")
router = APIRouter(prefix="/terraform", tags=["terraform"])


def _get_client(working_dir: str = "") -> TerraformClient:
    """Build TerraformClient."""
    wd = working_dir or os.getenv("TERRAFORM_WORKING_DIR", ".")
    binary = os.getenv("TERRAFORM_BINARY", "")
    return TerraformClient(working_dir=wd, binary=binary)


# ── Models ────────────────────────────────────────────────────────────────

class InitRequest(BaseModel):
    working_dir: str = Field(default=".", description="Terraform working directory")
    backend_config: dict[str, str] = Field(default_factory=dict, description="Backend config overrides")


class ValidateRequest(BaseModel):
    working_dir: str = Field(default=".", description="Terraform working directory")


class PlanRequest(BaseModel):
    working_dir: str = Field(default=".", description="Terraform working directory")
    targets: list[str] = Field(default_factory=list, description="Target specific resources")
    var_file: str = Field(default="", description="Path to var file")
    refresh_only: bool = Field(default=False, description="Refresh-only plan (drift detection)")


class ApplyRequest(BaseModel):
    working_dir: str = Field(default=".", description="Terraform working directory")
    auto_approve: bool = Field(default=False, description="Skip interactive approval")
    targets: list[str] = Field(default_factory=list, description="Target specific resources")
    var_file: str = Field(default="", description="Path to var file")


class DestroyRequest(BaseModel):
    working_dir: str = Field(default=".", description="Terraform working directory")
    targets: list[str] = Field(default_factory=list, description="Target specific resources")
    auto_approve: bool = Field(default=False, description="Skip interactive approval")


class FmtRequest(BaseModel):
    working_dir: str = Field(default=".", description="Terraform working directory")
    check: bool = Field(default=True, description="Check only — don't modify files")


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.post("/init")
async def terraform_init(req: InitRequest):
    """Initialize terraform in a working directory."""
    client = _get_client(req.working_dir)
    try:
        return await client.init(backend_config=req.backend_config or None)
    except TerraformError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/validate")
async def terraform_validate(req: ValidateRequest):
    """Validate terraform configuration."""
    client = _get_client(req.working_dir)
    try:
        return await client.validate()
    except TerraformError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/plan")
async def terraform_plan(req: PlanRequest):
    """Run terraform plan."""
    logger.info("Terraform plan: dir=%s, targets=%s, refresh_only=%s", req.working_dir, req.targets, req.refresh_only)
    client = _get_client(req.working_dir)
    try:
        return await client.plan(
            targets=req.targets or None,
            var_file=req.var_file,
            refresh_only=req.refresh_only,
        )
    except TerraformError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/apply")
async def terraform_apply(req: ApplyRequest):
    """Apply terraform changes. Requires auto_approve=true or prior plan."""
    logger.info("Terraform apply: dir=%s, auto_approve=%s", req.working_dir, req.auto_approve)
    client = _get_client(req.working_dir)
    try:
        return await client.apply(
            auto_approve=req.auto_approve,
            targets=req.targets or None,
            var_file=req.var_file,
        )
    except TerraformError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/destroy")
async def terraform_destroy(req: DestroyRequest):
    """Destroy terraform resources. DANGEROUS — use with caution."""
    logger.warning("Terraform destroy: dir=%s, targets=%s", req.working_dir, req.targets)
    client = _get_client(req.working_dir)
    try:
        return await client.destroy(targets=req.targets or None, auto_approve=req.auto_approve)
    except TerraformError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/state")
async def terraform_state_list(working_dir: str = Query(default=".", description="Terraform working directory")):
    """List resources in terraform state."""
    client = _get_client(working_dir)
    try:
        resources = await client.state_list()
        return {"total": len(resources), "resources": resources}
    except TerraformError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/state/{resource_address:path}")
async def terraform_state_show(resource_address: str, working_dir: str = Query(default=".")):
    """Show a specific resource in terraform state."""
    client = _get_client(working_dir)
    try:
        return await client.state_show(resource_address)
    except TerraformError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/output")
async def terraform_output(working_dir: str = Query(default=".", description="Terraform working directory")):
    """Get terraform outputs."""
    client = _get_client(working_dir)
    try:
        return await client.output()
    except TerraformError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/providers")
async def terraform_providers(working_dir: str = Query(default=".", description="Terraform working directory")):
    """List terraform providers."""
    client = _get_client(working_dir)
    try:
        return await client.providers()
    except TerraformError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/fmt")
async def terraform_fmt(req: FmtRequest):
    """Format terraform files (check mode by default)."""
    client = _get_client(req.working_dir)
    try:
        return await client.fmt(check=req.check)
    except TerraformError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
