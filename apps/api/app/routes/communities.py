"""コミュニティ (F-04)、関心からの推薦 (F-03)、マイページと通知 (F-15)、利用者 (F-19)."""
from __future__ import annotations

import json
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import llm, proposals
from ..agents import recommend
from ..db import get_conn
from ..deps import current_user
from ..domain import FOCUS_AREAS, ISSUE_STATUS_LABELS
from .issues import card_out

router = APIRouter()


def community_out(conn, row, user_id: int) -> dict:
    members = conn.execute("SELECT COUNT(*) FROM community_members WHERE community_id = ?", (row["id"],)).fetchone()[0]
    joined = conn.execute("SELECT 1 FROM community_members WHERE community_id = ? AND user_id = ?",
                          (row["id"], user_id)).fetchone() is not None
    return {**dict(row), "member_count": members, "joined": joined,
            "focus_area_label": FOCUS_AREAS.get(row["focus_area"], "")}


@router.get("/communities")
def list_communities(q: Optional[str] = None, focus_area: Optional[str] = None, user: dict = Depends(current_user)):
    sql, args = "SELECT * FROM communities WHERE 1=1", []
    if q:
        sql += " AND (name LIKE ? OR description LIKE ? OR category LIKE ? OR area LIKE ?)"
        args += [f"%{q}%"] * 4
    if focus_area:
        sql += " AND focus_area = ?"
        args.append(focus_area)
    with get_conn() as conn:
        return {"items": [community_out(conn, r, user["id"]) for r in conn.execute(sql + " ORDER BY id", args)]}


class CommunityIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=300)
    category: str = Field(default="", max_length=20)
    focus_area: str = ""
    area: str = Field(default="", max_length=40)


@router.post("/communities", status_code=201)
def create_community(body: CommunityIn, user: dict = Depends(current_user)):
    if body.focus_area and body.focus_area not in FOCUS_AREAS:
        raise HTTPException(422, "未知の注力分野です")
    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM communities WHERE name = ?", (body.name.strip(),)).fetchone():
            raise HTTPException(409, "同じ名前のコミュニティがあります。参加してください")
        now = time.time()
        cur = conn.execute(
            "INSERT INTO communities (name, description, category, focus_area, area, created_by) VALUES (?,?,?,?,?,?)",
            (body.name.strip(), body.description, body.category, body.focus_area, body.area, user["id"]))
        conn.execute("INSERT INTO community_members (community_id, user_id, joined_at) VALUES (?,?,?)",
                     (cur.lastrowid, user["id"], now))
    return get_community(int(cur.lastrowid), user)


@router.get("/issue-cards/{card_id}/community-candidates")
def community_candidates(card_id: int, user: dict = Depends(current_user)):
    """Communities to link an issue card to: the AI recommendation made in the
    card's origin conversation (an AI proposal, F-03 / F-21), plus rule-based
    matches on the origin thread and the focus area."""
    with get_conn() as conn:
        card = card_out(conn, card_id, user)
        names = {r["id"]: r for r in conn.execute("SELECT * FROM communities ORDER BY id")}
        ai = None
        if card["origin_kind"] == "conversation" and card["origin_ref"]:
            p = conn.execute("SELECT * FROM ai_proposals WHERE kind = 'recommendation' AND target_ref = ? AND created_by = ?"
                             " ORDER BY id DESC LIMIT 1", (f"conversation:{card['origin_ref']}", card["author_id"])).fetchone()
            if p:
                out = proposals.to_out(p)
                ai = {"id": out["id"], "status": out["status"], "model": out["model"],
                      "items": [c for c in out["payload"]["communities"] if c["id"] in names]}
        matches = []
        if card["origin_kind"] == "thread" and card["origin_ref"]:
            t = conn.execute("SELECT community_id FROM threads WHERE id = ?", (card["origin_ref"],)).fetchone()
            if t:
                matches.append({"id": t["community_id"], "name": names[t["community_id"]]["name"], "reason": "元のスレッドのコミュニティ"})
        if card["focus_area"] in FOCUS_AREAS:
            matches += [{"id": r["id"], "name": r["name"], "reason": f"注力分野が同じ（{FOCUS_AREAS[r['focus_area']]}）"}
                        for r in names.values() if r["focus_area"] == card["focus_area"] and r["id"] not in {m["id"] for m in matches}]
        return {"ai_recommendation": ai, "matches": matches,
                "all": [community_out(conn, r, user["id"]) for r in names.values()]}


class CardCommunityIn(BaseModel):
    community_id: Optional[int] = None
    recommendation_proposal_id: Optional[int] = None


@router.put("/issue-cards/{card_id}/community")
def link_card_community(card_id: int, body: CardCommunityIn, user: dict = Depends(current_user)):
    with get_conn() as conn:
        card = card_out(conn, card_id, user)
        if card["author_id"] != user["id"]:
            raise HTTPException(403, "課題カードの作成者だけがコミュニティを選べます")
        now = time.time()
        if body.community_id is not None:
            if conn.execute("SELECT 1 FROM communities WHERE id = ?", (body.community_id,)).fetchone() is None:
                raise HTTPException(404, "コミュニティが見つかりません")
            conn.execute("INSERT OR IGNORE INTO community_members (community_id, user_id, joined_at) VALUES (?,?,?)",
                         (body.community_id, user["id"], now))
        if body.recommendation_proposal_id is not None:
            prop = proposals.load(conn, body.recommendation_proposal_id, "recommendation")
            if body.community_id not in {c["id"] for c in json.loads(prop["payload"])["communities"]}:
                raise HTTPException(422, "AI が推薦したコミュニティではありません")
            # Choosing a recommended community is the person's explicit adoption of the recommendation.
            if prop["status"] == "proposed":
                proposals.decide(conn, prop["id"], "adopted", user["id"],
                                 result_ref=f"issue_card:{card_id}/community:{body.community_id}")
        conn.execute("UPDATE issue_cards SET community_id = ?, updated_at = ? WHERE id = ?", (body.community_id, now, card_id))
        return card_out(conn, card_id, user)


@router.get("/communities/{cid}")
def get_community(cid: int, user: dict = Depends(current_user)):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM communities WHERE id = ?", (cid,)).fetchone()
        if row is None:
            raise HTTPException(404, "コミュニティが見つかりません")
        threads = conn.execute(
            "SELECT t.*, (SELECT COUNT(*) FROM posts p WHERE p.thread_id = t.id) AS post_count FROM threads t"
            " WHERE community_id = ? ORDER BY t.id DESC", (cid,)).fetchall()
        cards = conn.execute("SELECT id, title, status FROM issue_cards WHERE community_id = ? AND visibility != 'private'"
                             " ORDER BY updated_at DESC", (cid,)).fetchall()
        return {**community_out(conn, row, user["id"]), "threads": [dict(t) for t in threads],
                "issue_cards": [dict(c) for c in cards]}


@router.post("/communities/{cid}/join")
def join(cid: int, user: dict = Depends(current_user)):
    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM communities WHERE id = ?", (cid,)).fetchone() is None:
            raise HTTPException(404, "コミュニティが見つかりません")
        conn.execute("INSERT OR IGNORE INTO community_members (community_id, user_id, joined_at) VALUES (?,?,?)",
                     (cid, user["id"], time.time()))
    return get_community(cid, user)


class ThreadIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=2000)


class PostIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


def _require_member(conn, cid: int, user_id: int) -> None:
    if conn.execute("SELECT 1 FROM community_members WHERE community_id = ? AND user_id = ?", (cid, user_id)).fetchone() is None:
        raise HTTPException(403, "コミュニティに参加すると投稿できます")


@router.post("/communities/{cid}/threads", status_code=201)
def create_thread(cid: int, body: ThreadIn, user: dict = Depends(current_user)):
    with get_conn() as conn:
        _require_member(conn, cid, user["id"])
        now = time.time()
        cur = conn.execute("INSERT INTO threads (community_id, title, created_by, created_at) VALUES (?,?,?,?)",
                           (cid, body.title, user["id"], now))
        conn.execute("INSERT INTO posts (thread_id, user_id, text, created_at) VALUES (?,?,?,?)",
                     (cur.lastrowid, user["id"], body.text, now))
    return get_thread(int(cur.lastrowid), user)


@router.get("/threads/{tid}")
def get_thread(tid: int, user: dict = Depends(current_user)):
    with get_conn() as conn:
        t = conn.execute("SELECT * FROM threads WHERE id = ?", (tid,)).fetchone()
        if t is None:
            raise HTTPException(404, "スレッドが見つかりません")
        posts = conn.execute(
            "SELECT p.id, p.text, p.created_at, u.display_name, u.role, u.attribute, u.department FROM posts p"
            " JOIN users u ON u.id = p.user_id WHERE thread_id = ? ORDER BY p.id", (tid,)).fetchall()
        return {**dict(t), "posts": [dict(p) for p in posts]}


@router.post("/threads/{tid}/posts", status_code=201)
def create_post(tid: int, body: PostIn, user: dict = Depends(current_user)):
    with get_conn() as conn:
        t = conn.execute("SELECT * FROM threads WHERE id = ?", (tid,)).fetchone()
        if t is None:
            raise HTTPException(404, "スレッドが見つかりません")
        _require_member(conn, t["community_id"], user["id"])
        conn.execute("INSERT INTO posts (thread_id, user_id, text, created_at) VALUES (?,?,?,?)",
                     (tid, user["id"], body.text, time.time()))
    return get_thread(tid, user)


@router.post("/conversations/{conv_id}/recommendations", status_code=201)
def recommendations(conv_id: int, user: dict = Depends(current_user)):
    with get_conn() as conn:
        c = conn.execute("SELECT * FROM conversations WHERE id = ? AND user_id = ?", (conv_id, user["id"])).fetchone()
        if c is None:
            raise HTTPException(404, "会話が見つかりません")
        msgs = conn.execute("SELECT * FROM messages WHERE conversation_id = ? ORDER BY id", (conv_id,)).fetchall()
        interest = "\n".join(
            [f"利用者: {m['text']}" for m in msgs if m["speaker"] == "user"]
            + [f"整理: {o['text']}" for m in msgs for o in json.loads(m["organization"]) if o["kind"] != "ai_inference"])
        if not interest.strip():
            raise HTTPException(422, "まだ利用者の発言がありません")
        communities = [dict(r) for r in conn.execute("SELECT id, name, description, focus_area FROM communities")]
        cards = [dict(r) for r in conn.execute(
            "SELECT id, title, target, focus_area FROM issue_cards WHERE visibility = 'public'")]
    try:
        result = recommend.recommend(interest, communities, cards)
    except llm.LLMUnavailable as exc:
        raise HTTPException(503, {"code": "ai_unavailable", "message": str(exc)}) from exc
    cname = {c["id"]: c["name"] for c in communities}
    ctitle = {c["id"]: c["title"] for c in cards}
    payload = {
        "communities": [{**x, "name": cname[x["id"]]} for x in result["communities"]],
        "issue_cards": [{**x, "title": ctitle[x["id"]]} for x in result["issue_cards"]],
    }
    with get_conn() as conn:
        pid = proposals.create(conn, kind="recommendation", target_ref=f"conversation:{conv_id}", payload=payload,
                               evidence=[{"kind": "conversation", "ref": f"conversation:{conv_id}", "label": "AI との対話"}],
                               user_id=user["id"])
        return proposals.to_out(proposals.load(conn, pid))


@router.get("/users")
def list_users():
    with get_conn() as conn:
        return {"items": [dict(r) for r in conn.execute("SELECT * FROM users ORDER BY id")]}


@router.get("/me")
def me(user: dict = Depends(current_user)):
    with get_conn() as conn:
        unread = conn.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0", (user["id"],)).fetchone()[0]
        cards = conn.execute("SELECT id, title, status FROM issue_cards WHERE author_id = ? ORDER BY updated_at DESC",
                             (user["id"],)).fetchall()
        joined = conn.execute("SELECT c.id, c.name FROM communities c JOIN community_members m ON m.community_id = c.id"
                              " WHERE m.user_id = ?", (user["id"],)).fetchall()
        policy = {c["id"]: [dict(n) for n in conn.execute(
            "SELECT id, title, published_at FROM news WHERE kind = 'policy' AND issue_card_id = ? ORDER BY id DESC",
            (c["id"],))] for c in cards}
    return {**user, "unread_notifications": unread,
            "issue_cards": [{**dict(c), "status_label": ISSUE_STATUS_LABELS[c["status"]], "policy_news": policy[c["id"]]}
                            for c in cards],
            "communities": [dict(j) for j in joined]}


@router.get("/me/notifications")
def notifications(user: dict = Depends(current_user)):
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC", (user["id"],)).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.post("/me/notifications/{nid}/read")
def read_notification(nid: int, user: dict = Depends(current_user)):
    with get_conn() as conn:
        conn.execute("UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?", (nid, user["id"]))
    return {"ok": True}
