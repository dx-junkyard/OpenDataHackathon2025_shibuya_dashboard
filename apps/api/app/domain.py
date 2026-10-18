"""Finite vocabularies shared by the API (docs/vision.md §5, docs/features.md)."""
from __future__ import annotations

FOCUS_AREAS = {
    "AREA-1": "それぞれの成長を、一生よろこべる街へ（子育て・教育・生涯学習）",
    "AREA-2": "あらゆる人が、自分らしく生きられる街へ（福祉）",
    "AREA-3": "思わず体を動かしたくなる街へ（健康・スポーツ）",
    "AREA-4": "人のつながりと意識が未来を守る街へ（防災・安全・環境・エネルギー）",
    "AREA-5": "愛せる場所と仲間を、誰もがもてる街へ（空間とコミュニティのデザイン）",
    "AREA-6": "あらたな文化を生みつづける街へ（文化・エンタテイメント）",
    "AREA-7": "ビジネスの冒険に満ちた街へ（産業振興）",
}
NO_FOCUS_AREA = "NONE"

MAX_KPIS = 3

ORGANIZATION_KINDS = ["experience", "opinion", "question", "article_fact", "ai_inference"]

ISSUE_STATUS_LABELS = {
    "draft": "下書き",
    "published": "公開",
    "verifying": "検証中",
    "dashboard_published": "ダッシュボード公開",
    "under_review": "区で検討中",
    "adopted": "採用",
    "declined": "見送り",
}

ADOPTION_TO_ISSUE_STATUS = {
    "under_review": "under_review",
    "adopted": "adopted",
    "declined": "declined",
}
