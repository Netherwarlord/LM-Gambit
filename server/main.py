"""FastAPI application factory.

In production the same process serves the JSON API and the compiled React
bundle from ``web/dist``. During frontend development Vite serves the UI on its
own port and proxies ``/api`` back here, so CORS is opened for localhost only.
"""

from __future__ import annotations

from pathlib import Path

import sys

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from . import __version__
from .api import router
from .core_bridge import ROOT_DIR, ensure_directories
from .plugins import get_plugin_manager

WEB_DIST = ROOT_DIR / "web" / "dist"

DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def create_app() -> FastAPI:
    ensure_directories()

    app = FastAPI(
        title="LM-Gambit",
        description="Automated LLM diagnostic suite.",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=DEV_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    _mount_plugin_routes(app)

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok", "version": __version__, "ui_built": WEB_DIST.is_dir()}

    _mount_frontend(app)
    return app


def _mount_plugin_routes(app: FastAPI) -> None:
    """Give each plugin defining register_routes its own /api/plugins/<slug>.

    Routes are bound at startup, so a plugin that adds or changes endpoints
    needs a server restart — unlike its other hooks, which reload live.
    """
    manager = get_plugin_manager()
    for plugin in manager.with_hook("register_routes"):
        plugin_router = APIRouter(
            prefix=f"/api/plugins/{plugin.slug}",
            tags=[f"plugin:{plugin.slug}"],
        )
        try:
            plugin.module.register_routes(plugin_router)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001 - never let a plugin block startup
            print(
                f"[plugin:{plugin.slug}] register_routes() failed: {exc}",
                file=sys.stderr,
            )
            continue
        if plugin_router.routes:
            app.include_router(plugin_router)


def _mount_frontend(app: FastAPI) -> None:
    assets_dir = WEB_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(request: Request, full_path: str) -> object:
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not found."}, status_code=404)

        index_file = WEB_DIST / "index.html"
        if not index_file.is_file():
            return JSONResponse(
                {
                    "detail": "Frontend not built.",
                    "fix": "Run 'npm install && npm run build' inside web/, "
                    "or start the Vite dev server with 'npm run dev'.",
                },
                status_code=503,
            )

        # Serve real files (favicon, manifest, …) directly; everything else
        # falls through to index.html so client-side routing works on reload.
        if full_path:
            candidate = (WEB_DIST / full_path).resolve()
            if candidate.is_file() and WEB_DIST.resolve() in candidate.parents:
                return FileResponse(candidate)

        return FileResponse(index_file)


app = create_app()
