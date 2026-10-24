"""Re-run adopted shaping plans when a dataset gets a new snapshot (運用: データの版の更新).

The KPI keeps its previous points if the new version cannot be shaped (columns
renamed, table empty): the card then says the latest version failed to apply,
instead of silently showing old values as current (UXR-X5).
"""
from __future__ import annotations

import json

from . import kpi_targets
from .agents import shaping


def _require_columns(latest_rows: list, plan: dict) -> None:
    """The newest version must still have the columns the plan uses; otherwise its rows
    would be dropped silently and the KPI would look current while missing that version."""
    if not latest_rows:
        return
    have = set(latest_rows[0])
    used = [plan.get(c) for c in ("date_column", "value_column", "filter_column")] + list(plan.get("unpivot_columns") or [])
    missing = [c for c in used if c and c not in have]
    if missing:
        raise shaping.ShapingError(f"列「{'」「'.join(missing)}」が見つかりません（列名が変わった可能性があります）")


def refresh_dataset(conn, dataset_id: int) -> list:
    """
    probe-agent:
      role: データセットの新しい版が取り込まれたとき、採用済みの整形手順で KPI の値を計算し直す関数
      capability: F-08 データの版の更新と KPI への反映（運用）
      system_purpose: ダッシュボードの値を最新の公開データに追従させ、反映できなかったことも隠さない（UXR-X5）
      probe_value: 版の更新ごとに、更新・変化なし・失敗の KPI 件数と失敗理由を観測できる
      element_type: supporting
      operation_kind: write
      consumers: [apps.api.app.ingest.opendata.store]
      state_effects: [database-write]
    """
    from .routes.dashboards import notify
    from .routes.data import _plan_rows, _snapshots

    ds = conn.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
    snaps = _snapshots(ds, conn)
    as_of = snaps[-1]["as_of"] if snaps else ds["updated_on"]
    results = []
    for k in conn.execute("SELECT k.*, ic.author_id FROM kpis k JOIN issue_cards ic ON ic.id = k.issue_card_id"
                          " WHERE k.dataset_id = ? AND k.shaping_plan IS NOT NULL", (dataset_id,)).fetchall():
        link = f"/issues/{k['issue_card_id']}"
        plan = json.loads(k["shaping_plan"])
        try:
            _require_columns(_plan_rows(ds, snaps[-1:], plan) if snaps else [], plan)
            points = shaping.apply_plan(_plan_rows(ds, snaps, plan), plan)
            if not points:
                raise shaping.ShapingError("整形の結果が 0 件でした")
        except (shaping.ShapingError, OSError) as exc:
            message = f"{as_of} 時点のデータを反映できませんでした: {exc}"
            if k["refresh_error"] != message:
                conn.execute("UPDATE kpis SET refresh_error = ? WHERE id = ?", (message, k["id"]))
                notify(conn, k["author_id"], f"KPI「{k['name']}」: {message}。表示は前回の値のままです", link)
            results.append({"kpi_id": k["id"], "status": "failed", "message": str(exc)})
            continue
        old = [(r["period"], r["value"]) for r in conn.execute(
            "SELECT period, value FROM kpi_points WHERE kpi_id = ? ORDER BY period", (k["id"],))]
        proposal = conn.execute("SELECT proposal_id FROM kpi_points WHERE kpi_id = ? LIMIT 1", (k["id"],)).fetchone()
        conn.execute("DELETE FROM kpi_points WHERE kpi_id = ?", (k["id"],))
        for p in points:
            conn.execute("INSERT INTO kpi_points (kpi_id, period, value, proposal_id) VALUES (?,?,?,?)",
                         (k["id"], p["period"], p["value"], proposal["proposal_id"] if proposal else None))
        conn.execute("UPDATE kpis SET data_as_of = ?, refresh_error = '' WHERE id = ?", (as_of, k["id"]))
        changed = old != [(p["period"], p["value"]) for p in points]
        if changed:
            notify(conn, k["author_id"], f"KPI「{k['name']}」のデータを {as_of} 時点の版に更新しました", link)
        kpi_targets.check(conn, k["id"])
        results.append({"kpi_id": k["id"], "status": "updated" if changed else "unchanged"})
    return results
