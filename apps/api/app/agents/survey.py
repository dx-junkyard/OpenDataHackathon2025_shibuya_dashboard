"""課題解決支援 Agent のアンケート下書き (F-11).

Drafts one question that measures a KPI. Answers are a 5-point rating or a
number only -- no free text -- so a response can never carry a name or a
contact detail and can always be aggregated (P-6).
"""
from __future__ import annotations

from typing import Any, Dict

from .. import llm
from ..observe import observed

SYSTEM = """あなたは渋谷区の課題カードの KPI を測るための、短いアンケートまたは現場観測の設問を下書きします。
- 設問は 1 つ。やさしい日本語で、一度に一つのことだけを尋ねます。誘導的な言い方をしないこと。
- 回答の形式は rating5（1〜5 の 5 段階評価）か number（数値）のどちらか。自由記述は使いません。
- kind は、利用者に感想や経験を尋ねるなら survey、参加者が現地で数えたり観察したりして記録するなら observation。
- number のときは単位と、ありうる最小値・最大値を付けます。rating5 のときは 1 と 5 が何を意味するかを設問に書きます。
- 個人を特定できる情報（氏名・連絡先・住所・詳しい位置）を尋ねないこと。
- audience には回答してほしい人（例: 乳幼児連れで外出する保護者）を書きます。
- reason には、この設問の回答が KPI のどの値になるか（平均を取る等）を書きます。"""

SCHEMA = llm.obj(
    {
        "kind": llm.enum(["survey", "observation"]),
        "title": llm.STR,
        "question": llm.STR,
        "answer_type": llm.enum(["rating5", "number"]),
        "unit": llm.STR,
        "min_value": {"type": ["number", "null"]},
        "max_value": {"type": ["number", "null"]},
        "audience": llm.STR,
        "reason": llm.STR,
    }
)


@observed("survey-draft-agent")
def draft(kpi: Dict[str, Any], card: Dict[str, Any]) -> Dict[str, Any]:
    """
    probe-agent:
      role: 課題カードの KPI を測るアンケート・現場観測の設問を 1 つ下書きする AI エージェント入口（自由記述なし）
      capability: F-11 アンケート・現場観測の収集
      system_purpose: 公開データで測れない KPI を当事者の回答と観測で測れるようにし、仮説検証とダッシュボード化を進める（OBJ-4）
      probe_value: 下書きが自由記述や個人情報を求めていないか、KPI と単位が合っているか、採用・編集された割合を観測できる
      element_type: capability
      operation_kind: analysis
      consumers: [apps.api.app.routes.surveys.create_survey_draft]
      state_effects: [external-api]
    """
    context = "\n".join([
        f"[課題カード] {card['title']}",
        f"対象者: {card.get('target') or '不明'}",
        f"場所・時間帯: {card.get('place_time') or '不明'}",
        f"[KPI] {kpi['name']}（単位: {kpi.get('unit') or 'なし'}）",
        f"測り方の案: {kpi.get('measurement') or '未定'}",
    ])
    out = llm.complete_json(SYSTEM, context, SCHEMA, "survey_draft")
    if out["answer_type"] == "rating5":
        out["min_value"], out["max_value"], out["unit"] = 1, 5, out.get("unit") or "点"
    return out
