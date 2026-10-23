"""アンケート・現場観測の収集 (F-11).

A KPI that open data cannot measure gets one survey (people's ratings) or
field observation (counts people make on site). The AI only drafts the
question (AI proposal ``survey_draft``); a person saves it, opens it for
answers and closes it.

Privacy (P-6, F-11 acceptance): answers are a rating or a number only, stored
under a salted hash of the respondent, never listed or exported. Each month's
answers become a KPI point only once at least ``min_responses`` people
answered; until then the KPI says "collecting (n of N)" rather than showing a
value from a handful of people (or 0).
"""
from __future__ import annotations

import hashlib
import json
import secrets
import statistics
import time
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import kpi_targets, llm, proposals
from ..agents import survey as survey_agent
from ..db import get_conn
from ..deps import current_user
from .dashboards import notify
from .issues import card_out

router = APIRouter()

MIN_RESPONSES = 5


def _period(ts: float) -> str:
    return time.strftime("%Y-%m", time.localtime(ts))


def _respondent(survey: dict, user_id: int) -> str:
    return hashlib.sha256(f"{survey['salt']}:{user_id}".encode()).hexdigest()


def _kpi_and_card(conn, kpi_id: int, user: dict):
    k = conn.execute("SELECT * FROM kpis WHERE id = ?", (kpi_id,)).fetchone()
    if k is None:
        raise HTTPException(404, "KPI が見つかりません")
    return dict(k), card_out(conn, k["issue_card_id"], user)


def _require_owner(card: dict, user: dict) -> None:
    if card["author_id"] != user["id"]:
        raise HTTPException(403, "課題カードの作成者だけがアンケートを作れます")


def aggregate(conn, survey: dict) -> list:
    """Recompute the KPI's points from the survey's answers, deterministically."""
    rows = conn.execute(
        "SELECT period, value FROM survey_responses WHERE survey_id = ? ORDER BY period", (survey["id"],)).fetchall()
    by_period: dict = {}
    for r in rows:
        by_period.setdefault(r["period"], []).append(r["value"])
    conn.execute("DELETE FROM kpi_points WHERE kpi_id = ?", (survey["kpi_id"],))
    published = []
    for period, values in sorted(by_period.items()):
        if len(values) >= survey["min_responses"]:
            value = round(statistics.fmean(values), 2)
            conn.execute("INSERT INTO kpi_points (kpi_id, period, value, sample_size) VALUES (?,?,?,?)",
                         (survey["kpi_id"], period, value, len(values)))
            published.append({"period": period, "value": value, "sample_size": len(values)})
    conn.execute("UPDATE kpis SET dataset_id = NULL WHERE id = ?", (survey["kpi_id"],))
    kpi_targets.check(conn, survey["kpi_id"])
    return published


def survey_out(conn, s, user: Optional[dict] = None) -> dict:
    s = dict(s)
    now_period = _period(time.time())
    counts = {r["period"]: r["n"] for r in conn.execute(
        "SELECT period, COUNT(*) AS n FROM survey_responses WHERE survey_id = ? GROUP BY period", (s["id"],))}
    answered = False
    if user is not None:
        answered = conn.execute(
            "SELECT 1 FROM survey_responses WHERE survey_id = ? AND respondent = ? AND period = ?",
            (s["id"], _respondent(s, user["id"]), now_period)).fetchone() is not None
    s.pop("salt")
    return {
        **s,
        "current_period": now_period,
        "current_period_responses": counts.get(now_period, 0),
        "total_responses": sum(counts.values()),
        "periods": [{"period": p, "responses": n, "published": n >= s["min_responses"]} for p, n in sorted(counts.items())],
        "answered_this_period": answered,
    }


def survey_for_kpi(conn, kpi_id: int) -> Optional[dict]:
    s = conn.execute("SELECT * FROM surveys WHERE kpi_id = ? ORDER BY id DESC LIMIT 1", (kpi_id,)).fetchone()
    return survey_out(conn, s) if s else None


@router.post("/kpis/{kpi_id}/survey-drafts", status_code=201)
def create_survey_draft(kpi_id: int, user: dict = Depends(current_user)):
    with get_conn() as conn:
        kpi, card = _kpi_and_card(conn, kpi_id, user)
        _require_owner(card, user)
    try:
        draft = survey_agent.draft(kpi, card)
    except llm.LLMUnavailable as exc:
        raise HTTPException(503, {"code": "ai_unavailable", "message": str(exc)}) from exc
    with get_conn() as conn:
        pid = proposals.create(conn, kind="survey_draft", target_ref=f"kpi:{kpi_id}", payload=draft,
                               evidence=[{"kind": "kpi", "ref": f"kpi:{kpi_id}", "label": kpi["name"]}], user_id=user["id"])
        return proposals.to_out(proposals.load(conn, pid))


class SurveyIn(BaseModel):
    proposal_id: Optional[int] = None
    kind: Literal["survey", "observation"] = "survey"
    title: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=300)
    answer_type: Literal["rating5", "number"]
    unit: str = Field(default="", max_length=20)
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    audience: str = Field(default="", max_length=100)


_DRAFT_FIELDS = ("kind", "title", "question", "answer_type", "unit", "min_value", "max_value", "audience")


@router.post("/kpis/{kpi_id}/surveys", status_code=201)
def create_survey(kpi_id: int, body: SurveyIn, user: dict = Depends(current_user)):
    if body.answer_type == "rating5":
        body.min_value, body.max_value = 1, 5
    if body.min_value is not None and body.max_value is not None and body.min_value > body.max_value:
        raise HTTPException(422, "最小値が最大値より大きくなっています")
    from .issues import personal_info_warnings
    found = personal_info_warnings(body.title, body.question, body.audience)
    if found:
        raise HTTPException(422, f"設問に {'・'.join(found)} が含まれています。個人を特定できる情報は尋ねないでください")
    with get_conn() as conn:
        kpi, card = _kpi_and_card(conn, kpi_id, user)
        _require_owner(card, user)
        if conn.execute("SELECT 1 FROM surveys WHERE kpi_id = ? AND status != 'closed'", (kpi_id,)).fetchone():
            raise HTTPException(409, "この KPI には収集中または下書きのアンケートがあります")
        decision = None
        if body.proposal_id is not None:
            prop = proposals.load(conn, body.proposal_id, "survey_draft")
            proposals.require_open(prop)
            if prop["target_ref"] != f"kpi:{kpi_id}":
                raise HTTPException(422, "この KPI の下書きではありません")
            draft = json.loads(prop["payload"])
            unchanged = all(getattr(body, f) == draft.get(f) for f in _DRAFT_FIELDS)
            decision = "adopted" if unchanged else "adopted_edited"
        cur = conn.execute(
            """INSERT INTO surveys (kpi_id, kind, title, question, answer_type, unit, min_value, max_value, audience,
                                    min_responses, salt, proposal_id, created_by, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (kpi_id, body.kind, body.title, body.question, body.answer_type, body.unit, body.min_value, body.max_value,
             body.audience, MIN_RESPONSES, secrets.token_hex(16), body.proposal_id, user["id"], time.time()))
        sid = int(cur.lastrowid)
        if decision:
            proposals.decide(conn, body.proposal_id, decision, user["id"], result_ref=f"survey:{sid}")
        if kpi["data_availability"] != "survey_needed":
            conn.execute("UPDATE kpis SET data_availability = 'survey_needed' WHERE id = ?", (kpi_id,))
        return survey_out(conn, conn.execute("SELECT * FROM surveys WHERE id = ?", (sid,)).fetchone(), user)


def _load(conn, survey_id: int):
    s = conn.execute("SELECT * FROM surveys WHERE id = ?", (survey_id,)).fetchone()
    if s is None:
        raise HTTPException(404, "アンケートが見つかりません")
    return dict(s)


@router.get("/surveys/{survey_id}")
def get_survey(survey_id: int, user: dict = Depends(current_user)):
    with get_conn() as conn:
        s = _load(conn, survey_id)
        card = card_out(conn, conn.execute("SELECT issue_card_id FROM kpis WHERE id = ?", (s["kpi_id"],)).fetchone()[0], user)
        kpi = conn.execute("SELECT name, unit FROM kpis WHERE id = ?", (s["kpi_id"],)).fetchone()
        return {**survey_out(conn, s, user), "issue_card": {"id": card["id"], "title": card["title"]},
                "kpi": {"name": kpi["name"], "unit": kpi["unit"]}, "is_owner": card["author_id"] == user["id"]}


def _set_status(survey_id: int, status: str, user: dict):
    with get_conn() as conn:
        s = _load(conn, survey_id)
        kpi, card = _kpi_and_card(conn, s["kpi_id"], user)
        _require_owner(card, user)
        allowed = {"open": ("draft",), "closed": ("open",)}[status]
        if s["status"] not in allowed:
            raise HTTPException(409, f"いまの状態（{s['status']}）からは変更できません")
        col = "opened_at" if status == "open" else "closed_at"
        conn.execute(f"UPDATE surveys SET status = ?, {col} = ? WHERE id = ?", (status, time.time(), survey_id))
        if status == "open" and card.get("community"):
            for m in conn.execute("SELECT user_id FROM community_members WHERE community_id = ? AND user_id != ?",
                                  (card["community"]["id"], user["id"])):
                notify(conn, m["user_id"], f"アンケート「{s['title']}」への回答をお願いします", f"/surveys/{survey_id}")
        return survey_out(conn, conn.execute("SELECT * FROM surveys WHERE id = ?", (survey_id,)).fetchone(), user)


@router.post("/surveys/{survey_id}/open")
def open_survey(survey_id: int, user: dict = Depends(current_user)):
    return _set_status(survey_id, "open", user)


@router.post("/surveys/{survey_id}/close")
def close_survey(survey_id: int, user: dict = Depends(current_user)):
    return _set_status(survey_id, "closed", user)


class AnswerIn(BaseModel):
    value: float


@router.post("/surveys/{survey_id}/responses", status_code=201)
def answer(survey_id: int, body: AnswerIn, user: dict = Depends(current_user)):
    with get_conn() as conn:
        s = _load(conn, survey_id)
        if s["status"] != "open":
            raise HTTPException(409, "このアンケートは回答を受け付けていません")
        if s["answer_type"] == "rating5" and (body.value not in (1, 2, 3, 4, 5)):
            raise HTTPException(422, "1〜5 のどれかで答えてください")
        if s["min_value"] is not None and body.value < s["min_value"] or s["max_value"] is not None and body.value > s["max_value"]:
            raise HTTPException(422, f"{s['min_value']}〜{s['max_value']} の範囲で答えてください")
        now = time.time()
        # One answer per person per month; answering again replaces it.
        conn.execute(
            """INSERT INTO survey_responses (survey_id, respondent, period, value, created_at) VALUES (?,?,?,?,?)
               ON CONFLICT (survey_id, respondent, period) DO UPDATE SET value = excluded.value, created_at = excluded.created_at""",
            (survey_id, _respondent(s, user["id"]), _period(now), body.value, now))
        aggregate(conn, s)
        return survey_out(conn, conn.execute("SELECT * FROM surveys WHERE id = ?", (survey_id,)).fetchone(), user)
