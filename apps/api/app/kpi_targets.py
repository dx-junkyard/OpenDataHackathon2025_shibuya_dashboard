"""KPI の目標到達の通知 (UXR-23).

Whether a KPI reached its target is decided deterministically from the latest
published value and the target's direction. The first time it is reached the
card author and the community members are told, with the reminder that the
change is not shown to be caused by any measure (P-4). Falling back below the
target clears the mark, so reaching it again notifies again.
"""
from __future__ import annotations

import time
from typing import Optional


def reached(value: Optional[float], target: Optional[float], direction: str) -> bool:
    if value is None or target is None:
        return False
    return value <= target if direction == "decrease" else value >= target


def check(conn, kpi_id: int) -> bool:
    """Update the KPI's reached mark from its latest point; True if newly reached."""
    from .routes.dashboards import notify  # dashboards imports issues, which imports this module lazily

    k = conn.execute("SELECT * FROM kpis WHERE id = ?", (kpi_id,)).fetchone()
    if k is None:
        return False
    last = conn.execute("SELECT period, value FROM kpi_points WHERE kpi_id = ? ORDER BY period DESC LIMIT 1",
                        (kpi_id,)).fetchone()
    is_reached = reached(last["value"] if last else None, k["target_value"], k["target_direction"])
    if not is_reached:
        if k["target_reached_at"] is not None:
            conn.execute("UPDATE kpis SET target_reached_period = NULL, target_reached_at = NULL WHERE id = ?", (kpi_id,))
        return False
    if k["target_reached_at"] is not None:
        return False
    conn.execute("UPDATE kpis SET target_reached_period = ?, target_reached_at = ? WHERE id = ?",
                 (last["period"], time.time(), kpi_id))
    card = conn.execute("SELECT id, title, author_id, community_id FROM issue_cards WHERE id = ?",
                        (k["issue_card_id"],)).fetchone()
    word = "以下" if k["target_direction"] == "decrease" else "以上"
    text = (f"KPI「{k['name']}」が目標（{k['target_value']:g}{k['unit']} {word}）に到達しました（{last['period']}、"
            f"{last['value']:g}{k['unit']}）。施策の効果かどうかは確認されていません。")
    recipients = {card["author_id"]}
    if card["community_id"]:
        recipients |= {r["user_id"] for r in conn.execute(
            "SELECT user_id FROM community_members WHERE community_id = ?", (card["community_id"],))}
    for uid in sorted(recipients):
        notify(conn, uid, text, f"/issues/{card['id']}")
    return True
