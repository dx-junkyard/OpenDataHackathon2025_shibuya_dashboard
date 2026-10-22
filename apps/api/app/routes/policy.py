"""施策ニュース化と還流 (F-14).

A staff member who adopted an issue card asks the AI for a policy news draft
(an `ai_proposals` row, F-21) or writes one by hand (F-18). Publishing creates
a `news` row with kind='policy' linked to the card, adds a policy-start
annotation to the dashboard (F-12) and notifies the author and community.
"""
from __future__ import annotations

import json
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import llm, proposals
from ..agents import policy_news
from ..db import get_conn
from ..deps import current_user, require_staff
from .dashboards import notify, public_view
from .issues import card_out

router = APIRouter()

DEFAULT_CATEGORIES = ["子育て", "移動", "安全", "観光", "産業", "福祉", "その他"]
DEFAULT_ANNOTATION_LABEL = "施策開始"


def categories(conn) -> list[str]:
    found = [r[0] for r in conn.execute("SELECT DISTINCT category FROM news WHERE category != '' ORDER BY category")]
    return found + [c for c in DEFAULT_CATEGORIES if c not in found]


def _adopted_card(conn, card_id: int, user: dict) -> dict:
    require_staff(user)
    card = card_out(conn, card_id, user)
    if not card["dashboard"] or card["dashboard"]["status"] != "published":
        raise HTTPException(422, "公開中のダッシュボードがありません")
    if (card["latest_decision"] or {}).get("state") != "adopted":
        raise HTTPException(409, "区が採用した課題だけを施策ニュースにできます")
    return card


def _context(card: dict) -> str:
    kpis = "\n".join(
        f"- {k['name']}: 現在 {k['points'][-1]['value'] if k['points'] else '未取得'}{k['unit']}"
        f"（目標 {k['target_value'] if k['target_value'] is not None else '未設定'}{k['unit']}）"
        for k in card["kpis"])
    # Individual voices stay out of the official article (F-17); only their summary text is passed.
    evidence = "\n".join(f"- {e['text']}" for e in card["evidence"])
    d = card["latest_decision"]
    return (f"[課題カード] {card['title']}\n対象: {card['target']}\n場所・時間帯: {card['place_time']}\n"
            f"注力分野: {card['focus_area_label']}\n根拠:\n{evidence}\n\n[KPI]\n{kpis}\n\n"
            f"[区の判断] {d['department']}が採用: {d['reason']}")


@router.post("/issue-cards/{card_id}/policy-news-drafts", status_code=201)
def create_policy_news_draft(card_id: int, user: dict = Depends(current_user)):
    with get_conn() as conn:
        card = _adopted_card(conn, card_id, user)
        cats = categories(conn)
    try:
        draft = policy_news.draft(_context(card), cats)
    except llm.LLMUnavailable as exc:
        raise HTTPException(503, {"code": "ai_unavailable", "message": str(exc)}) from exc
    evidence = [
        {"kind": "issue_card", "ref": f"issue_card:{card_id}", "label": card["title"]},
        {"kind": "dashboard", "ref": f"dashboard:{card['dashboard']['id']}", "label": "公開ダッシュボード"},
        {"kind": "decision", "ref": f"adoption_decision:{card['latest_decision']['id']}", "label": "区の採用判断"},
    ]
    with get_conn() as conn:
        pid = proposals.create(conn, kind="policy_news_draft", target_ref=f"issue_card:{card_id}",
                               payload=draft, evidence=evidence, user_id=user["id"])
        return proposals.to_out(proposals.load(conn, pid))


class PolicyNewsIn(BaseModel):
    proposal_id: Optional[int] = None
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=4000)
    category: str = Field(min_length=1, max_length=20)
    start_period: str = Field(pattern=r"^\d{4}-\d{2}$")
    annotation_label: str = Field(default=DEFAULT_ANNOTATION_LABEL, min_length=1, max_length=40)


DRAFT_FIELDS = ("title", "body", "category", "annotation_label")


@router.post("/issue-cards/{card_id}/policy-news", status_code=201)
def publish_policy_news(card_id: int, body: PolicyNewsIn, user: dict = Depends(current_user)):
    """
    probe-agent:
      role: 区職員が採用した課題の施策ニュースを配信し、ダッシュボードに施策開始の注釈を付けて関係者に通知する API ハンドラ
      capability: F-14 施策ニュース化と還流
      system_purpose: 施策がニュースとして区民に戻り、次の関心を生む（MS-5.2）
      probe_value: AI 下書きを変えずに配信したか直したかと、配信から閲覧までを観測できる
      element_type: core
      operation_kind: write
      consumers: [apps.web.src.components.PolicyNewsComposer]
      state_effects: [database-write]
    """
    with get_conn() as conn:
        card = _adopted_card(conn, card_id, user)
        decision = None
        if body.proposal_id is not None:
            prop = proposals.load(conn, body.proposal_id, "policy_news_draft")
            if prop["target_ref"] != f"issue_card:{card_id}":
                raise HTTPException(422, "別の課題カードの AI の提案です")
            proposals.require_open(prop)
            draft = json.loads(prop["payload"])
            decision = "adopted" if all(getattr(body, f) == draft[f] for f in DRAFT_FIELDS) else "adopted_edited"
        now = time.time()
        cur = conn.execute(
            "INSERT INTO news (title, body, category, focus_area, department, source_name, is_sample, kind,"
            " issue_card_id, published_at) VALUES (?,?,?,?,?,?,0,'policy',?,?)",
            (body.title, body.body, body.category, card["focus_area"], user["department"],
             "渋谷区 施策ニュース（区職員が確認して配信）", card_id, time.strftime("%Y-%m-%d", time.localtime(now))))
        news_id = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO annotations (dashboard_id, period, label, kind, news_id, created_by, created_at)"
            " VALUES (?,?,?,'policy_start',?,?,?)",
            (card["dashboard"]["id"], body.start_period, body.annotation_label, news_id, user["id"], now))
        if decision:
            proposals.decide(conn, body.proposal_id, decision, user["id"], result_ref=f"news:{news_id}")
        conn.execute("UPDATE issue_cards SET updated_at = ? WHERE id = ?", (now, card_id))
        recipients = {card["author_id"]}
        if card["community_id"]:
            recipients |= {r[0] for r in conn.execute(
                "SELECT user_id FROM community_members WHERE community_id = ?", (card["community_id"],))}
        recipients.discard(user["id"])
        text = f"{user['department']}が「{card['title']}」の施策を始めました: {body.title}"
        for uid in recipients:
            notify(conn, uid, text, f"/news/{news_id}")
        return {"news_id": news_id, "dashboard": public_view(conn, card_id)}
