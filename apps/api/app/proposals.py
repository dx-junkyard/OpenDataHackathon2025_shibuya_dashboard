"""AI 提案の共通パターン (docs/features.md F-21).

An AI output becomes an `ai_proposals` row in status `proposed`. Only an
explicit human decision moves it to `adopted` / `adopted_edited` /
`rejected`, and only adoption may create a formal entity. Decisions are
recorded with `decision_method='manual'`, the deciding user and the time.

probe-agent:
  role: AI 提案の保存・参照・採否の記録を担う共通モジュールで、候補が正式なエンティティへ採用される境界の土台
  capability: AI 提案（ai_proposals）の管理と、人による採用・却下のガバナンス（F-21）
  system_purpose: AI が出した候補を提案のまま保持し、人の明示操作でのみ正式なエンティティへ進める責任分界を支える
  probe_value: スレッド要約などの候補が後続で採用された割合を解釈する共通の境界で、提案の状態の観測点になる
  element_type: boundary
  operation_kind: orchestration
  consumers: [apps.api.app.routes.issues, apps.api.app.routes.communities, apps.api.app.routes.data, apps.api.app.routes.policy]
  state_effects: [database-read, database-write]
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
    """
    probe-agent:
      role: AI提案を共通の提案レコードとして作成する共通パターンの入口（課題カード下書き・データ候補・整形案など全 AI 提案に共通）
      capability: F-21 AI 提案の共通パターン（会話やコミュニティから課題候補・課題カードへ昇格させる）
      system_purpose: AI生成物を正式決定ではなく候補として保持し、人の明示操作に接続する共通基盤を提供する
      probe_value: 全AI候補に共通する承認パターンの起点であり、代表フロー横断の計測点として価値が高い
      element_type: core
      operation_kind: write
      consumers: [apps.api.app.routes.issues.create_draft, apps.api.app.routes.data.propose_shaping]
      state_effects: [database-write]
    """
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
    """
    probe-agent:
      role: 未決または受付中の提案だけを後続操作可能にする状態ガード（課題カード下書き・データ候補・整形案など全 AI 提案に共通）
      capability: F-21 AI 提案の共通パターン（判断済みの提案の再操作を防ぐ）
      system_purpose: 提案ライフサイクルを制御し、重複決定や不正な再操作を防ぐ
      probe_value: 共通承認パターンの状態整合性を補強するため、決定処理の周辺ガードとして観測価値がある
      element_type: supporting
      operation_kind: validation
      consumers: [apps.api.app.proposals.decide]
      state_effects: [none]
    """
    if row["status"] != "proposed":
        raise HTTPException(409, "この AI の提案はすでに判断済みです")


def decide(conn: sqlite3.Connection, proposal_id: int, decision: str, user_id: int, result_ref: str = "") -> None:
    """
    probe-agent:
      role: 提案に対する人手の採用・却下判断を記録する共通決定処理（課題カード下書き・データ候補・整形案など全 AI 提案に共通）
      capability: F-21 AI 提案の共通パターン（人の明示操作だけが採用・却下を記録する）
      system_purpose: AI候補に対する最終判断を人が担うという統治原則を実装し、正式化の責任境界を明確にする
      probe_value: AI候補が正式化される唯一の人手判断境界を捉えられるため、最重要のガードレール計測点になりうる
      element_type: core
      operation_kind: write
      consumers: [apps.api.app.routes.issues.reject_proposal, apps.api.app.routes.issues.create_issue_card]
      state_effects: [database-write]
    """
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
