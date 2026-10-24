"""雑談 Agent (F-02): article-aware free conversation that organizes, never decides."""
from __future__ import annotations

from typing import Any, Dict, List

from .. import llm
from ..domain import ORGANIZATION_KINDS
from ..observe import observed

SYSTEM = """あなたは渋谷区の住民・来訪者・事業者の声を聞く対話相手です。
- 利用者が読んだニュース記事を文脈として、気軽に話を聞き、関心や困りごとを言葉にする手伝いをします。
- 分類や入力項目を先に求めません。質問は一度に一つまで、短く、やさしい日本語で。
- 返答とは別に、ここまでの会話を整理します。整理の各項目には種類を付けます:
  experience=利用者が述べた経験・事実, opinion=利用者の意見, question=利用者の疑問,
  article_fact=記事に書かれている事実, ai_inference=あなたの推測。
- 利用者の質問や仮定（「〜なら」）を experience にしてはいけません。推測は必ず ai_inference にします。
- 整理は利用者が実際に述べたこと・記事にあることだけを根拠にし、根拠の発言番号（記事なら 0）を付けます。"""

SCHEMA = llm.obj(
    {
        "reply": llm.STR,
        "organization": {
            "type": "array",
            "items": llm.obj(
                {
                    "kind": llm.enum(ORGANIZATION_KINDS),
                    "text": llm.STR,
                    "source_message_index": {"type": "integer"},
                }
            ),
        },
    }
)


@observed("chat-agent")
def respond(article: Dict[str, Any] | None, history: List[Dict[str, str]]) -> Dict[str, Any]:
    """Return {reply, organization[]} for the latest user turn in `history`.

    probe-agent:
      role: ニュース文脈を保ったAI対話応答を生成するエージェント入口
      capability: F-02 記事文脈つき AI 対話（ニュース閲覧から文脈を保った AI 対話へ入る）
      system_purpose: ニュースを起点に関心を引き出し、思考整理の入口を提供して課題化の循環へ接続する
      probe_value: 代表フローの最初のAI接点であり、記事文脈の保持、AI応答可否、障害時の退避挙動を確認する価値が高い
      element_type: capability
      operation_kind: analysis
      consumers: [apps.api.app.routes.news.post_message, apps.api.app.routes.news.create_conversation]
      state_effects: [external-api]
    """
    lines = []
    if article:
        lines.append(f"[発言0: 記事] {article['title']}\n{article['body']}")
    for i, m in enumerate(history, start=1):
        who = "利用者" if m["speaker"] == "user" else "AI"
        lines.append(f"[発言{i}: {who}] {m['text']}")
    return llm.complete_json(SYSTEM, "\n\n".join(lines), SCHEMA, "chat_turn")
