"""施策ニュース化 (F-14): drafts a policy news article from an adopted issue card."""
from __future__ import annotations

from typing import Any, Dict, List

from .. import llm
from ..observe import observed

SYSTEM = """あなたは渋谷区の職員が、区民の課題カードを採用して始める施策を区民に知らせるニュース記事を書くのを手伝います。
- 与えられた課題カード・KPI の現状・区の判断理由だけを根拠に書きます。予算・日付・場所など、与えられていない事実を創作しないこと。
- タイトルは 40 字以内。本文は 300〜500 字で、(1) 区民の声から始まったこと、(2) 区が何を始めるか（判断理由の範囲で）、
  (3) 公開ダッシュボードで KPI の変化を追えること、の順に書きます。
- 個人名や個別の発言の引用は書かず、「区民から〜という声が寄せられました」のようにまとめます。
- 施策の効果は断定しません（例: 「改善します」ではなく「改善を目指します」）。
- カテゴリは候補の中から 1 つ選びます。
- 施策開始の注釈に使う短いラベル（20 字以内）を付けます。"""


def _schema(categories: List[str]) -> Dict[str, Any]:
    return llm.obj({
        "title": llm.STR,
        "body": llm.STR,
        "category": llm.enum(categories),
        "annotation_label": llm.STR,
    })


@observed("policy-news-agent")
def draft(context: str, categories: List[str]) -> Dict[str, Any]:
    """
    probe-agent:
      role: 区職員が採用した課題カードから施策ニュースの下書きを生成する AI エージェント入口
      capability: F-14 施策ニュース化と還流（採用された施策をニュースとして区民へ還流する）
      system_purpose: 区の判断を当事者とコミュニティへ返し、つくる → 公開 → 採用 の循環を閉じる
      probe_value: 区の公式発信の下書きになるため、創作・効果の断定がないかを観測する価値が高い
      element_type: capability
      operation_kind: analysis
      consumers: [apps.api.app.routes.policy.create_policy_news_draft]
      state_effects: [external-api]
    """
    return llm.complete_json(SYSTEM, f"カテゴリ候補: {'、'.join(categories)}\n\n{context}", _schema(categories), "policy_news_draft")
