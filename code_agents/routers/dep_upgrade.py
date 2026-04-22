"""Router for Dependency Upgrade Pilot."""

from __future__ import annotations

import logging
import os
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("code_agents.routers.dep_upgrade")

router = APIRouter(prefix="/dep-upgrade", tags=["dep-upgrade"])


class DepScanRequest(BaseModel):
    pass


class DepUpgradeRequest(BaseModel):
    package: str = Field("", description="Specific package to upgrade")
    all_packages: bool = Field(False, description="Upgrade all outdated")
    dry_run: bool = Field(True, description="Dry run mode")


class DepScanResponse(BaseModel):
    package_manager: str = ""
    candidates: list[dict] = []
    total_outdated: int = 0


class DepUpgradeResponse(BaseModel):
    package_manager: str = ""
    total_outdated: int = 0
    upgraded: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[dict] = []
    formatted: str = ""


@router.post("/scan", response_model=DepScanResponse)
async def scan_deps(req: DepScanRequest, request: Request):
    """Scan for outdated dependencies."""
    from code_agents.domain.dep_upgrade import DependencyUpgradePilot
    from dataclasses import asdict

    cwd = getattr(request.state, "repo_path", os.getcwd())
    pilot = DependencyUpgradePilot(cwd=cwd, dry_run=True)
    candidates = pilot.scan()
    return DepScanResponse(
        package_manager=pilot.package_manager,
        candidates=[asdict(c) for c in candidates],
        total_outdated=len(candidates),
    )


@router.post("/upgrade", response_model=DepUpgradeResponse)
async def upgrade_deps(req: DepUpgradeRequest, request: Request):
    """Upgrade outdated dependencies."""
    from code_agents.domain.dep_upgrade import DependencyUpgradePilot, format_upgrade_report
    from dataclasses import asdict

    cwd = getattr(request.state, "repo_path", os.getcwd())
    pilot = DependencyUpgradePilot(cwd=cwd, dry_run=req.dry_run)
    report = pilot.upgrade(package=req.package, all_packages=req.all_packages)
    return DepUpgradeResponse(
        package_manager=report.package_manager,
        total_outdated=report.total_outdated,
        upgraded=report.upgraded,
        failed=report.failed,
        skipped=report.skipped,
        results=[asdict(r) for r in report.results],
        formatted=format_upgrade_report(report),
    )
