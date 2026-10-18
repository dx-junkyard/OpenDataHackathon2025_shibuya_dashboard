"""Request user resolution.

MVP uses a demo user switcher: the client sends `X-User-Id`. Real
authentication is out of the MVP scope (docs/features.md F-19).
"""
from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException

from .db import get_conn


def current_user(x_user_id: Optional[int] = Header(default=None)) -> dict:
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
