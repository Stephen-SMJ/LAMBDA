from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import asyncio
import os
from urllib.parse import urlparse

from app.core.database import engine, Base, ensure_schema_compatibility
from app.api.v1 import api_router
from app.core.config import settings


# Create database tables
Base.metadata.create_all(bind=engine)
ensure_schema_compatibility()

# Ensure upload directory exists for local fallback
os.makedirs("./data/uploads", exist_ok=True)
os.makedirs("./data/images", exist_ok=True)
os.makedirs("./data/latex", exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 LAMBDA server starting up...")
    print(f"   Database: {'PostgreSQL' if 'postgresql' in settings.DATABASE_URL else 'SQLite'}")
    print(f"   File Storage: {settings.FILE_STORAGE_MODE}")
    print(f"   Code Execution: {settings.CODE_EXECUTION_MODE}")
    cleanup_task = None

    async def cleanup_idle_sandboxes():
        from app.services.opensandbox_service import get_opensandbox_service

        while True:
            await asyncio.sleep(60)
            try:
                await get_opensandbox_service().cleanup_idle_sessions()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"Sandbox idle cleanup failed: {exc}")

    if settings.CODE_EXECUTION_MODE == "opensandbox":
        from app.services.opensandbox_service import get_opensandbox_service

        await get_opensandbox_service().cleanup_orphan_containers_on_startup()
        cleanup_task = asyncio.create_task(cleanup_idle_sandboxes())

    try:
        yield
    finally:
        if cleanup_task:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
    # Shutdown
    print("👋 LAMBDA server shutting down...")


app = FastAPI(
    title="LAMBDA API",
    description="LLM Data Science Agents API - Production",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.FILE_STORAGE_MODE == "local" else None,
    redoc_url="/redoc" if settings.FILE_STORAGE_MODE == "local" else None,
)

# CORS middleware
frontend_origin = settings.FRONTEND_URL.rstrip("/")
frontend_host = urlparse(frontend_origin).hostname
allowed_origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    frontend_origin,
]
if frontend_host:
    allowed_origins.extend(
        [
            f"http://{frontend_host}",
            f"http://{frontend_host}:3000",
            f"https://{frontend_host}",
        ]
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(allowed_origins)),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api/v1")

# Mount static files for uploads (local fallback)
if settings.FILE_STORAGE_MODE == "local":
    app.mount("/uploads", StaticFiles(directory="./data/uploads"), name="uploads")
    app.mount("/images", StaticFiles(directory="./data/images"), name="images")


@app.get("/api/v1/public/config")
async def public_config():
    return {
        "local_mode": settings.LOCAL_MODE,
        "turnstile_enabled": False,
        "turnstile_site_key": "",
    }


@app.get("/")
async def root():
    return {
        "name": "LAMBDA API",
        "version": "1.0.0",
        "description": "LLM Data Science Agents Platform - Production",
        "status": "running",
        "docs_url": "/docs" if settings.FILE_STORAGE_MODE == "local" else None
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "lambda-api",
        "database": "connected",
        "storage": settings.FILE_STORAGE_MODE,
        "code_execution": settings.CODE_EXECUTION_MODE
    }


# Also add health check under /api/v1 for consistency
@app.get("/api/v1/health")
async def api_health_check():
    return {
        "status": "healthy",
        "service": "lambda-api",
        "database": "connected",
        "storage": settings.FILE_STORAGE_MODE,
        "code_execution": settings.CODE_EXECUTION_MODE
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # Disable reload in production
        log_level="info",
        workers=4  # Multiple workers for production
    )
