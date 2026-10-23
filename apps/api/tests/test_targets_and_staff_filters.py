"""KPI の目標到達の通知 (UXR-23) と区職員ビューの担当課・地域での絞り込み (UXR-18)."""

from app.routes import surveys

from .conftest import as_user

PARENT, VISITOR, STAFF, MANAGER, BUSINESS = 1, 2, 3, 4, 5


def _card_with_survey_kpi(client, title="授乳場所が見つかるまでの時間", place="恵比寿駅周辺／外出中"):
    card = client.post("/api/issue-cards", json={
        "title": title, "place_time": place, "community_id": 1, "origin_kind": "news", "origin_ref": "1",
        "kpis": [{"name": "見つかるまでの時間", "unit": "分"}]}, headers=as_user(PARENT)).json()
    kpi = card["kpis"][0]
    s = client.post(f"/api/kpis/{kpi['id']}/surveys", json={
        "title": "見つかるまでの時間", "question": "何分かかりましたか", "answer_type": "number",
        "unit": "分", "min_value": 0, "max_value": 180}, headers=as_user(PARENT)).json()
    client.post(f"/api/surveys/{s['id']}/open", headers=as_user(PARENT))
    return card, kpi, s


def _month(client, monkeypatch, survey_id, month, value):
    """Everyone answers `value` in `month`; the month then ends (published on the next read)."""
    monkeypatch.setattr(surveys, "current_period", lambda: month)
    for uid in (PARENT, VISITOR, STAFF, MANAGER, BUSINESS):
        client.post(f"/api/surveys/{survey_id}/responses", json={"value": value}, headers=as_user(uid))
    monkeypatch.setattr(surveys, "current_period", lambda: month + "~")
    client.get(f"/api/surveys/{survey_id}", headers=as_user(PARENT))


def _target_notes(client, uid):
    return [n for n in client.get("/api/me/notifications", headers=as_user(uid)).json()["items"] if "目標" in n["text"]]


def test_reaching_a_decrease_target_notifies_once_without_claiming_a_cause(client, monkeypatch):
    card, kpi, s = _card_with_survey_kpi(client)
    r = client.put(f"/api/kpis/{kpi['id']}/target", json={"target_value": 15, "target_direction": "decrease"},
                   headers=as_user(PARENT))
    assert r.status_code == 200 and r.json()["target_direction"] == "decrease"
    _month(client, monkeypatch, s["id"], "2026-07", 30)  # 30 min: above the target, not reached
    assert _target_notes(client, PARENT) == []
    _month(client, monkeypatch, s["id"], "2026-08", 10)  # 10 min: reached
    notes = _target_notes(client, PARENT)
    assert len(notes) == 1 and "15分 以下" in notes[0]["text"] and "効果かどうかは確認されていません" in notes[0]["text"]
    assert notes[0]["link"] == f"/issues/{card['id']}"
    assert len(_target_notes(client, MANAGER)) == 1  # community members are told too
    _month(client, monkeypatch, s["id"], "2026-09", 12)  # still reached: no second notification
    assert len(_target_notes(client, PARENT)) == 1
    k = client.get(f"/api/issue-cards/{card['id']}/dashboard", headers=as_user(PARENT)).json()["kpis"][0]
    assert k["target_reached_period"] and k["target_direction"] == "decrease"


def test_falling_back_clears_the_mark_so_reaching_again_notifies_again(client, monkeypatch):
    card, kpi, s = _card_with_survey_kpi(client)
    client.put(f"/api/kpis/{kpi['id']}/target", json={"target_value": 20}, headers=as_user(PARENT))  # increase
    _month(client, monkeypatch, s["id"], "2026-07", 25)
    assert len(_target_notes(client, PARENT)) == 1
    _month(client, monkeypatch, s["id"], "2026-08", 5)
    k = client.get(f"/api/issue-cards/{card['id']}", headers=as_user(PARENT)).json()["kpis"][0]
    assert k["target_reached_period"] is None
    _month(client, monkeypatch, s["id"], "2026-09", 40)
    assert len(_target_notes(client, PARENT)) == 2


def test_staff_list_filters_by_department_and_area(client):
    a, _, _ = _card_with_survey_kpi(client, title="恵比寿の授乳場所", place="恵比寿駅周辺")
    b, _, _ = _card_with_survey_kpi(client, title="代々木の授乳場所", place="代々木上原周辺")
    for c in (a, b):
        client.post(f"/api/issue-cards/{c['id']}/dashboard/publish", json={"acknowledge_personal_info": True}, headers=as_user(PARENT))
    full = client.get("/api/staff/dashboards", headers=as_user(STAFF)).json()
    assert {i["title"] for i in full["items"]} == {"恵比寿の授乳場所", "代々木の授乳場所"}
    dept = full["items"][0]["departments"][0]  # the origin article's department
    assert dept in full["departments"]
    by_area = client.get("/api/staff/dashboards?area=恵比寿", headers=as_user(STAFF)).json()["items"]
    assert [i["title"] for i in by_area] == ["恵比寿の授乳場所"]
    assert len(client.get(f"/api/staff/dashboards?department={dept}", headers=as_user(STAFF)).json()["items"]) == 2
    assert client.get("/api/staff/dashboards?department=存在しない課", headers=as_user(STAFF)).json()["items"] == []
