"""課題カード作成 Agent (F-06 / F-07): drafts a card, judges focus area, proposes KPIs."""
from __future__ import annotations

from typing import Any, Dict

from .. import llm
from ..domain import FOCUS_AREAS, MAX_KPIS, NO_FOCUS_AREA
from ..observe import observed

AREAS = "\n".join(f"{k}: {v}" for k, v in FOCUS_AREAS.items())

SYSTEM = f"""あなたは渋谷区の課題カード作成を手伝うアシスタントです。与えられた文脈（ニュース記事・利用者との対話・スレッドの発言）から、課題カードの下書きを作ります。
- タイトルは「対象・場所: 困りごと」の形で短く。
- 根拠は文脈に実際にあるものだけ。各根拠に種類（news=記事, conversation=AI との対話での利用者の発言, thread=コミュニティのスレッドの発言, observation=観測）と、利用者の言葉なら引用を付けます。創作しないこと。
- 渋谷区の 7 つの注力分野のどれに寄与するかを判定し、理由を書きます。どれにも寄与しない場合は {NO_FOCUS_AREA} とし理由を書きます。
{AREAS}
- 追跡すべき KPI 候補を 3〜6 件提案します（利用者はこの中から最大 {MAX_KPIS} 件を選びます）。各 KPI に単位・測り方・データの入手見込みを付けます。
  入手見込みは、文脈の [登録済みのデータセット] で測れそうなら open_data、アンケートや観測が必要なら survey_needed、判断できなければ unknown。一覧にないデータを open_data にしないこと。施設などの一覧は行を数えれば件数を測れます。
- 文脈から分からない項目は空文字にし、推測で埋めないこと。
- 元の文脈が住民の困りごとを含むかを origin_fit で示します。
  resident_issue: 住民・利用者の困りごとや要望が書かれている。
  announcement: 区のお知らせ（意見募集・計画の公表・事業者募集・通知の発送など）で、困りごとは書かれていない。この場合、タイトルを困りごとのように言い換えず、fit_note に「当事者の声を集めてから課題にする」ための問いかけを 1 文で書きます。
  personal_incident: 逮捕・不祥事・事故など特定の個人に関わる事案。個人や事案そのものを課題や KPI にしないこと（kpi_candidates は空にします）。fit_note に、扱うなら仕組みの困りごとに絞る旨を書きます。
  resident_issue のとき fit_note は空文字。"""

SCHEMA = llm.obj(
    {
        "title": llm.STR,
        "target": llm.STR,
        "place_time": llm.STR,
        "evidence": {
            "type": "array",
            "items": llm.obj({"kind": llm.enum(["news", "conversation", "thread", "observation"]), "text": llm.STR, "quote": llm.STR}),
        },
        "origin_fit": llm.enum(["resident_issue", "announcement", "personal_incident"]),
        "fit_note": llm.STR,
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
      capability: F-06 課題カード作成、F-07 注力分野判定・KPI 提案（会話や元文脈から課題カードの下書きを作る）
      system_purpose: 関心や対話を根拠付きの構造化課題へ整理し、人の採用判断へ渡す
      probe_value: AI生成物を候補として提示する中心であり、共通承認パターンに接続する前段の品質を確認できる
      element_type: capability
      operation_kind: analysis
      consumers: [apps.api.app.routes.issues.create_draft, apps.api.app.routes.issues.create_issue_card]
      state_effects: [external-api]
    """
    out = llm.complete_json(SYSTEM, context, SCHEMA, "issue_card_draft")
    if out.get("origin_fit") == "personal_incident":
        out["kpi_candidates"] = []  # never track a person or an incident as a KPI (P-6)
    return out
