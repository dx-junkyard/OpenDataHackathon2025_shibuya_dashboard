"""Request user resolution.

MVP uses a demo user switcher: the client sends `X-User-Id`. Real
authentication is out of the MVP scope (docs/features.md F-19).
"""
from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException

from .db import get_conn


def current_user(x_user_id: Optional[int] = Header(default=None)) -> dict:
    """
    probe-agent:
      role: リクエストの利用者と立場（住民・来訪者・事業者・コミュニティ運営・区職員）を決める依存関数（MVP はデモ用の利用者切替）
      capability: F-19 アカウント・立場（ロール）
      system_purpose: 発言者の立場と区職員の公式な発言を区別し、権限を分ける（UXR-6）
      probe_value: 立場ごとのリクエスト数を観測できる。本番の認証に置き換える境界
      element_type: boundary
      operation_kind: read
      consumers: [apps.api.app.routes]
      state_effects: [database-read]
    """
    if x_user_id is None:
        raise HTTPException(401, "利用者を選んでください")
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (x_user_id,)).fetchone()
    if row is None:
        raise HTTPException(401, "利用者が見つかりません")
    return dict(row)


def require_staff(user: dict) -> None:
    if user["role"] != "staff" or not user["department"]:
        raise HTTPException(403, "区職員のみが行える操作です")
