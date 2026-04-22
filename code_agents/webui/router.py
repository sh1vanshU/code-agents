"""Web UI router — serves static SPA interface."""
import logging
from pathlib import Path

from fastapi import APIRouter

logger = logging.getLogger("code_agents.webui.router")
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

router = APIRouter(tags=["webui"])
STATIC_DIR = Path(__file__).parent / "static"


@router.get("/ui")
async def ui_index():
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/telemetry-dashboard")
async def telemetry_page():
    """Redirect legacy telemetry page to SPA dashboard view."""
    return FileResponse(STATIC_DIR / "telemetry.html")


@router.get("/dashboard")
async def dashboard_page():
    """Redirect legacy dashboard to SPA dashboard view."""
    return FileResponse(STATIC_DIR / "dashboard.html")


@router.get("/ui/{path:path}")
async def ui_static(path: str):
    file_path = STATIC_DIR / path
    if file_path.is_file():
        return FileResponse(file_path)
    return HTMLResponse("Not found", status_code=404)
