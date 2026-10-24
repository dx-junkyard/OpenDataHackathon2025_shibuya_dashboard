"""Periodic real-data ingest inside the API process (運用: 定期取得).

Off unless INGEST_INTERVAL_HOURS is set (> 0). Each run fetches the open data
and news as `python -m app.ingest all` does; a new dataset version re-runs the
KPIs built on it (kpi_refresh). Failures are recorded in ingest_runs, never raised.
"""
from __future__ import annotations

import asyncio
import logging
import os

log = logging.getLogger(__name__)


def interval_hours() -> float:
    try:
        return float(os.getenv("INGEST_INTERVAL_HOURS", "0"))
    except ValueError:
        return 0.0


def run_once() -> None:
    from ..db import get_conn
    from ..routes.data import datasets_dir
    from . import news, opendata

    with get_conn() as conn:
        try:
            opendata.run(conn, os.path.abspath(datasets_dir()))
            news.run(conn)
        except Exception as exc:  # a broken source must not stop the API
            log.exception("scheduled ingest failed")
            opendata.record(conn, "dataset", "定期取得", "failed", f"{type(exc).__name__}: {exc}")
    try:
        news.classify_unassigned()  # its own connections; never holds the database during a model call
    except Exception as exc:  # noqa: BLE001 - same rule: never stop the API
        log.exception("news focus-area estimation failed")
        with get_conn() as conn:
            opendata.record(conn, "news", "注力分野の推定", "failed", f"{type(exc).__name__}: {exc}")


async def loop() -> None:
    hours = interval_hours()
    while True:
        await asyncio.to_thread(run_once)
        await asyncio.sleep(hours * 3600)
