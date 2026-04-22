"""API router for API development tools."""

from __future__ import annotations

import logging
import os
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger("code_agents.routers.api_tools")
router = APIRouter(prefix="/api-tools", tags=["api-tools"])


class EndpointGenRequest(BaseModel):
    resource_name: str = Field(..., description="Resource name (e.g. User, Order)")
    framework: str = Field("fastapi", description="Target framework: fastapi, express, flask, django")
    fields: Optional[list[str]] = Field(None, description="Field definitions (e.g. ['name:str', 'email:str'])")
    cwd: Optional[str] = None


class ApiSyncRequest(BaseModel):
    spec_file: str = Field(..., description="Path to OpenAPI/Swagger spec file")
    cwd: Optional[str] = None


class ResponseOptimizeRequest(BaseModel):
    cwd: Optional[str] = None


class RestToGrpcRequest(BaseModel):
    cwd: Optional[str] = None


class ApiChangelogRequest(BaseModel):
    old_spec: str = Field(..., description="Path to old API spec")
    new_spec: str = Field(..., description="Path to new API spec")
    cwd: Optional[str] = None


def _cwd(cwd: Optional[str]) -> str:
    return cwd or os.environ.get("TARGET_REPO_PATH") or os.getcwd()


@router.post("/endpoint-gen")
async def endpoint_gen(req: EndpointGenRequest):
    from code_agents.api.endpoint_generator import EndpointGenerator, EndpointGenConfig

    config = EndpointGenConfig(
        resource_name=req.resource_name,
        framework=req.framework,
        fields=req.fields,
        cwd=_cwd(req.cwd),
    )
    result = EndpointGenerator(config).generate()
    return asdict(result)


@router.post("/api-sync")
async def api_sync(req: ApiSyncRequest):
    from code_agents.api.api_sync import ApiSyncer, ApiSyncConfig

    config = ApiSyncConfig(spec_file=req.spec_file, cwd=_cwd(req.cwd))
    result = ApiSyncer(config).check()
    return asdict(result)


@router.post("/response-optimize")
async def response_optimize(req: ResponseOptimizeRequest):
    from code_agents.core.response_optimizer import ResponseOptimizer, ResponseOptimizerConfig

    config = ResponseOptimizerConfig(cwd=_cwd(req.cwd))
    result = ResponseOptimizer(config).scan()
    return asdict(result)


@router.post("/rest-to-grpc")
async def rest_to_grpc(req: RestToGrpcRequest):
    from code_agents.api.rest_to_grpc import RestToGrpcConverter, RestToGrpcConfig

    config = RestToGrpcConfig(cwd=_cwd(req.cwd))
    result = RestToGrpcConverter(config).convert()
    return asdict(result)


@router.post("/api-changelog")
async def api_changelog(req: ApiChangelogRequest):
    from code_agents.api.api_changelog_gen import ApiChangelogGenerator, ApiChangelogConfig

    config = ApiChangelogConfig(
        old_spec=req.old_spec,
        new_spec=req.new_spec,
        cwd=_cwd(req.cwd),
    )
    result = ApiChangelogGenerator(config).generate()
    return asdict(result)
