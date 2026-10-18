"""課題カード作成 Agent (F-06 / F-07): drafts a card, judges focus area, proposes KPIs."""
from __future__ import annotations

from typing import Any, Dict

from .. import llm
from ..domain import FOCUS_AREAS, MAX_KPIS, NO_FOCUS_AREA
from ..observe import observed

AREAS = "\n".join(f"{k}: {v}" for k, v in FOCUS_AREAS.items())

SYSTEM = f"""あなたは渋谷区の課題カード作成を手伝うアシスタントです。与えられた文脈（ニュース記事・利用者との対話・スレッドの発言）から、課題カードの下書きを作ります。
- タイトルは「対象・場所: 困りごと」の形で短く。
- 根拠は文脈に実際にあるものだけ。各根拠に種類（news=記事, conversation=利用者の発言, observation=観測）と、利用者の言葉なら引用を付けます。創作しないこと。
- 渋谷区の 7 つの注力分野のどれに寄与するかを判定し、理由を書きます。どれにも寄与しない場合は {NO_FOCUS_AREA} とし理由を書きます。
{AREAS}
- 追跡すべき KPI 候補を 3〜6 件提案します（利用者はこの中から最大 {MAX_KPIS} 件を選びます）。各 KPI に単位・測り方・データの入手見込み（open_data=公開データで測れそう, survey_needed=アンケートや観測が必要, unknown=不明）を付けます。
- 文脈から分からない項目は空文字にし、推測で埋めないこと。"""

SCHEMA = llm.obj(
    {
        "title": llm.STR,
        "target": llm.STR,
        "place_time": llm.STR,
        "evidence": {
            "type": "array",
            "items": llm.obj({"kind": llm.enum(["news", "conversation", "observation"]), "text": llm.STR, "quote": llm.STR}),
        },
        "focus_area": llm.enum(list(FOCUS_AREAS) + [NO_FOCUS_AREA]),
        "focus_reason": llm.STR,
        "kpi_candidates": {
            "type": "array",
            "items": llm.obj(
                {
                    "name": llm.STR,
                    "unit": llm.STR,
                    "measurement": llm.STR,
                    "data_availability": llm.enum(["open_data", "survey_needed", "unknown"]),
                }
            ),
        },
    }
)


@observed("issue-card-agent")
def draft(context: str) -> Dict[str, Any]:
    """
    probe-agent:
      role: 会話や元文脈から課題カード下書きを生成するAIエージェント入口
      capability: 会話やコミュニティから課題候補・課題カードへ昇格させる
      system_purpose: 関心や対話を根拠付きの構造化課題へ整理し、人の採用判断へ渡す
      probe_value: AI生成物を候補として提示する中心であり、共通承認パターンに接続する前段の品質を確認できる
      element_type: capability
      operation_kind: analysis
      consumers: [apps.api.app.routes.issues.create_draft, apps.api.app.routes.issues.create_issue_card]
      state_effects: [external-api]
    """
    return llm.complete_json(SYSTEM, context, SCHEMA, "issue_card_draft")
