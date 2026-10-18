"""AI 提案の共通パターン (docs/features.md F-21).

An AI output becomes an `ai_proposals` row in status `proposed`. Only an
explicit human decision moves it to `adopted` / `adopted_edited` /
`rejected`, and only adoption may create a formal entity. Decisions are
recorded with `decision_method='manual'`, the deciding user and the time.
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, Optional

from fastapi import HTTPException

from . import llm

DECISIONS = ("adopted", "adopted_edited", "rejected")


def create(conn: sqlite3.Connection, *, kind: str, target_ref: str, payload: Dict[str, Any],
           evidence: list, user_id: int) -> int:
    cur = conn.execute(
        "INSERT INTO ai_proposals (kind, target_ref, payload, evidence, model, created_by, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (kind, target_ref, json.dumps(payload, ensure_ascii=False), json.dumps(evidence, ensure_ascii=False),
         llm.model_name(), user_id, time.time()),
    )
    return int(cur.lastrowid)


def load(conn: sqlite3.Connection, proposal_id: int, kind: Optional[str] = None) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM ai_proposals WHERE id = ?", (proposal_id,)).fetchone()
    if row is None or (kind and row["kind"] != kind):
        raise HTTPException(404, "AI の提案が見つかりません")
    return row


def require_open(row: sqlite3.Row) -> None:
    if row["status"] != "proposed":
        raise HTTPException(409, "この AI の提案はすでに判断済みです")


def decide(conn: sqlite3.Connection, proposal_id: int, decision: str, user_id: int, result_ref: str = "") -> None:
    if decision not in DECISIONS:
        raise HTTPException(422, "未知の判断です")
    cur = conn.execute(
        "UPDATE ai_proposals SET status = ?, decided_by = ?, decided_at = ?, decision_method = 'manual',"
        " result_ref = ? WHERE id = ? AND status = 'proposed'",
        (decision, user_id, time.time(), result_ref, proposal_id),
    )
    if cur.rowcount != 1:
        raise HTTPException(409, "この AI の提案はすでに判断済みです")


def to_out(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "target_ref": row["target_ref"],
        "payload": json.loads(row["payload"]),
        "evidence": json.loads(row["evidence"]),
        "status": row["status"],
        "model": row["model"],
        "created_at": row["created_at"],
        "decided_by": row["decided_by"],
        "decided_at": row["decided_at"],
        "decision_method": row["decision_method"],
        "result_ref": row["result_ref"],
    }
