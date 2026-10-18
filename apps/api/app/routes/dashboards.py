"""KPI 追跡ダッシュボード (F-10) と区職員の採用判断 (F-13)."""
from __future__ import annotations

import csv
import io
import json
import secrets
import time
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..db import get_conn
from ..deps import current_user, require_staff
from ..domain import ADOPTION_TO_ISSUE_STATUS, FOCUS_AREAS
from .issues import card_out, personal_info_warnings

router = APIRouter()


def notify(conn, user_id: int, text: str, link: str) -> None:
    conn.execute("INSERT INTO notifications (user_id, text, link, created_at) VALUES (?,?,?,?)",
                 (user_id, text, link, time.time()))


def kpi_summary(k: dict) -> dict:
    pts = k["points"]
    current = pts[-1]["value"] if pts else None
    trend = None
    if len(pts) >= 2:
        diff = pts[-1]["value"] - pts[-2]["value"]
        trend = "up" if diff > 0 else "down" if diff < 0 else "flat"
    return {
        "id": k["id"], "name": k["name"], "unit": k["unit"], "measurement": k["measurement"],
        "target_value": k["target_value"], "current_value": current,
        "current_period": pts[-1]["period"] if pts else None,
        "data_status": "available" if pts else "not_collected",
        "trend": trend, "points": pts,
        "source": ({"title": k["dataset"]["title"], "publisher": k["dataset"]["publisher"],
                    "license": k["dataset"]["license"], "source_url": k["dataset"]["source_url"],
                    "updated_on": k["dataset"]["updated_on"], "is_sample": k["dataset"]["is_sample"]}
                   if k["dataset"] else None),
    }


def public_view(conn, card_id: int) -> dict:
    card = card_out(conn, card_id, None)
    return {
        "issue_card_id": card["id"],
        "title": card["title"],
        "target": card["target"],
        "place_time": card["place_time"],
        "focus_area": card["focus_area"],
        "focus_area_label": card["focus_area_label"],
        "status": card["status"],
        "status_label": card["status_label"],
        # Public view exposes evidence sources only, never individual posts or names (F-17).
        "evidence_sources": [{"kind": e["kind"], "text": e["text"]} for e in card["evidence"] if e["kind"] != "conversation"],
        "kpis": [kpi_summary(k) for k in card["kpis"]],
        "dashboard": card["dashboard"],
        "latest_decision": ({k: card["latest_decision"][k] for k in ("state", "reason", "department", "decided_at")}
                            if card["latest_decision"] else None),
        "annotations": [dict(a) for a in conn.execute(
            "SELECT period, label FROM annotations WHERE dashboard_id = ? ORDER BY period",
            (card["dashboard"]["id"],))] if card["dashboard"] else [],
    }


@router.get("/issue-cards/{card_id}/dashboard")
def preview_dashboard(card_id: int, user: dict = Depends(current_user)):
    with get_conn() as conn:
        card_out(conn, card_id, user)  # visibility check
        return public_view(conn, card_id)


class PublishIn(BaseModel):
    acknowledge_personal_info: bool = False


@router.post("/issue-cards/{card_id}/dashboard/publish")
def publish_dashboard(card_id: int, body: PublishIn, user: dict = Depends(current_user)):
    with get_conn() as conn:
        card = card_out(conn, card_id, user)
        if card["author_id"] != user["id"]:
            raise HTTPException(403, "課題カードの作成者だけが公開できます")
        if not card["kpis"]:
            raise HTTPException(422, "KPI が 1 件もありません")
        if card["visibility"] != "public":
            raise HTTPException(422, "課題カードの公開範囲が「全体公開」ではありません")
        found = personal_info_warnings(card["title"], card["target"], card["place_time"])
        if found and not body.acknowledge_personal_info:
            raise HTTPException(422, {"code": "personal_info", "message": f"公開前に確認してください: {'・'.join(found)}", "found": found})
        now = time.time()
        dash = conn.execute("SELECT * FROM dashboards WHERE issue_card_id = ?", (card_id,)).fetchone()
        if dash is None:
            conn.execute("INSERT INTO dashboards (issue_card_id, public_slug, status, published_by, published_at)"
                         " VALUES (?,?,?,?,?)", (card_id, secrets.token_urlsafe(8), "published", user["id"], now))
        else:
            # Re-publishing keeps the same fixed URL (docs/vision.md answer Q95).
            conn.execute("UPDATE dashboards SET status = 'published', published_by = ?, published_at = ? WHERE id = ?",
                         (user["id"], now, dash["id"]))
        if card["status"] in ("published", "verifying", "draft"):
            conn.execute("UPDATE issue_cards SET status = 'dashboard_published', updated_at = ? WHERE id = ?", (now, card_id))
        return public_view(conn, card_id)


@router.post("/issue-cards/{card_id}/dashboard/unpublish")
def unpublish_dashboard(card_id: int, user: dict = Depends(current_user)):
    with get_conn() as conn:
        card = card_out(conn, card_id, user)
        if card["author_id"] != user["id"] or not card["dashboard"]:
            raise HTTPException(403, "課題カードの作成者だけが非公開にできます")
        conn.execute("UPDATE dashboards SET status = 'private' WHERE issue_card_id = ?", (card_id,))
        return public_view(conn, card_id)


def _published(conn, slug: str):
    d = conn.execute("SELECT * FROM dashboards WHERE public_slug = ?", (slug,)).fetchone()
    if d is None:
        raise HTTPException(404, "ダッシュボードが見つかりません")
    if d["status"] != "published":
        raise HTTPException(410, "このダッシュボードは非公開です")
    return d


@router.get("/public/dashboards/{slug}")
def public_dashboard(slug: str):
    with get_conn() as conn:
        d = _published(conn, slug)
        return public_view(conn, d["issue_card_id"])


@router.get("/public/dashboards/{slug}/export.csv")
def export_csv(slug: str):
    with get_conn() as conn:
        d = _published(conn, slug)
        view = public_view(conn, d["issue_card_id"])
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["課題", "KPI", "単位", "期間", "値", "目標値", "出典", "提供者", "ライセンス", "出典URL", "データ更新日", "サンプルデータ"])
    for k in view["kpis"]:
        s = k["source"] or {}
        if not k["points"]:
            w.writerow([view["title"], k["name"], k["unit"], "", "未取得", k["target_value"] or "", "", "", "", "", "", ""])
        for p in k["points"]:
            w.writerow([view["title"], k["name"], k["unit"], p["period"], p["value"], k["target_value"] or "",
                        s.get("title", ""), s.get("publisher", ""), s.get("license", ""), s.get("source_url", ""),
                        s.get("updated_on", ""), "はい（架空）" if s.get("is_sample") else "いいえ"])
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="dashboard-{slug}.csv"'})


class AnnotationIn(BaseModel):
    period: str = Field(min_length=4, max_length=10)
    label: str = Field(min_length=1, max_length=100)


@router.post("/issue-cards/{card_id}/dashboard/annotations", status_code=201)
def add_annotation(card_id: int, body: AnnotationIn, user: dict = Depends(current_user)):
    with get_conn() as conn:
        card = card_out(conn, card_id, user)
        if not card["dashboard"]:
            raise HTTPException(422, "ダッシュボードがまだありません")
        if card["author_id"] != user["id"] and user["role"] != "staff":
            raise HTTPException(403, "作成者または区職員だけが注釈を追加できます")
        conn.execute("INSERT INTO annotations (dashboard_id, period, label, created_by, created_at) VALUES (?,?,?,?,?)",
                     (card["dashboard"]["id"], body.period, body.label, user["id"], time.time()))
        return public_view(conn, card_id)


@router.get("/staff/dashboards")
def staff_list(focus_area: Optional[str] = None, state: Optional[str] = None, user: dict = Depends(current_user)):
    require_staff(user)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT d.issue_card_id FROM dashboards d JOIN issue_cards ic ON ic.id = d.issue_card_id"
            " WHERE d.status = 'published' ORDER BY d.published_at DESC").fetchall()
        items = []
        for r in rows:
            v = public_view(conn, r["issue_card_id"])
            if focus_area and v["focus_area"] != focus_area:
                continue
            if state and (v["latest_decision"] or {}).get("state", "none") != state:
                continue
            card = conn.execute("SELECT community_id FROM issue_cards WHERE id = ?", (r["issue_card_id"],)).fetchone()
            members = conn.execute("SELECT COUNT(*) FROM community_members WHERE community_id = ?",
                                   (card["community_id"],)).fetchone()[0] if card["community_id"] else 0
            items.append({**v, "community_id": card["community_id"], "community_members": members})
    return {"items": items, "focus_areas": [{"key": k, "label": v} for k, v in FOCUS_AREAS.items()]}


class DecisionIn(BaseModel):
    state: Literal["under_review", "adopted", "declined"]
    reason: str = Field(min_length=1, max_length=1000)


@router.post("/dashboards/{dashboard_id}/decisions", status_code=201)
def decide(dashboard_id: int, body: DecisionIn, user: dict = Depends(current_user)):
    require_staff(user)
    with get_conn() as conn:
        d = conn.execute("SELECT * FROM dashboards WHERE id = ? AND status = 'published'", (dashboard_id,)).fetchone()
        if d is None:
            raise HTTPException(404, "公開中のダッシュボードが見つかりません")
        now = time.time()
        conn.execute("INSERT INTO adoption_decisions (dashboard_id, state, reason, department, decided_by, decided_at)"
                     " VALUES (?,?,?,?,?,?)", (dashboard_id, body.state, body.reason, user["department"], user["id"], now))
        card = conn.execute("SELECT * FROM issue_cards WHERE id = ?", (d["issue_card_id"],)).fetchone()
        conn.execute("UPDATE issue_cards SET status = ?, updated_at = ? WHERE id = ?",
                     (ADOPTION_TO_ISSUE_STATUS[body.state], now, card["id"]))
        label = {"under_review": "検討中にしました", "adopted": "採用しました", "declined": "見送りました"}[body.state]
        text = f"{user['department']}が「{card['title']}」を{label}: {body.reason}"
        link = f"/issues/{card['id']}"
        recipients = {card["author_id"]}
        if card["community_id"]:
            recipients |= {r[0] for r in conn.execute(
                "SELECT user_id FROM community_members WHERE community_id = ?", (card["community_id"],))}
        recipients.discard(user["id"])
        for uid in recipients:
            notify(conn, uid, text, link)
        return public_view(conn, card["id"])
