"""アンケート・現場観測の収集 (F-11) with the AI replaced by fixed outputs."""
from app.agents import survey as survey_agent
from app.routes import surveys

from .conftest import as_user

PARENT, VISITOR, STAFF, MANAGER, BUSINESS = 1, 2, 3, 4, 5

DRAFT = {"kind": "survey", "title": "外出のしやすさ", "question": "授乳やおむつ替えの場所の見つけやすさは？（1=とても難しい、5=とても簡単）",
         "answer_type": "rating5", "unit": "点", "min_value": 1, "max_value": 5, "audience": "乳幼児連れで外出する保護者",
         "reason": "回答の月平均を KPI にする"}


def _card(client):
    r = client.post("/api/issue-cards", json={"title": "授乳場所の見つけやすさ", "community_id": 1,
                                              "kpis": [{"name": "見つけやすさ（5段階）", "unit": "点"}]},
                    headers=as_user(PARENT))
    assert r.status_code == 201, r.text
    return r.json()


def _survey(client, monkeypatch, edit=False):
    card = _card(client)
    kpi = card["kpis"][0]
    monkeypatch.setattr(survey_agent, "draft", lambda k, c: dict(DRAFT))
    prop = client.post(f"/api/kpis/{kpi['id']}/survey-drafts", headers=as_user(PARENT)).json()
    assert prop["kind"] == "survey_draft" and prop["status"] == "proposed"
    body = {k: prop["payload"][k] for k in ("kind", "title", "question", "answer_type", "unit", "min_value", "max_value", "audience")}
    if edit:
        body["title"] = "外出のしやすさ（編集）"
    s = client.post(f"/api/kpis/{kpi['id']}/surveys", json={**body, "proposal_id": prop["id"]}, headers=as_user(PARENT))
    assert s.status_code == 201, s.text
    return card, kpi, prop, s.json()


def test_ai_draft_is_a_proposal_adopted_only_when_saved(client, monkeypatch):
    card, kpi, prop, s = _survey(client, monkeypatch)
    p = client.get(f"/api/ai-proposals/{prop['id']}", headers=as_user(PARENT)).json()
    assert p["status"] == "adopted" and p["result_ref"] == f"survey:{s['id']}"
    assert s["status"] == "draft" and "salt" not in s
    _, _, prop2, _ = _survey(client, monkeypatch, edit=True)
    assert client.get(f"/api/ai-proposals/{prop2['id']}", headers=as_user(PARENT)).json()["status"] == "adopted_edited"


def test_manual_survey_when_ai_is_unavailable(client):
    kpi = _card(client)["kpis"][0]
    r = client.post(f"/api/kpis/{kpi['id']}/survey-drafts", headers=as_user(PARENT))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_unavailable"
    s = client.post(f"/api/kpis/{kpi['id']}/surveys", json={"kind": "observation", "title": "スポットの数", "question": "この駅で見つけた授乳スポットの数",
                                                         "answer_type": "number", "unit": "か所", "min_value": 0, "max_value": 50},
                    headers=as_user(PARENT))
    assert s.status_code == 201 and s.json()["proposal_id"] is None and s.json()["kind"] == "observation"


def test_only_the_card_author_creates_and_opens(client, monkeypatch):
    card, kpi, _, s = _survey(client, monkeypatch)
    assert client.post(f"/api/kpis/{kpi['id']}/survey-drafts", headers=as_user(VISITOR)).status_code == 403
    assert client.post(f"/api/surveys/{s['id']}/open", headers=as_user(VISITOR)).status_code == 403
    assert client.post(f"/api/surveys/{s['id']}/responses", json={"value": 3}, headers=as_user(VISITOR)).status_code == 409  # not open yet


def test_question_with_contact_details_is_refused(client):
    kpi = _card(client)["kpis"][0]
    r = client.post(f"/api/kpis/{kpi['id']}/surveys", json={"title": "t", "question": "連絡先 taro@example.com を教えて",
                                                         "answer_type": "rating5"}, headers=as_user(PARENT))
    assert r.status_code == 422


def test_months_below_the_threshold_stay_collecting_not_zero(client, monkeypatch):
    card, kpi, _, s = _survey(client, monkeypatch)
    client.post(f"/api/issue-cards/{card['id']}/dashboard/publish", json={}, headers=as_user(PARENT))
    opened = client.post(f"/api/surveys/{s['id']}/open", headers=as_user(PARENT)).json()
    assert opened["status"] == "open"
    # Community members were asked to answer.
    assert any(f"/surveys/{s['id']}" == n["link"] for n in client.get("/api/me/notifications", headers=as_user(MANAGER)).json()["items"])
    for uid, v in [(PARENT, 2), (VISITOR, 3), (STAFF, 4)]:
        assert client.post(f"/api/surveys/{s['id']}/responses", json={"value": v}, headers=as_user(uid)).status_code == 201
    view = client.get(f"/api/issue-cards/{card['id']}/dashboard", headers=as_user(PARENT)).json()
    k = view["kpis"][0]
    assert k["data_status"] == "collecting" and k["points"] == [] and k["current_value"] is None
    assert k["source"]["current_period_responses"] == 3 and k["source"]["min_responses"] == 5


def test_aggregate_and_count_only_never_individual_answers(client, monkeypatch):
    card, kpi, _, s = _survey(client, monkeypatch)
    pub = client.post(f"/api/issue-cards/{card['id']}/dashboard/publish", json={}, headers=as_user(PARENT)).json()
    client.post(f"/api/surveys/{s['id']}/open", headers=as_user(PARENT))
    for uid, v in [(PARENT, 2), (VISITOR, 3), (STAFF, 4), (MANAGER, 5), (BUSINESS, 1)]:
        client.post(f"/api/surveys/{s['id']}/responses", json={"value": v}, headers=as_user(uid))
    # Answering again in the same month replaces the earlier answer.
    after = client.post(f"/api/surveys/{s['id']}/responses", json={"value": 5}, headers=as_user(PARENT)).json()
    assert after["current_period_responses"] == 5 and after["answered_this_period"] is True
    slug = pub["dashboard"]["public_slug"]
    # The month is still open: no value yet, so a before/after comparison reveals nobody's answer.
    assert client.get(f"/api/public/dashboards/{slug}").json()["kpis"][0]["data_status"] == "collecting"
    month = surveys.current_period()
    monkeypatch.setattr(surveys, "current_period", lambda: "9999-12")  # the month has ended
    view = client.get(f"/api/public/dashboards/{slug}").json()
    [k] = view["kpis"]
    assert k["data_status"] == "available"
    [pt] = k["points"]
    assert pt["value"] == 3.6 and pt["sample_size"] == 5  # (5+3+4+5+1)/5
    assert k["source"]["kind"] == "survey" and k["source"]["total_responses"] == 5
    csv_text = client.get(f"/api/public/dashboards/{slug}/export.csv").text
    assert "回答数" in csv_text and ",5\r\n" in csv_text
    # No endpoint lists individual answers; the survey view has counts only.
    sv = client.get(f"/api/surveys/{s['id']}", headers=as_user(VISITOR)).json()
    assert "responses" not in sv and sv["periods"][0] == {"period": month, "responses": 5, "published": True}
    for bad in (0, 6, 2.5):
        assert client.post(f"/api/surveys/{s['id']}/responses", json={"value": bad}, headers=as_user(VISITOR)).status_code == 422


def test_closed_survey_stops_answers_and_keeps_points(client, monkeypatch):
    card, kpi, _, s = _survey(client, monkeypatch)
    client.post(f"/api/surveys/{s['id']}/open", headers=as_user(PARENT))
    for uid in (PARENT, VISITOR, STAFF, MANAGER, BUSINESS):
        client.post(f"/api/surveys/{s['id']}/responses", json={"value": 4}, headers=as_user(uid))
    assert client.post(f"/api/surveys/{s['id']}/close", headers=as_user(PARENT)).json()["status"] == "closed"
    assert client.post(f"/api/surveys/{s['id']}/responses", json={"value": 4}, headers=as_user(PARENT)).status_code == 409
    kpi_after = client.get(f"/api/issue-cards/{card['id']}", headers=as_user(PARENT)).json()["kpis"][0]
    assert kpi_after["points"][0]["value"] == 4 and kpi_after["survey"]["status"] == "closed"


def test_one_extreme_number_does_not_move_the_kpi(client):
    card = _card(client)
    kpi = card["kpis"][0]
    s = client.post(f"/api/kpis/{kpi['id']}/surveys", json={"kind": "observation", "title": "待ち時間", "question": "何分待ちましたか",
                                                         "answer_type": "number", "unit": "分", "min_value": 0, "max_value": 180},
                    headers=as_user(PARENT)).json()
    client.post(f"/api/surveys/{s['id']}/open", headers=as_user(PARENT))
    for uid, v in [(PARENT, 10), (VISITOR, 12), (STAFF, 15), (MANAGER, 11), (BUSINESS, 180)]:
        client.post(f"/api/surveys/{s['id']}/responses", json={"value": v}, headers=as_user(uid))
    closed = client.post(f"/api/surveys/{s['id']}/close", headers=as_user(PARENT)).json()
    assert closed["aggregation"] == "median"
    pts = client.get(f"/api/issue-cards/{card['id']}", headers=as_user(PARENT)).json()["kpis"][0]["points"]
    assert [p["value"] for p in pts] == [12]  # the mean would be 45.6
