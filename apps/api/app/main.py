"""渋谷共創ダッシュボード API."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import uuid

from fastapi import FastAPI, Request
from starlette.routing import compile_path

from . import llm, observe
from .db import init_db
from .ingest import schedule
from .routes import communities, dashboards, data, issues, news, policy, surveys


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    task = asyncio.create_task(schedule.loop()) if schedule.interval_hours() > 0 else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="渋谷共創ダッシュボード API", version="0.1.0", lifespan=lifespan)

API_PREFIX = "/api"
ROUTERS = (news.router, issues.router, data.router, dashboards.router, communities.router, policy.router,
           surveys.router)
for r in ROUTERS:
    app.include_router(r, prefix=API_PREFIX)

# (method, route template, compiled regex) for naming a request by its route,
# built from the routers this app mounts rather than framework internals.
ROUTE_TEMPLATES = [
    (m, API_PREFIX + rt.path, compile_path(API_PREFIX + rt.path)[0])
    for r in ROUTERS for rt in r.routes for m in getattr(rt, "methods", ()) or ()
]


def route_template(method: str, path: str) -> str:
    for m, template, regex in ROUTE_TEMPLATES:
        if m == method and regex.match(path):
            return template
    return path


@app.middleware("http")
async def probe_request_context(request: Request, call_next):
    """One correlation id per request and the matched route as the flow id,
    so the AI agents traced during a request are grouped under it (probe-agent
    shows the request's calls as a waterfall)."""
    if not observe.enabled():
        return await call_next(request)
    correlation_id = uuid.uuid4().hex
    with observe.request_context(correlation_id, f"{request.method} {route_template(request.method, request.url.path)}"):
        response = await call_next(request)
    response.headers["X-Probe-Correlation-Id"] = correlation_id
    return response


@app.get("/api/health")
def health():
    return {"ok": True, "ai_available": llm.is_configured(), "model": llm.model_name(), "probe_enabled": observe.enabled()}
