import uvicorn
from pathlib import Path
import sys

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.core.config import settings
from backend.app.routers.accuracy import router as accuracy_router
from backend.app.routers.instruments import router as instrument_router
from backend.app.routers.measurement import router as measurement_router
from backend.app.routers.state_estimation import router as state_estimation_router
from backend.app.routers.system import router as system_router

app = FastAPI(title=settings.app_name, version=settings.app_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system_router)
app.include_router(instrument_router)
app.include_router(measurement_router)
app.include_router(state_estimation_router)
app.include_router(accuracy_router)

# Frontend build output (dev: frontend/dist; portable package: may be same relative path)
_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
_HAS_FRONTEND_DIST = (_FRONTEND_DIST / "index.html").is_file()

_API_RESERVED_PREFIXES = (
    "api",
    "docs",
    "redoc",
    "openapi.json",
    "openapi",
)


def _is_api_or_docs_path(full_path: str) -> bool:
    cleaned = (full_path or "").lstrip("/")
    if not cleaned:
        return False
    head = cleaned.split("/", 1)[0]
    return head in _API_RESERVED_PREFIXES or cleaned in _API_RESERVED_PREFIXES


if _HAS_FRONTEND_DIST:
    _assets_dir = _FRONTEND_DIST / "assets"
    if _assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")

    @app.get("/")
    async def spa_root():
        return FileResponse(_FRONTEND_DIST / "index.html")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        """Serve built SPA files; leave /api and docs to FastAPI routes."""
        if _is_api_or_docs_path(full_path):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (_FRONTEND_DIST / full_path).resolve()
        try:
            candidate.relative_to(_FRONTEND_DIST.resolve())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Not Found") from exc
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIST / "index.html")
else:

    @app.get("/")
    async def root() -> dict[str, str]:
        return {
            "message": "NV Measurement Backend is running.",
            "frontend": "Dev: npm run dev on :5173. Portable: build frontend/dist then restart.",
            "docs": "/docs",
        }


if __name__ == "__main__":
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=False)
