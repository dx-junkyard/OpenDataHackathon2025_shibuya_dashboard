"""Community 形成支援 Agent (F-05): summarizes a thread and proposes issue candidates.

Every summary point and issue candidate must cite posts of the thread
(UXR-7, P-3). Citations to posts that are not in the thread are dropped, and
a point or candidate left without any citation is dropped with them, so the
AI cannot present an ungrounded claim as the discussion's conclusion.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .. import llm
from ..observe import observed

POINT_KINDS = ["experience", "opinion", "question", "staff_info"]

SYSTEM = """あなたは渋谷区のコミュニティのスレッドを整理するアシスタントです。議論を決めるのは参加者で、あなたは整理と候補の提示だけをします。
- 発言は [発言n: 立場] の形で与えられます。整理の各点と課題候補には、根拠になった発言の番号 n を必ず付けます。根拠のない点は書きません。
- 整理の各点には種類を付けます: experience=参加者が述べた経験・事実, opinion=意見・要望, question=疑問・情報提供の依頼, staff_info=区職員による情報提供。
- 課題候補は「対象・場所: 困りごと」の形の短いタイトルにし、なぜ課題と言えるかを発言に基づいて書きます。0〜3 件。発言から言えない候補は作りません。
- まだ分かっていないこと（数値・場所・原因など）は open_questions に書き、推測で埋めないこと。
- 個人を特定できる情報（氏名・連絡先・住所）は書かないこと。"""

SCHEMA = llm.obj(
    {
        "summary": llm.STR,
        "points": {
            "type": "array",
            "items": llm.obj({"kind": llm.enum(POINT_KINDS), "text": llm.STR,
                              "post_numbers": {"type": "array", "items": {"type": "integer"}}}),
        },
        "issue_candidates": {
            "type": "array",
            "items": llm.obj({"title": llm.STR, "target": llm.STR, "reason": llm.STR,
                              "post_numbers": {"type": "array", "items": {"type": "integer"}}}),
        },
        "open_questions": {"type": "array", "items": llm.STR},
    }
)


def _grounded(items: List[Dict[str, Any]], valid: set) -> List[Dict[str, Any]]:
    out = []
    for it in items:
        nums = sorted({n for n in it.get("post_numbers", []) if n in valid})
        if nums:
            out.append({**it, "post_numbers": nums})
    return out


@observed("thread-summary-agent")
def summarize(title: str, posts: List[Dict[str, str]]) -> Dict[str, Any]:
    """Return {summary, points[], issue_candidates[], open_questions[]} for a thread.

    `posts` are {speaker, text} in thread order; post number n is the 1-based index.

    probe-agent:
      role: スレッドの発言を要約し、発言番号の根拠付きで課題候補を提示するAIエージェント入口
      capability: 会話やコミュニティから課題候補・課題カードへ昇格させる
      system_purpose: 一人の不満をコミュニティで共有された課題にし、根拠付きの課題カード作成へ橋渡しする（OBJ-2 / MS-2.1）
      probe_value: 根拠のない要約・候補を除外できているか、候補が課題カードに採用されたかを観測できる
      element_type: capability
      operation_kind: analysis
      consumers: [apps.api.app.routes.communities.summarize_thread]
      state_effects: [external-api]
    """
    lines = [f"[スレッド] {title}"]
    lines += [f"[発言{i}: {p['speaker']}] {p['text']}" for i, p in enumerate(posts, start=1)]
    out = llm.complete_json(SYSTEM, "\n\n".join(lines), SCHEMA, "thread_summary")
    valid = set(range(1, len(posts) + 1))
    out["points"] = _grounded(out["points"], valid)
    out["issue_candidates"] = _grounded(out["issue_candidates"], valid)[:3]
    return out
