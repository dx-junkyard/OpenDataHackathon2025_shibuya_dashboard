"""KPI のデータ準備: オープンデータ検索 (F-08) とデータ整形 (F-09)."""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from .. import kpi_targets, llm, proposals
from ..agents import opendata, shaping
from ..db import get_conn
from ..deps import current_user

router = APIRouter()


def datasets_dir() -> str:
    return os.getenv("APP_DATASETS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "data", "datasets"))


def _kpi_for_author(conn, kpi_id: int, user: dict):
    k = conn.execute(
        "SELECT k.*, ic.author_id, ic.id AS card_id FROM kpis k JOIN issue_cards ic ON ic.id = k.issue_card_id WHERE k.id = ?",
        (kpi_id,)).fetchone()
    if k is None:
        raise HTTPException(404, "KPI が見つかりません")
    if k["author_id"] != user["id"]:
        raise HTTPException(403, "課題カードの作成者だけがデータを設定できます")
    return k


def dataset_out(row) -> dict:
    return {**dict(row), "is_sample": bool(row["is_sample"])}


@router.get("/datasets")
def list_datasets():
    with get_conn() as conn:
        return {"items": [dataset_out(r) for r in conn.execute("SELECT * FROM datasets ORDER BY id")]}


@router.get("/ingest-runs")
def list_ingest_runs(kind: Optional[str] = None, limit: int = 50):
    """What the real-data ingest looked at, including sources it could not fetch (F-08 の検索範囲)."""
    q, args = "SELECT * FROM ingest_runs", ()
    if kind:
        q, args = q + " WHERE kind = ?", (kind,)
    with get_conn() as conn:
        return {"items": [dict(r) for r in conn.execute(q + " ORDER BY id DESC LIMIT ?", (*args, min(limit, 200)))]}


@router.post("/datasets", status_code=201)
async def register_dataset(
    title: str = Form(..., min_length=1, max_length=200),
    publisher: str = Form(..., min_length=1, max_length=200),
    license: str = Form(..., min_length=1, max_length=100),
    source_url: str = Form(default="", max_length=500),
    description: str = Form(default="", max_length=1000),
    updated_on: str = Form(default="", max_length=20),
    granularity: str = Form(default="", max_length=100),
    tags: str = Form(default="", max_length=200),
    file: UploadFile = File(...),
    user: dict = Depends(current_user),
):
    ext = os.path.splitext(file.filename or "")[1].lower().lstrip(".")
    ext = {"htm": "html"}.get(ext, ext)
    if ext not in shaping.FILE_FORMATS:
        raise HTTPException(422, "CSV / Excel（.xlsx）/ PDF / HTML のみ登録できます")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "ファイルは 10MB までです")
    name = f"upload-{uuid.uuid4().hex}.{ext}"
    os.makedirs(datasets_dir(), exist_ok=True)
    with open(os.path.join(datasets_dir(), name), "wb") as f:
        f.write(data)
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO datasets (title, publisher, description, source_url, license, file_format, file_path,"
            " updated_on, granularity, tags, is_sample) VALUES (?,?,?,?,?,?,?,?,?,?,0)",
            (title, publisher, description, source_url, license, ext, name, updated_on, granularity, tags))
        return dataset_out(conn.execute("SELECT * FROM datasets WHERE id = ?", (cur.lastrowid,)).fetchone())


@router.post("/kpis/{kpi_id}/dataset-search", status_code=201)
def search_datasets(kpi_id: int, user: dict = Depends(current_user)):
    with get_conn() as conn:
        k = _kpi_for_author(conn, kpi_id, user)
        catalog = [dataset_out(r) for r in conn.execute("SELECT * FROM datasets ORDER BY id")]
    try:
        result = opendata.search(dict(k), catalog)
    except llm.LLMUnavailable as exc:
        raise HTTPException(503, {"code": "ai_unavailable", "message": str(exc)}) from exc
    by_id = {d["id"]: d for d in catalog}
    payload = {
        "searched_count": len(catalog),
        "candidates": [{"dataset": by_id[c["dataset_id"]], "reason": c["reason"]} for c in result["candidates"]],
    }
    with get_conn() as conn:
        pid = proposals.create(conn, kind="dataset_candidates", target_ref=f"kpi:{kpi_id}", payload=payload,
                               evidence=[{"kind": "data", "ref": "datasets", "label": f"登録済みデータセット {len(catalog)} 件"}],
                               user_id=user["id"])
        return proposals.to_out(proposals.load(conn, pid))


class PlanRequest(BaseModel):
    dataset_id: int
    search_proposal_id: Optional[int] = None


def _read(file_path: str, file_format: str) -> list:
    try:
        return shaping.read_tables(shaping.dataset_file(os.path.abspath(datasets_dir()), file_path), file_format)
    except (OSError, shaping.ShapingError) as exc:
        raise HTTPException(422, f"データを読み込めませんでした: {exc}") from exc


def _snapshots(ds) -> list:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT as_of, file_path, file_format FROM dataset_snapshots WHERE dataset_id = ? ORDER BY as_of", (ds["id"],))]


def _plan_rows(ds, snaps: list, plan: dict) -> list:
    """Rows the plan runs on: the selected table of the file, or of every snapshot with 取得時点 added."""
    if not snaps:
        return shaping.table_rows(_read(ds["file_path"], ds["file_format"]), plan)
    rows = []
    for s in snaps:
        rows += [{**r, shaping.SNAPSHOT_COLUMN: s["as_of"]}
                 for r in shaping.table_rows(_read(s["file_path"], s["file_format"]), plan)]
    return rows


def _snapshot_note(snaps: list) -> str:
    if not snaps:
        return ""
    return (f"このデータセットは取得時点ごとの版が {len(snaps)} 回分（{'、'.join(s['as_of'] for s in snaps)}）あり、"
            f"表の各行に「{shaping.SNAPSHOT_COLUMN}」列（YYYY-MM-DD）が付きます。")


@router.post("/kpis/{kpi_id}/shaping-plans", status_code=201)
def propose_shaping(kpi_id: int, req: PlanRequest, user: dict = Depends(current_user)):
    with get_conn() as conn:
        k = _kpi_for_author(conn, kpi_id, user)
        ds = conn.execute("SELECT * FROM datasets WHERE id = ?", (req.dataset_id,)).fetchone()
        if ds is None:
            raise HTTPException(404, "データセットが見つかりません")
        if req.search_proposal_id is not None:
            sp = proposals.load(conn, req.search_proposal_id, "dataset_candidates")
            if sp["target_ref"] != f"kpi:{kpi_id}":
                raise HTTPException(422, "別の KPI の検索結果です")
            if sp["status"] == "proposed":
                ids = [c["dataset"]["id"] for c in json.loads(sp["payload"])["candidates"]]
                proposals.decide(conn, sp["id"], "adopted" if req.dataset_id in ids else "adopted_edited",
                                 user["id"], result_ref=f"dataset:{req.dataset_id}")
    snaps = _snapshots(ds)
    tables = _read(snaps[-1]["file_path"], snaps[-1]["file_format"]) if snaps else _read(ds["file_path"], ds["file_format"])
    if not any(len(t["rows"]) > 1 for t in tables):
        raise HTTPException(422, "データが空です")
    try:
        plan = shaping.propose_plan(dict(k), tables, _snapshot_note(snaps))
    except llm.LLMUnavailable as exc:
        raise HTTPException(503, {"code": "ai_unavailable", "message": str(exc)}) from exc
    payload = {"dataset_id": req.dataset_id, "plan": plan, "columns": [], "before_sample": [], "warnings": [],
               "tables": [{"index": i, "name": t["name"], "row_count": len(t["rows"])} for i, t in enumerate(tables)],
               "snapshots": [s["as_of"] for s in snaps]}
    try:
        rows = _plan_rows(ds, snaps, plan)
        payload["columns"] = list(rows[0].keys()) if rows else []
        payload["before_sample"] = rows[:5]
        payload["warnings"] = shaping.plan_warnings(plan, shaping.profile_columns(rows),
                                                    snapshot_count=len(snaps) if snaps else None)
        payload["after_preview"] = shaping.apply_plan(rows, plan)
        payload["preview_error"] = ""
    except shaping.ShapingError as exc:
        payload["after_preview"] = []
        payload["preview_error"] = str(exc)
    with get_conn() as conn:
        pid = proposals.create(conn, kind="shaping_plan", target_ref=f"kpi:{kpi_id}", payload=payload,
                               evidence=[{"kind": "data", "ref": f"dataset:{req.dataset_id}", "label": ds["title"]}],
                               user_id=user["id"])
        return proposals.to_out(proposals.load(conn, pid))


class AdoptPlan(BaseModel):
    plan: Optional[dict] = None


@router.post("/shaping-plans/{proposal_id}/adopt")
def adopt_shaping(proposal_id: int, body: AdoptPlan, user: dict = Depends(current_user)):
    with get_conn() as conn:
        prop = proposals.load(conn, proposal_id, "shaping_plan")
        proposals.require_open(prop)
        kpi_id = int(prop["target_ref"].split(":")[1])
        _kpi_for_author(conn, kpi_id, user)
        payload = json.loads(prop["payload"])
        ds = conn.execute("SELECT * FROM datasets WHERE id = ?", (payload["dataset_id"],)).fetchone()
    plan = body.plan or payload["plan"]
    edited = body.plan is not None and body.plan != payload["plan"]
    try:
        points = shaping.apply_plan(_plan_rows(ds, _snapshots(ds), plan), plan)
    except shaping.ShapingError as exc:
        raise HTTPException(422, str(exc)) from exc
    with get_conn() as conn:
        conn.execute("DELETE FROM kpi_points WHERE kpi_id = ?", (kpi_id,))
        for p in points:
            conn.execute("INSERT INTO kpi_points (kpi_id, period, value, proposal_id) VALUES (?,?,?,?)",
                         (kpi_id, p["period"], p["value"], proposal_id))
        conn.execute("UPDATE kpis SET dataset_id = ? WHERE id = ?", (payload["dataset_id"], kpi_id))
        conn.execute("UPDATE issue_cards SET status = CASE WHEN status = 'published' THEN 'verifying' ELSE status END,"
                     " updated_at = ? WHERE id = (SELECT issue_card_id FROM kpis WHERE id = ?)", (time.time(), kpi_id))
        proposals.decide(conn, proposal_id, "adopted_edited" if edited else "adopted", user["id"], result_ref=f"kpi:{kpi_id}")
        kpi_targets.check(conn, kpi_id)
        return {"kpi_id": kpi_id, "points": points}


class TargetIn(BaseModel):
    target_value: Optional[float] = None
    target_direction: Literal["increase", "decrease"] = "increase"


@router.put("/kpis/{kpi_id}/target")
def set_target(kpi_id: int, body: TargetIn, user: dict = Depends(current_user)):
    with get_conn() as conn:
        _kpi_for_author(conn, kpi_id, user)
        conn.execute("UPDATE kpis SET target_value = ?, target_direction = ? WHERE id = ?",
                     (body.target_value, body.target_direction, kpi_id))
        kpi_targets.check(conn, kpi_id)
        return dict(conn.execute("SELECT * FROM kpis WHERE id = ?", (kpi_id,)).fetchone())

