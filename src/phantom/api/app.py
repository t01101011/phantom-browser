"""FastAPI application factory for Phantom Browser control plane.

The app binds to 127.0.0.1 by default and exposes:
- Public endpoints (no auth): ``/healthz``, ``/docs``, ``/openapi.json``
- Authenticated endpoints: ``/readyz``, ``/v1/*``

Usage
-----
.. code-block:: python

    uvicorn phantom.api.app:create_app() --host 127.0.0.1 --port 5100
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.routing import Route

from phantom.api.auth import load_or_generate_token
from phantom.api.routes_health import router as health_router
from phantom.api.routes_profiles import router as profiles_router
from phantom.api.routes_folders import router as folders_router
from phantom.api.routes_proxies import router as proxies_router
from phantom.api.routes_sessions import router as sessions_router
from phantom.api.routes_events import router as events_router
from phantom.api.routes_instant import router as instant_router
from phantom.api.routes_leases import router as leases_router
from phantom.api.routes_artifacts import router as artifacts_router
from phantom.api.routes_actions import router as actions_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Async setup/teardown for the FastAPI application.

    Token creation is now done eagerly in ``create_app()``, so this
    handler is reserved for future async operations (DB pool warm-up,
    health-check timers, etc.).
    """
    app.state.lease_service.start_sweeper()
    try:
        async with app.state.mcp_server.session_manager.run():
            yield
    finally:
        app.state.lease_service.stop_sweeper()


def create_app() -> FastAPI:
    """Build the FastAPI application instance.

    The token auth file is auto-created (or loaded) eagerly **before**
    returning, so it is available immediately — even before the lifespan
    handler runs (important for tests using ``TestClient`` without ``with``
    and for production code that reads the token before binding the port).

    The ``lifespan`` handler is retained for future async setup (e.g. DB
    connection pool warm-up), but token creation happens here synchronously.
    """
    # Eagerly ensure the token exists before the app starts accepting
    # requests.  This is safe because ``load_or_generate_token`` is
    # idempotent — it reads an existing token if one is already present.
    load_or_generate_token()

    # Ensure DB tables and migrations exist (idempotent).
    from phantom.db import init_db
    init_db()

    app = FastAPI(
        title="Phantom Browser",
        description="Self-hosted antidetect browser profile manager — control plane API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )
    # Desktop dev UI is served by Vite on loopback. Production uses the
    # tauri://localhost origin. Keep the allow-list exact; bearer auth remains
    # mandatory and credentials are never accepted through cookies.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:1420", "http://127.0.0.1:1420", "tauri://localhost"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "Last-Event-ID"],
    )

    # Mount health/version routes (some are public, some require auth via
    # dependencies on the individual endpoints).
    app.include_router(health_router)

    # Profile, folder, and proxy CRUD routes (all require auth).
    app.include_router(profiles_router)
    app.include_router(folders_router)
    app.include_router(proxies_router)
    app.include_router(sessions_router)
    app.include_router(events_router)
    app.include_router(instant_router)
    app.include_router(leases_router)
    app.include_router(artifacts_router)
    app.include_router(actions_router)

    from phantom.services.session_service import SessionService
    app.state.session_service = SessionService()
    from phantom.services.lease_service import LeaseService, ArtifactService
    app.state.lease_service = LeaseService(app.state.session_service)
    app.state.artifact_service = ArtifactService(app.state.session_service)
    from phantom.agent.actions import SessionActionService
    app.state.action_service = SessionActionService(app.state.session_service, app.state.lease_service)

    # One in-process Streamable HTTP endpoint shares REST's service instances.
    from phantom.mcp.server import create_mcp_app
    mcp_app, app.state.mcp_server = create_mcp_app(
        app.state.session_service, app.state.lease_service, app.state.action_service
    )
    app.router.routes.append(Route("/mcp", mcp_app, methods=["GET", "POST", "DELETE"], name="mcp"))

    return app
