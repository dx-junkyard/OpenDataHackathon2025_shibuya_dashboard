"""ニュース (F-01) と記事文脈つき AI 対話 (F-02)."""
from __future__ import annotations

import json
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import llm
from ..agents import chat
from ..db import get_conn
from ..deps import current_user

router = APIRouter()


def news_out(row, conn=None) -> dict:
    out = {k: row[k] for k in row.keys()} | {"is_sample": bool(row["is_sample"])}
    if conn is not None and row["kind"] == "policy" and row["issue_card_id"]:
        # Policy news links back to the issue card and its public dashboard (F-14).
        c = conn.execute(
            "SELECT ic.id, ic.title, ic.status, d.public_slug, d.status AS dashboard_status FROM issue_cards ic"
            " LEFT JOIN dashboards d ON d.issue_card_id = ic.id WHERE ic.id = ? AND ic.visibility != 'private'",
            (row["issue_card_id"],)).fetchone()
        out["issue_card"] = ({"id": c["id"], "title": c["title"],
                              "dashboard_slug": c["public_slug"] if c["dashboard_status"] == "published" else None}
                             if c else None)
    return out


@router.get("/news")
def list_news(category: Optional[str] = None):
    """
    probe-agent:
      role: 区のニュースをカテゴリで絞り込んで一覧にする API ハンドラ（出典・担当課・掲載日・サンプルかどうか付き）
      capability: F-01 ニュース集約・配信
      system_purpose: 区民がニュースを読むところから関心に気づく入口を提供する（OBJ-1）
      probe_value: 一覧の件数・カテゴリの偏り・サンプル記事の混入を観測できる
      element_type: boundary
      operation_kind: read
      consumers: [apps.web.src.pages.News.NewsList]
      state_effects: [database-read]
    """
    q = "SELECT * FROM news"
    args: tuple = ()
    if category:
        q += " WHERE category = ?"
        args = (category,)
    with get_conn() as conn:
        rows = conn.execute(q + " ORDER BY published_at DESC, id DESC", args).fetchall()
        cats = [r[0] for r in conn.execute("SELECT DISTINCT category FROM news ORDER BY category")]
        items = [news_out(r, conn) for r in rows]
    return {"categories": cats, "items": items}


@router.get("/news/{news_id}")
def get_news(news_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM news WHERE id = ?", (news_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "記事が見つかりません")
        return news_out(row, conn)


class ConversationCreate(BaseModel):
    news_id: Optional[int] = None


class MessageCreate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


def conversation_out(conn, conv_id: int) -> dict:
    conv = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
    if conv is None:
        raise HTTPException(404, "会話が見つかりません")
    msgs = conn.execute("SELECT * FROM messages WHERE conversation_id = ? ORDER BY id", (conv_id,)).fetchall()
    return {
        "id": conv["id"],
        "news_id": conv["news_id"],
        "user_id": conv["user_id"],
        "messages": [
            {"id": m["id"], "speaker": m["speaker"], "text": m["text"], "ai_status": m["ai_status"],
             "model": m["model"], "organization": json.loads(m["organization"]), "created_at": m["created_at"]}
            for m in msgs
        ],
        "ai_available": llm.is_configured(),
    }


@router.post("/conversations", status_code=201)
def create_conversation(payload: ConversationCreate, user: dict = Depends(current_user)):
    with get_conn() as conn:
        if payload.news_id is not None and conn.execute("SELECT 1 FROM news WHERE id = ?", (payload.news_id,)).fetchone() is None:
            raise HTTPException(404, "記事が見つかりません")
        cur = conn.execute("INSERT INTO conversations (news_id, user_id, created_at) VALUES (?,?,?)",
                           (payload.news_id, user["id"], time.time()))
        return conversation_out(conn, int(cur.lastrowid))


@router.get("/conversations/{conv_id}")
def get_conversation(conv_id: int, user: dict = Depends(current_user)):
    with get_conn() as conn:
        out = conversation_out(conn, conv_id)
    if out["user_id"] != user["id"]:
        raise HTTPException(404, "会話が見つかりません")
    return out


@router.post("/conversations/{conv_id}/messages", status_code=201)
def post_message(conv_id: int, payload: MessageCreate, user: dict = Depends(current_user)):
    """
    probe-agent:
      role: 記事についての利用者の発言を保存し、雑談 Agent の応答を付ける API ハンドラ。AI が使えないときも発言は保存し、失敗をそのまま返す
      capability: F-02 記事文脈つき AI 対話、F-18 AI 障害時の手動フォールバック
      system_purpose: AI が失敗しても利用者の入力を失わず、手入力の経路へ戻せるようにする（UXR-X2）
      probe_value: AI 応答の成否（ok / unavailable / failed）と所要時間を対話の単位で観測できる
      element_type: core
      operation_kind: orchestration
      consumers: [apps.web.src.pages.News.NewsDetail]
      state_effects: [database-write, external-api]
    """
    with get_conn() as conn:
        conv = conversation_out(conn, conv_id)
        if conv["user_id"] != user["id"]:
            raise HTTPException(404, "会話が見つかりません")
        conn.execute("INSERT INTO messages (conversation_id, speaker, text, created_at) VALUES (?,?,?,?)",
                     (conv_id, "user", payload.text, time.time()))
        article = None
        if conv["news_id"] is not None:
            article = dict(conn.execute("SELECT title, body FROM news WHERE id = ?", (conv["news_id"],)).fetchone())
        history = [{"speaker": m["speaker"], "text": m["text"]} for m in conv["messages"] if m["ai_status"] == "ok"]
        history.append({"speaker": "user", "text": payload.text})
    # The model call runs outside the transaction; the user's message is already saved (F-18).
    try:
        result = chat.respond(article, history)
        row = ("ai", result["reply"], json.dumps(result["organization"], ensure_ascii=False), "ok", llm.model_name())
    except llm.LLMUnavailable as exc:
        status = "unavailable" if not llm.is_configured() else "failed"
        row = ("ai", str(exc), "[]", status, "")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages (conversation_id, speaker, text, organization, ai_status, model, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (conv_id, *row, time.time()),
        )
        return conversation_out(conn, conv_id)
