import logging
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from chusky_bridge.api import admin, approvals, catalog, connectors, tools
from chusky_bridge.auth import AuthError, identity_var, verify_token
from chusky_bridge.config import require_server_config, settings
from chusky_bridge.db import SessionLocal, engine
from chusky_bridge.mcp.server import mcp
from chusky_bridge.models import Base
from chusky_bridge.observability import configure_logging, request_id_var
from chusky_bridge.workers.discovery_worker import load_manifest_dir

configure_logging(settings.log_level, settings.log_json)
log = logging.getLogger("chusky_bridge")

mcp_http_app = mcp.streamable_http_app()
_REQUEST_ID = re.compile(r"^[A-Za-z0-9\-]{8,64}$")


@asynccontextmanager
async def lifespan(_: FastAPI):
    require_server_config()
    if settings.env == "development":
        # Production applies migrations with Alembic before the service starts.
        Base.metadata.create_all(bind=engine)
    if settings.load_manifests_on_start:
        loaded = load_manifest_dir(Path(settings.manifest_dir))
        log.info("loaded connectors", extra={"connectors": loaded})
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="Chusky Bridge",
    description="Governed MCP access to legacy and modern enterprise systems",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    incoming = request.headers.get("x-request-id", "")
    request_id = incoming if _REQUEST_ID.match(incoming) else str(uuid.uuid4())
    token = request_id_var.set(request_id)
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def mcp_auth(request: Request, call_next):
    """Authenticate every MCP request and bind the caller's identity for the tools."""
    if not request.url.path.startswith("/mcp"):
        return await call_next(request)

    challenge = f'Bearer resource_metadata="{settings.public_base_url}/.well-known/oauth-protected-resource"'
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return JSONResponse({"error": "unauthorized"}, status_code=401, headers={"WWW-Authenticate": challenge})
    try:
        identity = await run_in_threadpool(verify_token, header[7:].strip())
    except AuthError:
        return JSONResponse(
            {"error": "invalid_token"},
            status_code=401,
            headers={"WWW-Authenticate": f'{challenge}, error="invalid_token"'},
        )

    token = identity_var.set(identity)
    try:
        return await call_next(request)
    finally:
        identity_var.reset(token)


@app.get("/healthz", tags=["ops"])
def healthz() -> dict:
    """Liveness: the process is running."""
    return {"status": "ok", "env": settings.env}


@app.get("/readyz", tags=["ops"])
async def readyz():
    """Readiness: the database answers. Load balancers should route only to ready instances."""

    def ping() -> None:
        session = SessionLocal()
        try:
            session.execute(text("SELECT 1"))
        finally:
            session.close()

    try:
        await run_in_threadpool(ping)
    except Exception:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return {"status": "ready"}


if settings.metrics_enabled:

    @app.get("/metrics", tags=["ops"], include_in_schema=False)
    def metrics() -> Response:
        """Prometheus metrics. Expose only on an internal interface or behind network policy."""
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/.well-known/oauth-protected-resource", tags=["ops"])
def protected_resource_metadata() -> dict:
    return {
        "resource": f"{settings.public_base_url}/mcp",
        "authorization_servers": [settings.jwt_issuer],
        "bearer_methods_supported": ["header"],
    }


app.include_router(connectors.router)
app.include_router(tools.router)
app.include_router(approvals.router)
app.include_router(admin.router)
app.include_router(catalog.router)

app.mount("/mcp", mcp_http_app)
