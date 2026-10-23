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
    sv = k.get("survey")
    if pts:
        status = "available"
    elif sv and sv["status"] == "open":
        status = "collecting"  # answers are coming in but no month has enough yet
    else:
        status = "not_collected"
    source = None
    if k["dataset"]:
        source = {"title": k["dataset"]["title"], "publisher": k["dataset"]["publisher"],
                  "license": k["dataset"]["license"], "source_url": k["dataset"]["source_url"],
                  "updated_on": k["dataset"]["updated_on"], "is_sample": k["dataset"]["is_sample"], "kind": "dataset"}
    elif sv:
        # Aggregates only: the response count, never an individual answer (F-11).
        source = {"title": sv["title"], "publisher": "現場観測（本システム）" if sv["kind"] == "observation" else "アンケート（本システム）",
                  "license": "", "source_url": "", "updated_on": None, "is_sample": False, "kind": sv["kind"],
                  "total_responses": sv["total_responses"], "min_responses": sv["min_responses"],
                  "current_period_responses": sv["current_period_responses"], "survey_status": sv["status"],
                  "aggregation": sv["aggregation"]}
    return {
        "id": k["id"], "name": k["name"], "unit": k["unit"], "measurement": k["measurement"],
        "target_value": k["target_value"], "current_value": current,
        "target_direction": k.get("target_direction", "increase"),
        # Reached = the latest value is at/over (or at/under) the target; never a claim about cause.
        "target_reached_period": k.get("target_reached_period"),
        "current_period": pts[-1]["period"] if pts else None,
        "data_status": status,
        "trend": trend, "points": pts,
        "source": source,
    }


CAUSALITY_NOTE = ("因果関係は未確認です。注釈の前後で値が変わっていても、施策の効果とは限りません"
                  "（季節・ほかの施策・データの定義変更などでも変わります）。")
ANNOTATION_KINDS = {"policy_start": "施策開始", "event": "イベント", "definition_change": "データ定義の変更"}
SLOPE_WINDOW = 6


def _per_period(values: list) -> Optional[float]:
    return (values[-1] - values[0]) / (len(values) - 1) if len(values) >= 2 else None


def comparisons(kpis: list, annotations: list) -> list:
    """Before/after view for each annotation (F-12). Pure arithmetic on the
    published points; it describes the change and never claims a cause."""
    out = []
    for a in annotations:
        rows = []
        for k in kpis:
            before = [p["value"] for p in k["points"] if p["period"] < a["period"]]
            after = [p["value"] for p in k["points"] if p["period"] >= a["period"]]
            rows.append({
                "kpi_id": k["id"], "name": k["name"], "unit": k["unit"],
                "before_value": before[-1] if before else None,
                "after_value": after[-1] if after else None,
                "after_periods": len(after),
                "before_per_period": _per_period(before[-SLOPE_WINDOW:]),
                "after_per_period": _per_period(before[-1:] + after) if before else _per_period(after),
                "state": "no_data" if not k["points"] else "no_after" if not after else "no_before" if not before else "ok",
            })
        out.append({"annotation_id": a["id"], "period": a["period"], "label": a["label"], "kind": a["kind"], "kpis": rows})
    return out


def public_view(conn, card_id: int) -> dict:
    card = card_out(conn, card_id, None)
    kpis = [kpi_summary(k) for k in card["kpis"]]
    annotations = [{**dict(a), "kind_label": ANNOTATION_KINDS[a["kind"]]} for a in conn.execute(
        "SELECT id, period, label, kind, news_id FROM annotations WHERE dashboard_id = ? ORDER BY period, id",
        (card["dashboard"]["id"],))] if card["dashboard"] else []
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
        "kpis": kpis,
        "dashboard": card["dashboard"],
        "latest_decision": ({k: card["latest_decision"][k] for k in ("state", "reason", "department", "decided_at")}
                            if card["latest_decision"] else None),
        "annotations": annotations,
        "comparisons": comparisons(kpis, annotations),
        "causality_note": CAUSALITY_NOTE,
        "policy_news": card["policy_news"],
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
    """
    probe-agent:
      role: KPI 追跡ダッシュボードを公開し、固定の公開 URL を発行する API ハンドラ（人の明示操作、公開前の個人情報の確認付き）
      capability: F-10 KPI 追跡ダッシュボード生成・公開、F-17 公開範囲・個人情報保護
      system_purpose: 当事者が自分の課題を KPI 付きで公開し、区が採用判断できる材料にする（OBJ-4）
      probe_value: 公開の成否と、個人情報の警告で止まった件数を観測できる
      element_type: core
      operation_kind: write
      consumers: [apps.web.src.pages.Issues.IssueDetail]
      state_effects: [database-write]
    """
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
    """
    probe-agent:
      role: 公開ダッシュボードを誰でも閲覧できる形で返す API ハンドラ（個別の発言・回答・名前は含めない）
      capability: F-10 KPI 追跡ダッシュボード生成・公開、F-17 公開範囲・個人情報保護
      system_purpose: 区民と区職員が同じ KPI の推移と区の判断を見る共有の場を提供する
      probe_value: 公開ダッシュボードの閲覧回数と、未取得・収集中の KPI の割合を観測できる
      element_type: boundary
      operation_kind: read
      consumers: [apps.web.src.pages.Dash.PublicDashboard]
      state_effects: [database-read]
    """
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
    w.writerow(["課題", "KPI", "単位", "期間", "値", "目標値", "出典", "提供者", "ライセンス", "出典URL", "データ更新日",
                "サンプルデータ", "回答数"])
    for k in view["kpis"]:
        s = k["source"] or {}
        if not k["points"]:
            state = "収集中" if k["data_status"] == "collecting" else "未取得"
            w.writerow([view["title"], k["name"], k["unit"], "", state, k["target_value"] or "",
                        s.get("title", ""), s.get("publisher", ""), "", "", "", "", ""])
        for p in k["points"]:
            w.writerow([view["title"], k["name"], k["unit"], p["period"], p["value"], k["target_value"] or "",
                        s.get("title", ""), s.get("publisher", ""), s.get("license", ""), s.get("source_url", ""),
                        s.get("updated_on", "") or "", "はい（架空）" if s.get("is_sample") else "いいえ",
                        p.get("sample_size") if p.get("sample_size") is not None else ""])
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="dashboard-{slug}.csv"'})


class AnnotationIn(BaseModel):
    period: str = Field(min_length=4, max_length=10)
    label: str = Field(min_length=1, max_length=100)
    kind: Literal["policy_start", "event", "definition_change"] = "event"


@router.post("/issue-cards/{card_id}/dashboard/annotations", status_code=201)
def add_annotation(card_id: int, body: AnnotationIn, user: dict = Depends(current_user)):
    """
    probe-agent:
      role: ダッシュボードに注釈（施策開始・イベント・データ定義の変更）を追加する API ハンドラ
      capability: F-12 注釈と施策前後比較
      system_purpose: 施策の前後で KPI を見比べられるようにする（因果は断定しない）
      probe_value: 注釈の種類と、注釈の後にデータが付いた KPI の割合を観測できる
      element_type: boundary
      operation_kind: write
      consumers: [apps.web.src.components.DashboardAnnotations]
      state_effects: [database-write]
    """
    with get_conn() as conn:
        card = card_out(conn, card_id, user)
        if not card["dashboard"]:
            raise HTTPException(422, "ダッシュボードがまだありません")
        if card["author_id"] != user["id"] and user["role"] != "staff":
            raise HTTPException(403, "作成者または区職員だけが注釈を追加できます")
        conn.execute("INSERT INTO annotations (dashboard_id, period, label, kind, created_by, created_at) VALUES (?,?,?,?,?,?)",
                     (card["dashboard"]["id"], body.period, body.label, body.kind, user["id"], time.time()))
        return public_view(conn, card_id)


@router.get("/staff/dashboards")
def staff_list(focus_area: Optional[str] = None, state: Optional[str] = None,
               department: Optional[str] = None, area: Optional[str] = None,
               user: dict = Depends(current_user)):
    """
    probe-agent:
      role: 区職員が公開ダッシュボードを担当課・注力分野・状態で絞り込んで比べる一覧を返す API ハンドラ
      capability: F-13 区職員ビュー（選定・採用判断）
      system_purpose: 区民発のダッシュボードを施策検討の材料として受け取れるようにする（NEED-5）
      probe_value: 職員ビューの利用回数と、絞り込み条件ごとの件数を観測できる
      element_type: boundary
      operation_kind: read
      consumers: [apps.web.src.pages.Dash.Dash]
      state_effects: [database-read]
    """
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
            card = conn.execute("SELECT community_id, origin_kind, origin_ref FROM issue_cards WHERE id = ?",
                                (r["issue_card_id"],)).fetchone()
            community = conn.execute("SELECT area FROM communities WHERE id = ?", (card["community_id"],)).fetchone() \
                if card["community_id"] else None
            departments = _related_departments(conn, card, v)
            if department and department not in departments:
                continue
            places = [v["place_time"] or "", community["area"] if community else ""]
            if area and not any(area in p for p in places):
                continue
            members = conn.execute("SELECT COUNT(*) FROM community_members WHERE community_id = ?",
                                   (card["community_id"],)).fetchone()[0] if card["community_id"] else 0
            items.append({**v, "community_id": card["community_id"], "community_members": members,
                          "departments": sorted(departments), "community_area": community["area"] if community else ""})
        all_departments = sorted({d for (d,) in conn.execute(
            "SELECT DISTINCT department FROM news WHERE department != '' UNION SELECT DISTINCT department FROM users"
            " WHERE role = 'staff' AND department != ''")})
    return {"items": items, "focus_areas": [{"key": k, "label": v} for k, v in FOCUS_AREAS.items()],
            "departments": all_departments}


def _related_departments(conn, card, view: dict) -> set:
    """Departments a dashboard concerns: the one that recorded a decision on it, and
    the one responsible for the news article it started from (UXR-18)."""
    out = set()
    if view["latest_decision"] and view["latest_decision"].get("department"):
        out.add(view["latest_decision"]["department"])
    news_id = None
    if card["origin_kind"] == "news" and (card["origin_ref"] or "").isdigit():
        news_id = int(card["origin_ref"])
    elif card["origin_kind"] == "conversation" and (card["origin_ref"] or "").isdigit():
        row = conn.execute("SELECT news_id FROM conversations WHERE id = ?", (int(card["origin_ref"]),)).fetchone()
        news_id = row["news_id"] if row else None
    if news_id:
        row = conn.execute("SELECT department FROM news WHERE id = ?", (news_id,)).fetchone()
        if row and row["department"]:
            out.add(row["department"])
    return out


class DecisionIn(BaseModel):
    state: Literal["under_review", "adopted", "declined"]
    reason: str = Field(min_length=1, max_length=1000)


@router.post("/dashboards/{dashboard_id}/decisions", status_code=201)
def decide(dashboard_id: int, body: DecisionIn, user: dict = Depends(current_user)):
    """
    probe-agent:
      role: 区職員が検討中・採用・見送りを理由と担当課付きで記録し、課題カードの状態に反映して当事者とコミュニティに通知する API ハンドラ
      capability: F-13 区職員ビュー（選定・採用判断）、F-15 マイページ・進捗追跡・通知
      system_purpose: 区の採用判断をシステム内の状態として残し、つくる → 公開 → 採用の循環を閉じる（MS-5.1）
      probe_value: 判断の種類ごとの件数と、公開から判断までの日数を観測できる
      element_type: core
      operation_kind: write
      consumers: [apps.web.src.pages.Dash.Dash]
      state_effects: [database-write]
    """
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
