"""課題カード (F-06 / F-07) と AI 提案の判断 (F-21)."""
from __future__ import annotations

import json
import re
import time
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import llm, proposals
from ..agents import issue_card
from ..db import get_conn
from ..deps import current_user
from ..domain import FOCUS_AREAS, ISSUE_STATUS_LABELS, MAX_KPIS, NO_FOCUS_AREA

router = APIRouter()

OriginKind = Literal["news", "conversation", "thread", "manual"]


class DraftRequest(BaseModel):
    origin_kind: Literal["news", "conversation", "thread"]
    origin_ref: int
    # An issue candidate of the thread's AI summary (F-05) to start the draft from.
    summary_proposal_id: Optional[int] = None
    candidate_index: Optional[int] = None


def speaker_label(role: str, attribute: str, department: str) -> str:
    """Who spoke, without the person's name (F-17): the AI sees the stance only."""
    if role == "staff":
        return f"区職員（{department}）" if department else "区職員"
    if role == "community_manager":
        return "コミュニティ運営"
    return {"resident": "住民", "visitor": "来訪者", "business": "事業者"}.get(attribute, "参加者")


def thread_posts_for_ai(conn, thread_id: int) -> list:
    rows = conn.execute(
        "SELECT p.id, p.text, u.role, u.attribute, u.department FROM posts p JOIN users u ON u.id = p.user_id"
        " WHERE thread_id = ? ORDER BY p.id", (thread_id,)).fetchall()
    return [{"id": r["id"], "speaker": speaker_label(r["role"], r["attribute"], r["department"]),
             "text": redact_personal_info(r["text"])} for r in rows]


def origin_context(conn, kind: str, ref: int, user_id: int) -> tuple[str, list]:
    """Build the agent context and the evidence references for an origin."""
    if kind == "news":
        n = conn.execute("SELECT * FROM news WHERE id = ?", (ref,)).fetchone()
        if n is None:
            raise HTTPException(404, "記事が見つかりません")
        return f"[ニュース記事] {n['title']}\n{n['body']}", [{"kind": "news", "ref": f"news:{ref}", "label": n["title"]}]
    if kind == "conversation":
        c = conn.execute("SELECT * FROM conversations WHERE id = ? AND user_id = ?", (ref, user_id)).fetchone()
        if c is None:
            raise HTTPException(404, "会話が見つかりません")
        parts, ev = [], [{"kind": "conversation", "ref": f"conversation:{ref}", "label": "AI との対話"}]
        if c["news_id"] is not None:
            n = conn.execute("SELECT * FROM news WHERE id = ?", (c["news_id"],)).fetchone()
            parts.append(f"[ニュース記事] {n['title']}\n{n['body']}")
            ev.append({"kind": "news", "ref": f"news:{n['id']}", "label": n["title"]})
        for m in conn.execute("SELECT * FROM messages WHERE conversation_id = ? AND ai_status = 'ok' ORDER BY id", (ref,)):
            parts.append(f"[{'利用者' if m['speaker'] == 'user' else 'AI'}] {m['text']}")
        if not any(p.startswith("[利用者]") for p in parts):
            raise HTTPException(422, "まだ利用者の発言がありません")
        return "\n\n".join(parts), ev
    t = conn.execute("SELECT * FROM threads WHERE id = ?", (ref,)).fetchone()
    if t is None:
        raise HTTPException(404, "スレッドが見つかりません")
    body = "\n".join(f"[発言{i}: {p['speaker']}] {p['text']}" for i, p in enumerate(thread_posts_for_ai(conn, ref), start=1))
    return f"[スレッド] {t['title']}\n{body}", [{"kind": "thread", "ref": f"thread:{ref}", "label": t["title"]}]


def candidate_context(conn, req: DraftRequest) -> tuple[str, list, list]:
    """The chosen issue candidate of a thread summary, as extra context, proposal evidence,
    and the cited posts as card evidence (taken from the thread itself, not from the AI)."""
    if req.summary_proposal_id is None:
        return "", [], []
    prop = proposals.load(conn, req.summary_proposal_id, "thread_summary")
    if req.origin_kind != "thread" or prop["target_ref"] != f"thread:{req.origin_ref}":
        raise HTTPException(422, "このスレッドの課題候補ではありません")
    if prop["status"] == "rejected":
        raise HTTPException(409, "この課題候補は却下されています")
    cands = json.loads(prop["payload"])["issue_candidates"]
    if req.candidate_index is None or not 0 <= req.candidate_index < len(cands):
        raise HTTPException(422, "課題候補が見つかりません")
    c = cands[req.candidate_index]
    nums = "・".join(f"発言{n}" for n in c["post_numbers"])
    text = (f"[コミュニティで提示された課題候補（AI の提案）] {c['title']}\n対象: {c['target']}\n"
            f"理由: {c['reason']}\n根拠: {nums}\nこの候補を中心に下書きを作ること。")
    posts = thread_posts_for_ai(conn, req.origin_ref)
    quoted = [{"kind": "thread", "text": f"スレッドの発言{n}（{posts[n - 1]['speaker']}）", "quote": posts[n - 1]["text"]}
              for n in c["post_numbers"] if n <= len(posts)]
    return text, [{"kind": "thread_summary", "ref": f"ai_proposal:{prop['id']}#candidate:{req.candidate_index}",
                   "label": f"AI の課題候補: {c['title']}"}], quoted


@router.post("/issue-drafts", status_code=201)
def create_draft(req: DraftRequest, user: dict = Depends(current_user)):
    with get_conn() as conn:
        context, evidence = origin_context(conn, req.origin_kind, req.origin_ref, user["id"])
        extra, extra_ev, quoted = candidate_context(conn, req)
        if extra:
            context, evidence = f"{context}\n\n{extra}", evidence + extra_ev
    try:
        draft = issue_card.draft(context)
    except llm.LLMUnavailable as exc:
        raise HTTPException(503, {"code": "ai_unavailable", "message": str(exc), "evidence": evidence,
                                  "quoted_evidence": quoted}) from exc
    # The posts the candidate cites become the card's first evidence, verbatim (P-3).
    draft["evidence"] = quoted + [e for e in draft["evidence"] if e["quote"] not in {q["quote"] for q in quoted}]
    with get_conn() as conn:
        pid = proposals.create(conn, kind="issue_card_draft", target_ref=f"{req.origin_kind}:{req.origin_ref}",
                               payload=draft, evidence=evidence, user_id=user["id"])
        return proposals.to_out(proposals.load(conn, pid))


@router.get("/ai-proposals/{proposal_id}")
def get_proposal(proposal_id: int, user: dict = Depends(current_user)):
    with get_conn() as conn:
        return proposals.to_out(proposals.load(conn, proposal_id))


@router.post("/ai-proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: int, user: dict = Depends(current_user)):
    with get_conn() as conn:
        row = proposals.load(conn, proposal_id)
        proposals.require_open(row)
        proposals.decide(conn, proposal_id, "rejected", user["id"])
        return proposals.to_out(proposals.load(conn, proposal_id))


class EvidenceIn(BaseModel):
    kind: Literal["news", "conversation", "observation", "thread", "data"]
    text: str = Field(max_length=1000)
    quote: str = Field(default="", max_length=1000)


class KpiIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    unit: str = Field(default="", max_length=30)
    measurement: str = Field(default="", max_length=300)
    data_availability: Literal["open_data", "survey_needed", "unknown"] = "unknown"


class IssueCardCreate(BaseModel):
    proposal_id: Optional[int] = None
    title: str = Field(min_length=1, max_length=120)
    target: str = Field(default="", max_length=100)
    place_time: str = Field(default="", max_length=100)
    evidence: List[EvidenceIn] = Field(default_factory=list, max_length=20)
    focus_area: str = ""
    focus_reason: str = Field(default="", max_length=500)
    kpis: List[KpiIn] = Field(default_factory=list)
    origin_kind: OriginKind = "manual"
    origin_ref: str = ""
    community_id: Optional[int] = None
    visibility: Literal["private", "community", "public"] = "public"
    acknowledge_personal_info: bool = False


PII_PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "メールアドレス"),
    (re.compile(r"0\d{1,4}-?\d{1,4}-?\d{3,4}"), "電話番号"),
]


def redact_personal_info(text: str) -> str:
    """Mask contact details before a post leaves for the LLM (F-17)."""
    for pat, label in PII_PATTERNS:
        text = pat.sub(f"［{label}は伏せました］", text)
    return text


def personal_info_warnings(*texts: str) -> List[str]:
    found = []
    for pat, label in PII_PATTERNS:
        if any(pat.search(t or "") for t in texts):
            found.append(label)
    return found


def _kpi_key(k: dict) -> tuple:
    return (k["name"], k["unit"], k["measurement"], k["data_availability"])


@router.post("/issue-cards", status_code=201)
def create_issue_card(body: IssueCardCreate, user: dict = Depends(current_user)):
    if len(body.kpis) > MAX_KPIS:
        raise HTTPException(422, f"KPI は最大 {MAX_KPIS} 件まで選べます")
    if body.focus_area and body.focus_area not in FOCUS_AREAS and body.focus_area != NO_FOCUS_AREA:
        raise HTTPException(422, "未知の注力分野です")
    if body.visibility != "private" and not body.acknowledge_personal_info:
        found = personal_info_warnings(body.title, body.target, body.place_time,
                                       *[e.text + e.quote for e in body.evidence])
        if found:
            raise HTTPException(422, {"code": "personal_info", "message": f"公開前に確認してください: {'・'.join(found)} が含まれている可能性があります", "found": found})
    now = time.time()
    with get_conn() as conn:
        if body.community_id is not None and conn.execute(
                "SELECT 1 FROM communities WHERE id = ?", (body.community_id,)).fetchone() is None:
            raise HTTPException(422, "コミュニティが見つかりません")
        decision = None
        if body.proposal_id is not None:
            prop = proposals.load(conn, body.proposal_id, "issue_card_draft")
            proposals.require_open(prop)
            draft = json.loads(prop["payload"])
            chosen_from_candidates = all(_kpi_key(k.model_dump()) in {_kpi_key(c) for c in draft["kpi_candidates"]} for k in body.kpis)
            unchanged = (
                body.title == draft["title"] and body.target == draft["target"] and body.place_time == draft["place_time"]
                and body.focus_area == draft["focus_area"] and body.focus_reason == draft["focus_reason"]
                and [e.model_dump(include={"kind", "text", "quote"}) for e in body.evidence] == draft["evidence"]
                and chosen_from_candidates
            )
            decision = "adopted" if unchanged else "adopted_edited"
        cur = conn.execute(
            "INSERT INTO issue_cards (title, target, place_time, evidence, focus_area, focus_reason, origin_kind,"
            " origin_ref, community_id, author_id, proposal_id, visibility, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (body.title, body.target, body.place_time,
             json.dumps([e.model_dump() for e in body.evidence], ensure_ascii=False),
             body.focus_area, body.focus_reason, body.origin_kind, body.origin_ref, body.community_id,
             user["id"], body.proposal_id, body.visibility,
             "draft" if body.visibility == "private" else "published", now, now),
        )
        card_id = int(cur.lastrowid)
        if body.community_id is not None:
            # The author follows the community the card belongs to, so its replies and the
            # district's decisions reach them (F-15).
            conn.execute("INSERT OR IGNORE INTO community_members (community_id, user_id, joined_at) VALUES (?,?,?)",
                         (body.community_id, user["id"], now))
        for i, k in enumerate(body.kpis):
            conn.execute(
                "INSERT INTO kpis (issue_card_id, name, unit, measurement, data_availability, position) VALUES (?,?,?,?,?,?)",
                (card_id, k.name, k.unit, k.measurement, k.data_availability, i))
        if decision:
            proposals.decide(conn, body.proposal_id, decision, user["id"], result_ref=f"issue_card:{card_id}")
            _adopt_thread_candidate(conn, json.loads(prop["evidence"]), card_id, user["id"])
        return card_out(conn, card_id, user)


def _adopt_thread_candidate(conn, evidence: list, card_id: int, user_id: int) -> None:
    """Saving a card drafted from a thread's issue candidate is the person's adoption of
    that candidate, so the thread summary proposal is recorded as adopted (F-05 / F-21)."""
    for e in evidence:
        m = re.fullmatch(r"ai_proposal:(\d+)#candidate:(\d+)", e.get("ref", "")) if e.get("kind") == "thread_summary" else None
        if m:
            summary = proposals.load(conn, int(m.group(1)), "thread_summary")
            if summary["status"] == "proposed":
                proposals.decide(conn, summary["id"], "adopted", user_id,
                                 result_ref=f"issue_card:{card_id}#candidate:{m.group(2)}")


def card_out(conn, card_id: int, viewer: Optional[dict]) -> dict:
    c = conn.execute(
        "SELECT ic.*, u.display_name AS author_name, u.attribute AS author_attribute FROM issue_cards ic"
        " JOIN users u ON u.id = ic.author_id WHERE ic.id = ?", (card_id,)).fetchone()
    if c is None:
        raise HTTPException(404, "課題カードが見つかりません")
    if c["visibility"] == "private" and (viewer is None or viewer["id"] != c["author_id"]):
        raise HTTPException(404, "課題カードが見つかりません")
    kpis = conn.execute("SELECT * FROM kpis WHERE issue_card_id = ? ORDER BY position", (card_id,)).fetchall()
    dash = conn.execute("SELECT * FROM dashboards WHERE issue_card_id = ?", (card_id,)).fetchone()
    prop = conn.execute("SELECT id, status, model, decided_at FROM ai_proposals WHERE id = ?", (c["proposal_id"],)).fetchone() if c["proposal_id"] else None
    out = {k: c[k] for k in c.keys()}
    out["evidence"] = json.loads(c["evidence"])
    out["status_label"] = ISSUE_STATUS_LABELS[c["status"]]
    out["focus_area_label"] = FOCUS_AREAS.get(c["focus_area"], "どの注力分野にも当てはまらない" if c["focus_area"] == NO_FOCUS_AREA else "")
    out["kpis"] = []
    for k in kpis:
        pts = conn.execute("SELECT period, value FROM kpi_points WHERE kpi_id = ? ORDER BY period", (k["id"],)).fetchall()
        ds = conn.execute("SELECT * FROM datasets WHERE id = ?", (k["dataset_id"],)).fetchone() if k["dataset_id"] else None
        out["kpis"].append({**{x: k[x] for x in k.keys()},
                            "points": [dict(p) for p in pts],
                            "dataset": ({**dict(ds), "is_sample": bool(ds["is_sample"])} if ds else None)})
    out["dashboard"] = dict(dash) if dash else None
    out["origin_proposal"] = dict(prop) if prop else None
    decision = None
    if dash:
        d = conn.execute(
            "SELECT ad.*, u.display_name AS decided_by_name FROM adoption_decisions ad JOIN users u ON u.id = ad.decided_by"
            " WHERE dashboard_id = ? ORDER BY ad.id DESC LIMIT 1", (dash["id"],)).fetchone()
        decision = dict(d) if d else None
    out["latest_decision"] = decision
    out["policy_news"] = [dict(n) for n in conn.execute(
        "SELECT id, title, published_at, department FROM news WHERE kind = 'policy' AND issue_card_id = ? ORDER BY id DESC",
        (card_id,))]
    out["community"] = (dict(conn.execute("SELECT id, name FROM communities WHERE id = ?", (c["community_id"],)).fetchone())
                        if c["community_id"] else None)
    out["origin"] = _origin_out(conn, c, viewer)
    return out


def _origin_out(conn, c, viewer: Optional[dict]) -> Optional[dict]:
    """Where the card came from, so readers can go back to it (UXR-12). A conversation is
    private to its author; others only see that the card started from one."""
    kind, ref = c["origin_kind"], c["origin_ref"]
    if not ref or not ref.isdigit():
        return None
    if kind == "thread":
        t = conn.execute("SELECT id, title, community_id FROM threads WHERE id = ?", (int(ref),)).fetchone()
        return {"kind": "thread", "label": t["title"], "path": f"/community/{t['community_id']}?thread={t['id']}"} if t else None
    if kind == "news":
        n = conn.execute("SELECT id, title FROM news WHERE id = ?", (int(ref),)).fetchone()
        return {"kind": "news", "label": n["title"], "path": f"/news/{n['id']}"} if n else None
    if kind == "conversation":
        conv = conn.execute("SELECT news_id FROM conversations WHERE id = ?", (int(ref),)).fetchone()
        own = viewer is not None and viewer["id"] == c["author_id"]
        path = f"/news/{conv['news_id']}" if conv and conv["news_id"] and own else ""
        return {"kind": "conversation", "label": "作成者と AI の対話", "path": path}
    return None


@router.get("/issue-cards")
def list_issue_cards(user: dict = Depends(current_user)):
    with get_conn() as conn:
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM issue_cards WHERE visibility != 'private' OR author_id = ? ORDER BY updated_at DESC", (user["id"],))]
        return {"items": [card_out(conn, i, user) for i in ids]}


@router.get("/issue-cards/{card_id}")
def get_issue_card(card_id: int, user: dict = Depends(current_user)):
    with get_conn() as conn:
        return card_out(conn, card_id, user)


@router.get("/focus-areas")
def focus_areas():
    return {"items": [{"key": k, "label": v} for k, v in FOCUS_AREAS.items()], "max_kpis": MAX_KPIS}
