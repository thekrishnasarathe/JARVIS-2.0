"""JARVIS 2.0 — FastAPI Production Web & API Gateway.

Provides a production-hardened REST API for JARVIS 2.0 with full CORS support,
health checks, graceful fallbacks, and static web UI hosting for cloud deployments
(Render, Railway, Hugging Face Spaces, Fly.io).
"""

from __future__ import annotations

import datetime
import logging
import os
import platform
import sys
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Ensure project root is in sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.core.router import process_command
from shared.logging_config import configure_logging
from shared.schemas import CommandResult, Severity

configure_logging()
logger = logging.getLogger("jarvis.api")

app = FastAPI(
    title="JARVIS 2.0 Web & API Gateway",
    description="Production REST API and Web Interface for JARVIS 2.0 Multi-Modal Desktop AI",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── CORS Configuration ───────────────────────────────────────────────
frontend_env = os.getenv("FRONTEND_URL", "").strip()
default_origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8000",
]

if frontend_env and frontend_env != "*":
    for u in frontend_env.split(","):
        cleaned = u.strip()
        if cleaned and cleaned not in default_origins:
            default_origins.append(cleaned)
    allowed_origins = default_origins
    allow_credentials = True
elif frontend_env == "*":
    allowed_origins = ["*"]
    allow_credentials = False
else:
    allowed_origins = default_origins
    allow_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=allow_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["*"],
    max_age=86400,
)


# ─── Request & Response Models ────────────────────────────────────────
class CommandRequest(BaseModel):
    command: str = Field(..., description="The query or command for JARVIS")

    class Config:
        json_schema_extra = {"example": {"command": "system status"}}


class CommandResponse(BaseModel):
    text: str
    severity: str
    source: str
    continue_loop: bool
    timestamp: str = Field(
        default_factory=lambda: datetime.datetime.now().isoformat()
    )


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    timestamp: str
    platform: str
    python: str


# ─── API Endpoints ────────────────────────────────────────────────────
@app.get("/health", response_model=HealthResponse, tags=["Diagnostics"])
def health_check() -> HealthResponse:
    """Lightweight health check endpoint for uptime monitors and container orchestrators."""
    return HealthResponse(
        status="ok",
        app="JARVIS 2.0",
        version="2.0.0",
        timestamp=datetime.datetime.now().isoformat(),
        platform=platform.system(),
        python=sys.version.split()[0],
    )


@app.post("/api/command", response_model=CommandResponse, tags=["Core"])
def handle_command(payload: CommandRequest) -> CommandResponse:
    """Execute a command through the JARVIS central router."""
    query = payload.command.strip()
    if not query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Command string cannot be empty.",
        )

    try:
        result = process_command(query)
        severity_val = (
            result.severity.value
            if hasattr(result.severity, "value")
            else str(result.severity)
        )
        return CommandResponse(
            text=result.text,
            severity=severity_val,
            source=result.source,
            continue_loop=result.continue_loop,
        )
    except Exception as exc:
        logger.exception("Error processing command '%s': %s", query, exc)
        return CommandResponse(
            text=f"An unexpected internal error occurred: {str(exc)}",
            severity="error",
            source="api_gateway",
            continue_loop=True,
        )


@app.post("/api/chat", response_model=CommandResponse, tags=["Core"])
def handle_chat(payload: CommandRequest) -> CommandResponse:
    """Alias for /api/command to integrate seamlessly with standard web chat components."""
    return handle_command(payload)


@app.get("/api/status", tags=["Diagnostics"])
def get_system_status() -> dict[str, Any]:
    """Retrieve runtime diagnostics, memory stats, and plugin registry metadata."""
    try:
        import psutil

        cpu_percent = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        memory_usage_pct = mem.percent
    except Exception:
        cpu_percent = 0.0
        memory_usage_pct = 0.0

    from shared.plugin_registry import PluginRegistry

    plugins = PluginRegistry.get_instance().list_plugins()

    try:
        from backend.modules.memory import get_engine

        memory_stats = get_engine().get_stats()
    except Exception:
        memory_stats = {"total_memories": 0}

    return {
        "status": "online",
        "cpu_percent": cpu_percent,
        "ram_percent": memory_usage_pct,
        "active_plugins": len(plugins),
        "plugins": [
            {
                "name": p.metadata.name,
                "version": p.metadata.version,
                "author": p.metadata.author,
            }
            for p in plugins
        ],
        "memory_stats": memory_stats,
        "timestamp": datetime.datetime.now().isoformat(),
    }


@app.get("/api/memory", tags=["Memory"])
def get_memories(limit: int = 50) -> list[dict[str, Any]]:
    """Retrieve recent eidetic memories for visualization or spatial plotting."""
    try:
        from backend.modules.memory import get_engine

        engine = get_engine()
        return engine.get_recent_memories(limit=limit)
    except Exception as exc:
        logger.error("Failed to fetch memories: %s", exc)
        return []


# ─── Static Web UI Mount ─────────────────────────────────────────────
web_dir = os.path.join(BASE_DIR, "web")
if os.path.isdir(web_dir):
    app.mount("/static", StaticFiles(directory=web_dir), name="static")

    @app.get("/", include_in_schema=False)
    def serve_index():
        index_file = os.path.join(web_dir, "index.html")
        if os.path.isfile(index_file):
            return FileResponse(index_file)
        return JSONResponse(
            {"message": "JARVIS 2.0 API Online. Visit /docs for Swagger UI."}
        )
