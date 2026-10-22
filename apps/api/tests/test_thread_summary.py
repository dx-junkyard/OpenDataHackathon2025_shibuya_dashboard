"""スレッド要約・課題候補 (F-05 / MS-2.1) with the AI replaced by fixed outputs."""
from app import llm
from app.agents import issue_card, thread_summary

from .conftest import as_user

PARENT, VISITOR, STAFF, MANAGER = 1, 2, 3, 4
THREAD = 1  # seeded: 「授乳・おむつ替えスペースの不足について」 (posts by the manager and staff)

RESULT = {
    "summary": "駅周辺の授乳スペース不足について、区職員が現状の把握を求めている。",
    "points": [
        {"kind": "experience", "text": "外出中に授乳スペースがなく困った", "post_numbers": [1]},
        {"kind": "question", "text": "設置場所と混雑状況の情報提供の依頼", "post_numbers": [2]},
        {"kind": "opinion", "text": "根拠のない点", "post_numbers": [9]},
    ],
    "issue_candidates": [
        {"title": "駅周辺: 授乳スペースが足りない", "target": "乳幼児連れの保護者", "reason": "発言1の経験",
         "post_numbers": [1, 2, 7]},
        {"title": "根拠のない候補", "target": "", "reason": "", "post_numbers": []},
    ],
    "open_questions": ["どの駅で不足しているか"],
}


def _fake_llm(monkeypatch, seen=None):
    def fake(system, user, schema, name):
        if seen is not None:
            seen.append(user)
        return {**RESULT, "points": list(RESULT["points"]), "issue_candidates": list(RESULT["issue_candidates"])}
    monkeypatch.setattr(llm, "complete_json", fake)


def _summarize(client, monkeypatch, uid=MANAGER):
    _fake_llm(monkeypatch)
    return client.post(f"/api/threads/{THREAD}/summary", headers=as_user(uid))


def test_summary_is_a_proposal_grounded_in_thread_posts(client, monkeypatch):
    r = _summarize(client, monkeypatch)
    assert r.status_code == 201, r.text
    s = r.json()
    post_ids = [p["id"] for p in client.get(f"/api/threads/{THREAD}", headers=as_user(MANAGER)).json()["posts"]]
    assert s["kind"] == "thread_summary" and s["status"] == "proposed" and s["stale"] is False
    # Points and candidates citing no post of the thread are dropped; out-of-range citations are removed.
    assert [p["text"] for p in s["payload"]["points"]] == ["外出中に授乳スペースがなく困った", "設置場所と混雑状況の情報提供の依頼"]
    [cand] = s["payload"]["issue_candidates"]
    assert cand["post_numbers"] == [1, 2] and cand["post_ids"] == post_ids
    assert [e["ref"] for e in s["evidence"]] == [f"post:{i}" for i in post_ids]
    thread = client.get(f"/api/threads/{THREAD}", headers=as_user(VISITOR)).json()
    assert thread["summary"]["id"] == s["id"]


def test_summary_is_for_members_and_hides_names_and_contacts(client, monkeypatch):
    assert _summarize(client, monkeypatch, uid=VISITOR).status_code == 403
    client.post(f"/api/threads/{THREAD}/posts", json={"text": "詳しくは 090-1234-5678 か hanako@example.com へ"},
                headers=as_user(MANAGER))
    seen = []
    _fake_llm(monkeypatch, seen)
    client.post(f"/api/threads/{THREAD}/summary", headers=as_user(MANAGER))
    sent = seen[0]
    assert "090-1234-5678" not in sent and "hanako@example.com" not in sent
    assert "子育て@渋谷 運営" not in sent and "[発言1: コミュニティ運営]" in sent
    assert "[発言2: 区職員（子ども家庭部 子育て支援課）]" in sent


def test_new_posts_make_the_summary_stale(client, monkeypatch):
    _summarize(client, monkeypatch)
    client.post(f"/api/threads/{THREAD}/posts", json={"text": "恵比寿駅でも困りました"}, headers=as_user(MANAGER))
    assert client.get(f"/api/threads/{THREAD}", headers=as_user(MANAGER)).json()["summary"]["stale"] is True


def test_ai_unavailable_is_reported_not_hidden(client):
    r = client.post(f"/api/threads/{THREAD}/summary", headers=as_user(MANAGER))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_unavailable"
    assert client.get(f"/api/threads/{THREAD}", headers=as_user(MANAGER)).json()["summary"] is None


def test_rejected_summary_is_not_shown_and_cannot_seed_a_card(client, monkeypatch):
    s = _summarize(client, monkeypatch).json()
    client.post(f"/api/ai-proposals/{s['id']}/reject", headers=as_user(MANAGER))
    assert client.get(f"/api/threads/{THREAD}", headers=as_user(MANAGER)).json()["summary"] is None
    r = client.post("/api/issue-drafts", json={"origin_kind": "thread", "origin_ref": THREAD,
                                               "summary_proposal_id": s["id"], "candidate_index": 0},
                    headers=as_user(MANAGER))
    assert r.status_code == 409


def test_candidate_carries_into_the_card_and_is_adopted_on_save(client, monkeypatch):
    s = _summarize(client, monkeypatch).json()
    contexts = []

    def fake_draft(ctx):
        contexts.append(ctx)
        return {"title": "駅周辺: 授乳スペースが足りない", "target": "乳幼児連れの保護者", "place_time": "駅周辺",
                "evidence": [{"kind": "observation", "text": "外出中に困った", "quote": "外出中に困りました"}],
                "focus_area": "AREA-1", "focus_reason": "子育て", "kpi_candidates": [
                    {"name": "スポット設置数", "unit": "か所", "measurement": "", "data_availability": "open_data"}]}
    monkeypatch.setattr(issue_card, "draft", fake_draft)
    other = client.post("/api/issue-drafts", json={"origin_kind": "thread", "origin_ref": 99,
                                                   "summary_proposal_id": s["id"], "candidate_index": 0},
                        headers=as_user(MANAGER))
    assert other.status_code in (404, 422)
    d = client.post("/api/issue-drafts", json={"origin_kind": "thread", "origin_ref": THREAD,
                                               "summary_proposal_id": s["id"], "candidate_index": 0},
                    headers=as_user(MANAGER)).json()
    assert "課題候補（AI の提案）] 駅周辺: 授乳スペースが足りない" in contexts[0]
    assert {e["kind"] for e in d["evidence"]} == {"thread", "thread_summary"}
    p = d["payload"]
    # The cited posts come first, verbatim and with the speaker's stance only.
    assert [(e["kind"], e["text"]) for e in p["evidence"][:2]] == [
        ("thread", "スレッドの発言1（コミュニティ運営）"), ("thread", "スレッドの発言2（区職員（子ども家庭部 子育て支援課））")]
    assert p["evidence"][0]["quote"].startswith("駅周辺に授乳スペース")
    card = client.post("/api/issue-cards", json={
        "proposal_id": d["id"], "title": p["title"], "target": p["target"], "place_time": p["place_time"],
        "evidence": p["evidence"], "focus_area": p["focus_area"], "focus_reason": p["focus_reason"],
        "kpis": p["kpi_candidates"], "origin_kind": "thread", "origin_ref": str(THREAD), "community_id": 1},
        headers=as_user(MANAGER)).json()
    summary = client.get(f"/api/ai-proposals/{s['id']}", headers=as_user(MANAGER)).json()
    assert summary["status"] == "adopted" and summary["decision_method"] == "manual"
    assert summary["result_ref"] == f"issue_card:{card['id']}#candidate:0"
    assert client.get(f"/api/ai-proposals/{d['id']}", headers=as_user(MANAGER)).json()["status"] == "adopted"
    # The thread shows which card the candidate became, and the card links back to the thread.
    made = client.get(f"/api/threads/{THREAD}", headers=as_user(VISITOR)).json()["summary"]["issue_cards"]
    assert made == [{"candidate_index": 0, "id": card["id"], "title": p["title"]}]
    origin = client.get(f"/api/issue-cards/{card['id']}", headers=as_user(VISITOR)).json()["origin"]
    assert origin == {"kind": "thread", "label": "授乳・おむつ替えスペースの不足について", "path": f"/community/1?thread={THREAD}"}


def test_recent_voice_returns_only_the_users_own_words(client, monkeypatch):
    assert client.get("/api/me/recent-voice", headers=as_user(PARENT)).json()["texts"] == []
    monkeypatch.setattr(llm, "complete_json", lambda *a: {"reply": "AI の返答", "organization": []})
    conv = client.post("/api/conversations", json={"news_id": 1}, headers=as_user(PARENT)).json()
    client.post(f"/api/conversations/{conv['id']}/messages", json={"text": "恵比寿駅で授乳場所を30分探しました"},
                headers=as_user(PARENT))
    v = client.get("/api/me/recent-voice", headers=as_user(PARENT)).json()
    assert v["conversation_id"] == conv["id"] and v["texts"] == ["恵比寿駅で授乳場所を30分探しました"]
    assert v["news_title"].startswith("区内の授乳")
    assert client.get("/api/me/recent-voice", headers=as_user(VISITOR)).json()["texts"] == []


def test_conversation_origin_is_private_to_the_author(client, monkeypatch):
    monkeypatch.setattr(llm, "complete_json", lambda *a: {"reply": "r", "organization": []})
    conv = client.post("/api/conversations", json={"news_id": 1}, headers=as_user(PARENT)).json()
    client.post(f"/api/conversations/{conv['id']}/messages", json={"text": "困りました"}, headers=as_user(PARENT))
    card = client.post("/api/issue-cards", json={"title": "t", "origin_kind": "conversation", "origin_ref": str(conv["id"])},
                       headers=as_user(PARENT)).json()
    assert card["origin"]["path"] == "/news/1"
    assert client.get(f"/api/issue-cards/{card['id']}", headers=as_user(VISITOR)).json()["origin"]["path"] == ""


def test_issue_draft_context_lists_registered_datasets(client, monkeypatch):
    seen = []
    monkeypatch.setattr(issue_card, "draft", lambda ctx: seen.append(ctx) or {
        "title": "t", "target": "", "place_time": "", "evidence": [], "focus_area": "AREA-1", "focus_reason": "",
        "kpi_candidates": []})
    r = client.post("/api/issue-drafts", json={"origin_kind": "news", "origin_ref": 1}, headers=as_user(PARENT))
    assert r.status_code == 201
    assert "[登録済みのデータセット]" in seen[0]
    assert "授乳・おむつ替えスポット一覧（サンプル）" in seen[0] and "サンプル（架空）" in seen[0]


def test_issue_card_agent_accepts_thread_evidence():
    from app.agents.issue_card import SCHEMA
    kinds = SCHEMA["properties"]["evidence"]["items"]["properties"]["kind"]["enum"]
    assert "thread" in kinds
