"""関心からの推薦 (F-03): communities and existing issue cards, each with a reason."""
from __future__ import annotations

from typing import Any, Dict, List

from .. import llm
from ..observe import observed

SYSTEM = """あなたは渋谷区の参加者に、関心に合うコミュニティと既存の課題カードを紹介します。
- 会話の整理（関心・困りごと）と、候補一覧が与えられます。
- 関連が強いものだけを最大 3 件ずつ選び、どの発言・どの注力分野が一致したかを理由に書きます。
- 関連するものが無ければ空の配列にします。id は一覧にある値だけを使います。"""

SCHEMA = llm.obj(
    {
        "communities": {"type": "array", "items": llm.obj({"id": {"type": "integer"}, "reason": llm.STR})},
        "issue_cards": {"type": "array", "items": llm.obj({"id": {"type": "integer"}, "reason": llm.STR})},
    }
)


@observed("recommend-agent")
def recommend(interest: str, communities: List[Dict[str, Any]], cards: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    probe-agent:
      role: 会話で言葉になった関心から、関連するコミュニティと既存の課題カードを理由付きで推薦する AI エージェント入口
      capability: F-03 関心からのコミュニティ・課題推薦
      system_purpose: 一人の関心を、同じ関心を持つ人のコミュニティと既存の課題へつなぎ、深掘りの循環へ入れる
      probe_value: 推薦がコミュニティ一覧にない id を返していないか、推薦が採用された割合を観測できる
      element_type: capability
      operation_kind: analysis
      consumers: [apps.api.app.routes.communities.recommendations]
      state_effects: [external-api]
    """
    lines = ["関心:", interest, "", "コミュニティ:"]
    lines += [f"- id={c['id']} {c['name']} / {c['description']} / 分野: {c['focus_area']}" for c in communities]
    lines += ["", "課題カード:"]
    lines += [f"- id={c['id']} {c['title']} / 対象: {c['target']} / 分野: {c['focus_area']}" for c in cards]
    out = llm.complete_json(SYSTEM, "\n".join(lines), SCHEMA, "recommendation")
    ck = {c["id"] for c in communities}
    ik = {c["id"] for c in cards}
    out["communities"] = [x for x in out["communities"] if x["id"] in ck][:3]
    out["issue_cards"] = [x for x in out["issue_cards"] if x["id"] in ik][:3]
    return out
