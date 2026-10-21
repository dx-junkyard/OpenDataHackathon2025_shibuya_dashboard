"""OpenData 検索 Agent (F-08): ranks registered datasets for one KPI.

The catalog is the set of datasets registered in this system. The agent only
ranks and explains; it may return zero candidates, which the UI reports as
"見つからなかった" together with the searched scope.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .. import llm
from ..observe import observed

def _catalog_prompt(kpi: Dict[str, Any], catalog: List[Dict[str, Any]]) -> str:
    lines = [f"KPI: {kpi['name']}（単位: {kpi['unit']}、測り方: {kpi['measurement']}）", "", "データセット一覧:"]
    for d in catalog:
        lines.append(f"- id={d['id']} {d['title']} / 提供: {d['publisher']} / {d['description']} / 粒度: {d['granularity']} / タグ: {d['tags']}")
    return "\n".join(lines)


def _known(out: Dict[str, Any], catalog: List[Dict[str, Any]]) -> Dict[str, Any]:
    known = {d["id"] for d in catalog}
    out["candidates"] = [c for c in out["candidates"] if c["dataset_id"] in known][:5]
    return out


SYSTEM = """あなたはオープンデータの検索を手伝います。KPI と、登録済みデータセットの一覧が与えられます。
- 各データセットについて、KPI をそのデータで直接測れるか（direct）、間接的な手がかりにしかならないか（indirect）を判定し、関係するものだけを関連が強い順に最大 5 件返します。無関係なものは返しません。
- dataset_id は一覧にある値だけを使います。"""

SCHEMA = llm.obj(
    {
        "candidates": {
            "type": "array",
            "items": llm.obj({"dataset_id": {"type": "integer"}, "relevance": llm.enum(["direct", "indirect"]), "reason": llm.STR}),
        }
    }
)


@observed("opendata-search-agent")
def search(kpi: Dict[str, Any], catalog: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Only datasets that measure the KPI directly are proposed.

    Adopted from the v2 candidate after probe-agent shadow comparison (System 6,
    shadow results 1/5/9/13: v2 dropped unrelated datasets in all 4 cases).

    probe-agent:
      role: KPI候補に関連するオープンデータ探索を行うエージェント入口
      capability: F-08 オープンデータ検索（KPI に関連するデータセットを探す）
      system_purpose: 課題カードに対応するKPI候補とデータ根拠を見つけ、追跡ダッシュボード公開の材料を揃える
      probe_value: KPI選定から公開までの不足していた詳細フローのうち、データ検索段階の実装接点として重要
      element_type: capability
      operation_kind: analysis
      consumers: [apps.api.app.routes.data.search_datasets, apps.api.app.routes.data.propose_shaping]
      state_effects: [external-api]
    """
    out = llm.complete_json(SYSTEM, _catalog_prompt(kpi, catalog), SCHEMA, "dataset_candidates")
    out["candidates"] = [{"dataset_id": c["dataset_id"], "reason": c["reason"]} for c in out["candidates"] if c["relevance"] == "direct"]
    return _known(out, catalog)
