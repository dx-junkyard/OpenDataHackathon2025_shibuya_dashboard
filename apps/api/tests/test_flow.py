"""Representative flow (docs/ux.md §5) with the AI agents replaced by fixed outputs."""
from app.agents import chat, issue_card, opendata, shaping

from .conftest import as_user

PARENT, VISITOR, STAFF = 1, 2, 3

DRAFT = {
    "title": "近所: 子どもが外遊びできる場所が少ない",
    "target": "未就学児〜小学生の子どもと保護者",
    "place_time": "住宅地の近所／放課後・休日",
    "evidence": [{"kind": "conversation", "text": "近所の公園はボール遊び禁止で遊べる場所がない", "quote": "近所に子どもが思い切り遊べる場所がありません"}],
    "focus_area": "AREA-1",
    "focus_reason": "子どもが安心して外遊びできる環境は子育て支援の要望の最多のため",
    "kpi_candidates": [
        {"name": "外遊びできる場所の数", "unit": "か所", "measurement": "区内の公園・児童遊園地・プレーパーク等の数（累計）", "data_availability": "open_data"},
        {"name": "プレーパークの日別平均利用者数", "unit": "人", "measurement": "月次の日別平均", "data_availability": "open_data"},
        {"name": "外遊び環境の満足度（5段階）", "unit": "点", "measurement": "外遊び環境の満足度調査", "data_availability": "survey_needed"},
        {"name": "遊具の点検件数", "unit": "件", "measurement": "点検結果", "data_availability": "unknown"},
    ],
}

PLAN = {
    "feasible": True, "date_column": "開設日", "value_column": "", "filter_column": "区名", "filter_value": "渋谷区",
    "aggregation": "count_rows", "period": "month", "cumulative": True, "steps": ["渋谷区の行だけを使う", "開設月ごとに数えて累計する"],
}


def test_ai_unavailable_keeps_user_message_and_offers_manual_path(client):
    conv = client.post("/api/conversations", json={"news_id": 1}, headers=as_user(PARENT)).json()
    out = client.post(f"/api/conversations/{conv['id']}/messages", json={"text": "近所に子どもが思い切り遊べる場所がありません"},
                      headers=as_user(PARENT)).json()
    assert [m["speaker"] for m in out["messages"]] == ["user", "ai"]
    assert out["messages"][1]["ai_status"] == "unavailable"
    r = client.post("/api/issue-drafts", json={"origin_kind": "conversation", "origin_ref": conv["id"]}, headers=as_user(PARENT))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_unavailable"
    manual = client.post("/api/issue-cards", json={"title": "手入力の課題", "origin_kind": "manual"}, headers=as_user(PARENT))
    assert manual.status_code == 201 and manual.json()["proposal_id"] is None


def _card_from_conversation(client, monkeypatch, edit_title=False):
    monkeypatch.setattr(chat, "respond", lambda a, h: {"reply": "どこで困りましたか？", "organization": [
        {"kind": "experience", "text": "近所の公園でボール遊びができなかった", "source_message_index": 1}]})
    monkeypatch.setattr(issue_card, "draft", lambda ctx: DRAFT)
    conv = client.post("/api/conversations", json={"news_id": 1}, headers=as_user(PARENT)).json()
    out = client.post(f"/api/conversations/{conv['id']}/messages", json={"text": "近所に子どもが思い切り遊べる場所がありません"},
                      headers=as_user(PARENT)).json()
    assert out["messages"][1]["organization"][0]["kind"] == "experience"
    prop = client.post("/api/issue-drafts", json={"origin_kind": "conversation", "origin_ref": conv["id"]},
                       headers=as_user(PARENT)).json()
    assert prop["status"] == "proposed" and {e["kind"] for e in prop["evidence"]} == {"conversation", "news"}
    d = prop["payload"]
    body = {"proposal_id": prop["id"], "title": d["title"] + ("（編集）" if edit_title else ""), "target": d["target"],
            "place_time": d["place_time"], "evidence": d["evidence"], "focus_area": d["focus_area"],
            "focus_reason": d["focus_reason"], "kpis": d["kpi_candidates"][:3],
            "origin_kind": "conversation", "origin_ref": str(conv["id"]), "community_id": 1}
    card = client.post("/api/issue-cards", json=body, headers=as_user(PARENT))
    assert card.status_code == 201, card.text
    return prop, card.json()


def test_adopting_a_draft_records_a_manual_decision(client, monkeypatch):
    prop, card = _card_from_conversation(client, monkeypatch)
    p = client.get(f"/api/ai-proposals/{prop['id']}", headers=as_user(PARENT)).json()
    assert p["status"] == "adopted" and p["decision_method"] == "manual" and p["result_ref"] == f"issue_card:{card['id']}"
    again = client.post("/api/issue-cards", json={"proposal_id": prop["id"], "title": "x"}, headers=as_user(PARENT))
    assert again.status_code == 409


def test_edited_draft_is_recorded_as_adopted_edited(client, monkeypatch):
    prop, _ = _card_from_conversation(client, monkeypatch, edit_title=True)
    assert client.get(f"/api/ai-proposals/{prop['id']}", headers=as_user(PARENT)).json()["status"] == "adopted_edited"


def test_kpi_limit_is_three(client):
    kpis = [{"name": f"K{i}"} for i in range(4)]
    r = client.post("/api/issue-cards", json={"title": "t", "kpis": kpis}, headers=as_user(PARENT))
    assert r.status_code == 422


def test_personal_info_requires_acknowledgement(client):
    r = client.post("/api/issue-cards", json={"title": "連絡は taro@example.com まで"}, headers=as_user(PARENT))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "personal_info"
    r = client.post("/api/issue-cards", json={"title": "連絡は taro@example.com まで", "acknowledge_personal_info": True},
                    headers=as_user(PARENT))
    assert r.status_code == 201


def test_shaping_is_deterministic_and_cumulative(client):
    rows = [{"区名": "渋谷区", "開設日": "2026-01-03"}, {"区名": "渋谷区", "開設日": "2026-01-20"},
            {"区名": "新宿区", "開設日": "2026-02-01"}, {"区名": "渋谷区", "開設日": "2026/2/9"}]
    assert shaping.apply_plan(rows, PLAN) == [{"period": "2026-01", "value": 2.0}, {"period": "2026-02", "value": 3.0}]


def test_full_flow_to_staff_adoption(client, monkeypatch):
    _, card = _card_from_conversation(client, monkeypatch)
    kpi = card["kpis"][0]
    datasets = client.get("/api/datasets").json()["items"]
    spots = next(d for d in datasets if d["file_path"] == "sample_play_spaces.csv")
    monkeypatch.setattr(opendata, "search", lambda k, cat: {"candidates": [{"dataset_id": spots["id"], "reason": "開設日がある"}]})
    monkeypatch.setattr(shaping, "propose_plan", lambda k, cols, sample: PLAN)
    search = client.post(f"/api/kpis/{kpi['id']}/dataset-search", headers=as_user(PARENT)).json()
    assert search["payload"]["candidates"][0]["dataset"]["is_sample"] is True
    assert client.post(f"/api/kpis/{kpi['id']}/dataset-search", headers=as_user(VISITOR)).status_code == 403
    plan = client.post(f"/api/kpis/{kpi['id']}/shaping-plans",
                       json={"dataset_id": spots["id"], "search_proposal_id": search["id"]}, headers=as_user(PARENT)).json()
    assert plan["payload"]["preview_error"] == "" and plan["payload"]["after_preview"]
    assert plan["payload"]["warnings"] == []
    # Nothing reaches the KPI before the plan is adopted.
    assert client.get(f"/api/issue-cards/{card['id']}", headers=as_user(PARENT)).json()["kpis"][0]["points"] == []
    adopted = client.post(f"/api/shaping-plans/{plan['id']}/adopt", json={}, headers=as_user(PARENT)).json()
    assert adopted["points"][-1]["value"] >= adopted["points"][0]["value"]
    client.put(f"/api/kpis/{kpi['id']}/target", json={"target_value": 74}, headers=as_user(PARENT))

    pub = client.post(f"/api/issue-cards/{card['id']}/dashboard/publish", json={}, headers=as_user(PARENT)).json()
    slug = pub["dashboard"]["public_slug"]
    view = client.get(f"/api/public/dashboards/{slug}").json()
    assert view["status"] == "dashboard_published"
    assert all(e["kind"] != "conversation" for e in view["evidence_sources"])  # no individual voices in public
    statuses = {k["name"]: k["data_status"] for k in view["kpis"]}
    assert statuses["外遊びできる場所の数"] == "available" and statuses["プレーパークの日別平均利用者数"] == "not_collected"
    csv_text = client.get(f"/api/public/dashboards/{slug}/export.csv").text
    assert "未取得" in csv_text and "はい（架空）" in csv_text

    # Re-publishing keeps the same URL.
    again = client.post(f"/api/issue-cards/{card['id']}/dashboard/publish", json={}, headers=as_user(PARENT)).json()
    assert again["dashboard"]["public_slug"] == slug

    assert client.post(f"/api/dashboards/{pub['dashboard']['id']}/decisions",
                       json={"state": "adopted", "reason": "x"}, headers=as_user(PARENT)).status_code == 403
    staff_list = client.get("/api/staff/dashboards", headers=as_user(STAFF)).json()["items"]
    assert [i["issue_card_id"] for i in staff_list] == [card["id"]]
    dec = client.post(f"/api/dashboards/{pub['dashboard']['id']}/decisions",
                      json={"state": "under_review", "reason": "設置候補地を調査します"}, headers=as_user(STAFF)).json()
    assert dec["status"] == "under_review" and dec["latest_decision"]["department"] == "子ども家庭部 子育て支援課"
    notes = client.get("/api/me/notifications", headers=as_user(PARENT)).json()["items"]
    assert notes and "検討中" in notes[0]["text"]
    me = client.get("/api/me", headers=as_user(PARENT)).json()
    assert me["unread_notifications"] == 1 and me["issue_cards"][0]["status_label"] == "区で検討中"


def test_unpublished_dashboard_says_private(client, monkeypatch):
    _, card = _card_from_conversation(client, monkeypatch)
    pub = client.post(f"/api/issue-cards/{card['id']}/dashboard/publish", json={}, headers=as_user(PARENT)).json()
    client.post(f"/api/issue-cards/{card['id']}/dashboard/unpublish", headers=as_user(PARENT))
    assert client.get(f"/api/public/dashboards/{pub['dashboard']['public_slug']}").status_code == 410


def test_missing_area_filter_is_warned():
    profile = shaping.profile_columns([{"区名": "渋谷区", "設置日": "2026-01-01"}, {"区名": "新宿区", "設置日": "2026-01-02"}])
    no_filter = {**PLAN, "filter_column": "", "filter_value": ""}
    assert shaping.plan_warnings(no_filter, profile) == ["「区名」に渋谷区以外（新宿区）の行が含まれていますが、絞り込みがありません"]
    assert shaping.plan_warnings(PLAN, profile) == []
