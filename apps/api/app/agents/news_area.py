"""ニュースの注力分野の推定 (F-01, GAP-OP-2).

区のホームページの分類（施設案内・区政情報など）は 7 つの注力分野と 1 対 1 に
対応しないため、取り込んだ記事の 96%（29 件中 28 件、2026-10-24）が分野なしに
なり、分野で探す利用者に届かなかった。記事の題名・本文・区の分類・担当課から
分野を 1 つ推定し、理由を返す。結果は「AI の推定」として表示し、区職員が直せる。
AI が使えないときは推定しない（未判定のまま残す。見た目だけの推定はしない）。
"""
from __future__ import annotations

from typing import Any, Dict

from .. import llm
from ..domain import FOCUS_AREAS
from ..observe import observed

NONE = "none"

SYSTEM = """あなたは渋谷区のニュース記事を、区の 7 つの注力分野のどれに関係するかで分類します。
- 記事の題名・本文・区のホームページ上の分類・担当課が与えられます。
- 記事の内容が最も直接に関係する分野を 1 つ選びます。区のホームページ上の分類名だけで決めず、内容で判断します
  （例: 公園や児童遊園地の整備・利用は、子どもの遊び場なら子育て、地域の交流の場なら空間とコミュニティ）。
- 区民の暮らしの体験ではなく区の事務についての記事は、扱う施設や事業の分野にかかわらず none にします。
  例: 入札・契約、業務委託の公募型プロポーザルや事業者の選定結果、職員の不祥事やお詫び、手続きの様式変更。
  （子育て支援センターの運営委託の公募でも、区民向けの子育ての情報ではないので none です。）
- reason には、記事のどの記述からその分野と判断したかを 1 文で書きます。記事に書かれていないことは書きません。"""

SCHEMA = llm.obj({"focus_area": llm.enum(list(FOCUS_AREAS) + [NONE]), "reason": llm.STR})


def _prompt(article: Dict[str, Any]) -> str:
    areas = "\n".join(f"- {k}: {v}" for k, v in FOCUS_AREAS.items())
    return (f"注力分野:\n{areas}\n\n"
            f"題名: {article['title']}\n区の分類: {article.get('category', '')}\n担当課: {article.get('department', '')}\n"
            f"本文:\n{(article.get('body') or '')[:1500]}")


@observed("news-area-agent")
def estimate(article: Dict[str, Any]) -> Dict[str, str]:
    """
    probe-agent:
      role: 区のニュース記事の注力分野を、記事の内容から 1 つ推定し理由を返す AI エージェント入口
      capability: F-01 ニュース集約・配信
      system_purpose: 区の分類が施設の目線でも、分野で探す区民（子育て中の保護者など）にニュースを届ける（OBJ-1、GAP-OP-2）
      probe_value: 分野なしの記事の割合、推定が区職員に直された割合を観測できる
      element_type: capability
      operation_kind: analysis
      consumers: [apps.api.app.ingest.news.classify_unassigned]
      state_effects: [external-api]
    """
    out = llm.complete_json(SYSTEM, _prompt(article), SCHEMA, "news_focus_area")
    area = out["focus_area"] if out["focus_area"] in FOCUS_AREAS else ""
    return {"focus_area": area, "reason": out["reason"].strip()}
