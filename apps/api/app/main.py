"""渋谷共創ダッシュボード API."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import llm, observe
from .db import init_db
from .routes import communities, dashboards, data, issues, news, policy, surveys


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="渋谷共創ダッシュボード API", version="0.1.0", lifespan=lifespan)

for r in (news.router, issues.router, data.router, dashboards.router, communities.router, policy.router,
          surveys.router):
    app.include_router(r, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True, "ai_available": llm.is_configured(), "model": llm.model_name(), "probe_enabled": observe.enabled()}
