"""つくる → 公開 → 採用 の後半: 施策ニュース化 (F-14)、注釈と前後比較 (F-12)、コミュニティとの紐づけ."""
import sqlite3

from app.agents import opendata, policy_news, shaping

from .conftest import as_user
from .test_flow import PARENT, PLAN, STAFF, VISITOR, _card_from_conversation

MANAGER = 4  # member of community 1 in the seed

NEWS_DRAFT = {
    "title": "近所で外遊びできる場所を増やします",
    "body": "区民から、近所に子どもが思い切り遊べる場所がないという声が寄せられました。……",
    "category": "子育て",
    "annotation_label": "校庭開放の時間帯を拡大",
}


def _published(client, monkeypatch):
    _, card = _card_from_conversation(client, monkeypatch)
    kpi = card["kpis"][0]
    spots = next(d for d in client.get("/api/datasets").json()["items"] if d["file_path"] == "sample_play_spaces.csv")
    monkeypatch.setattr(opendata, "search", lambda k, cat: {"candidates": [{"dataset_id": spots["id"], "reason": "開設日がある"}]})
    monkeypatch.setattr(shaping, "propose_plan", lambda k, cols, sample: PLAN)
    search = client.post(f"/api/kpis/{kpi['id']}/dataset-search", headers=as_user(PARENT)).json()
    plan = client.post(f"/api/kpis/{kpi['id']}/shaping-plans", json={"dataset_id": spots["id"], "search_proposal_id": search["id"]},
                       headers=as_user(PARENT)).json()
    client.post(f"/api/shaping-plans/{plan['id']}/adopt", json={}, headers=as_user(PARENT))
    pub = client.post(f"/api/issue-cards/{card['id']}/dashboard/publish", json={}, headers=as_user(PARENT)).json()
    return card, pub


def _adopted(client, monkeypatch):
    card, pub = _published(client, monkeypatch)
    r = client.post(f"/api/dashboards/{pub['dashboard']['id']}/decisions",
                    json={"state": "adopted", "reason": "校庭開放の時間帯の拡大を検討します"}, headers=as_user(STAFF))
    assert r.status_code == 201
    return card, pub


def _publish_body(**over):
    return {**NEWS_DRAFT, "start_period": "2026-04", **over}


def test_policy_news_needs_staff_and_adoption(client, monkeypatch):
    card, pub = _published(client, monkeypatch)
    monkeypatch.setattr(policy_news, "draft", lambda ctx, cats: NEWS_DRAFT)
    assert client.post(f"/api/issue-cards/{card['id']}/policy-news-drafts", headers=as_user(STAFF)).status_code == 409
    client.post(f"/api/dashboards/{pub['dashboard']['id']}/decisions", json={"state": "adopted", "reason": "x"}, headers=as_user(STAFF))
    assert client.post(f"/api/issue-cards/{card['id']}/policy-news-drafts", headers=as_user(PARENT)).status_code == 403
    assert client.post(f"/api/issue-cards/{card['id']}/policy-news", json=_publish_body(), headers=as_user(PARENT)).status_code == 403


def test_policy_news_publish_links_annotates_and_notifies(client, monkeypatch):
    card, pub = _adopted(client, monkeypatch)
    seen = {}
    monkeypatch.setattr(policy_news, "draft", lambda ctx, cats: seen.update(ctx=ctx, cats=cats) or NEWS_DRAFT)
    prop = client.post(f"/api/issue-cards/{card['id']}/policy-news-drafts", headers=as_user(STAFF)).json()
    assert prop["kind"] == "policy_news_draft" and prop["status"] == "proposed"
    assert "近所に子どもが思い切り遊べる場所がありません" not in seen["ctx"]  # individual quotes stay out of the official article
    assert "未取得人" not in seen["ctx"] and "現在 未取得（目標 未設定）" in seen["ctx"]  # no unit after a missing value
    assert "校庭開放の時間帯の拡大を検討します" in seen["ctx"] and "子育て" in seen["cats"]
    # Nothing is published while the draft is only proposed (F-21).
    assert all(n["kind"] != "policy" for n in client.get("/api/news").json()["items"])
    before = {n["id"] for n in client.get("/api/me/notifications", headers=as_user(PARENT)).json()["items"]}

    out = client.post(f"/api/issue-cards/{card['id']}/policy-news", json=_publish_body(proposal_id=prop["id"]),
                      headers=as_user(STAFF))
    assert out.status_code == 201, out.text
    news_id = out.json()["news_id"]
    p = client.get(f"/api/ai-proposals/{prop['id']}", headers=as_user(STAFF)).json()
    assert p["status"] == "adopted" and p["decision_method"] == "manual" and p["result_ref"] == f"news:{news_id}"
    assert client.post(f"/api/issue-cards/{card['id']}/policy-news", json=_publish_body(proposal_id=prop["id"]),
                       headers=as_user(STAFF)).status_code == 409

    # News → issue card / dashboard.
    news = client.get(f"/api/news/{news_id}").json()
    assert news["kind"] == "policy" and news["issue_card_id"] == card["id"] and news["is_sample"] is False
    assert news["issue_card"] == {"id": card["id"], "title": card["title"], "dashboard_slug": pub["dashboard"]["public_slug"]}
    # Issue card / dashboard → news.
    c = client.get(f"/api/issue-cards/{card['id']}", headers=as_user(VISITOR)).json()
    assert [n["id"] for n in c["policy_news"]] == [news_id]
    view = client.get(f"/api/public/dashboards/{pub['dashboard']['public_slug']}").json()
    assert [n["id"] for n in view["policy_news"]] == [news_id]

    # Policy-start annotation is added automatically.
    [ann] = view["annotations"]
    assert (ann["kind"], ann["period"], ann["label"], ann["news_id"]) == ("policy_start", "2026-04", NEWS_DRAFT["annotation_label"], news_id)
    assert view["comparisons"][0]["annotation_id"] == ann["id"]

    # Author and community members are notified with a link to the news.
    for uid in (PARENT, MANAGER):
        notes = client.get("/api/me/notifications", headers=as_user(uid)).json()["items"]
        assert notes[0]["link"] == f"/news/{news_id}" and "施策を始めました" in notes[0]["text"]
    assert not [n for n in client.get("/api/me/notifications", headers=as_user(STAFF)).json()["items"] if n["link"] == f"/news/{news_id}"]
    assert {n["id"] for n in client.get("/api/me/notifications", headers=as_user(PARENT)).json()["items"]} > before

    me = client.get("/api/me", headers=as_user(PARENT)).json()
    assert me["issue_cards"][0]["status_label"] == "採用" and me["issue_cards"][0]["policy_news"][0]["id"] == news_id


def test_edited_policy_news_is_adopted_edited(client, monkeypatch):
    card, _ = _adopted(client, monkeypatch)
    monkeypatch.setattr(policy_news, "draft", lambda ctx, cats: NEWS_DRAFT)
    prop = client.post(f"/api/issue-cards/{card['id']}/policy-news-drafts", headers=as_user(STAFF)).json()
    client.post(f"/api/issue-cards/{card['id']}/policy-news",
                json=_publish_body(proposal_id=prop["id"], title="近所で外遊びできる場所を増やします（第1弾）"), headers=as_user(STAFF))
    assert client.get(f"/api/ai-proposals/{prop['id']}", headers=as_user(STAFF)).json()["status"] == "adopted_edited"


def test_policy_news_can_be_written_by_hand_when_ai_is_unavailable(client, monkeypatch):
    card, _ = _adopted(client, monkeypatch)
    r = client.post(f"/api/issue-cards/{card['id']}/policy-news-drafts", headers=as_user(STAFF))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_unavailable"
    out = client.post(f"/api/issue-cards/{card['id']}/policy-news",
                      json=_publish_body(title="手入力の施策ニュース", annotation_label="施策開始"), headers=as_user(STAFF))
    assert out.status_code == 201
    assert client.get(f"/api/news/{out.json()['news_id']}").json()["issue_card"]["id"] == card["id"]


def test_before_after_comparison_does_not_claim_causality(client, monkeypatch):
    card, pub = _published(client, monkeypatch)
    view = client.post(f"/api/issue-cards/{card['id']}/dashboard/annotations",
                       json={"period": "2026-04", "label": "案内表示を追加", "kind": "event"}, headers=as_user(PARENT)).json()
    assert client.post(f"/api/issue-cards/{card['id']}/dashboard/annotations", json={"period": "2026-04", "label": "x"},
                       headers=as_user(VISITOR)).status_code == 403
    assert "因果関係は未確認" in view["causality_note"]
    [cmp] = view["comparisons"]
    rows = {r["name"]: r for r in cmp["kpis"]}
    spots = rows["外遊びできる場所の数"]
    pts = next(k for k in view["kpis"] if k["name"] == "外遊びできる場所の数")["points"]
    before = [p["value"] for p in pts if p["period"] < "2026-04"]
    after = [p["value"] for p in pts if p["period"] >= "2026-04"]
    assert spots["state"] == "ok" and spots["before_value"] == before[-1] and spots["after_value"] == after[-1]
    assert spots["after_periods"] == len(after)
    assert spots["after_per_period"] == (after[-1] - before[-1]) / len(after)
    assert spots["before_per_period"] == (before[-1] - before[-6]) / 5
    assert rows["プレーパークの日別平均利用者数"]["state"] == "no_data"
    later = client.post(f"/api/issue-cards/{card['id']}/dashboard/annotations",
                        json={"period": "2027-01", "label": "次の施策"}, headers=as_user(STAFF)).json()
    assert later["comparisons"][1]["kpis"][0]["state"] == "no_after"


def test_card_links_to_recommended_or_new_community(client, monkeypatch):
    _, card = _card_from_conversation(client, monkeypatch)
    # Cards can be created without a community; an unknown one is refused.
    assert client.post("/api/issue-cards", json={"title": "t", "community_id": 999}, headers=as_user(PARENT)).status_code == 422
    loose = client.post("/api/issue-cards", json={"title": "ニュースから作った課題", "origin_kind": "news", "origin_ref": "1"},
                        headers=as_user(PARENT)).json()
    assert loose["community_id"] is None

    from app.agents import recommend
    monkeypatch.setattr(recommend, "recommend", lambda i, c, k: {"communities": [{"id": 2, "reason": "駅の段差の話題が同じ"}], "issue_cards": []})
    conv_id = int(card["origin_ref"])
    reco = client.post(f"/api/conversations/{conv_id}/recommendations", headers=as_user(PARENT)).json()
    linked_card = client.post("/api/issue-cards", json={"title": "会話から作った課題", "origin_kind": "conversation",
                                                         "origin_ref": str(conv_id), "focus_area": "AREA-1"}, headers=as_user(PARENT)).json()
    cands = client.get(f"/api/issue-cards/{linked_card['id']}/community-candidates", headers=as_user(PARENT)).json()
    assert cands["ai_recommendation"]["id"] == reco["id"] and cands["ai_recommendation"]["items"][0]["id"] == 2
    assert [m["id"] for m in cands["matches"]] == [1]  # same focus area (AREA-1), rule-based

    assert client.put(f"/api/issue-cards/{linked_card['id']}/community", json={"community_id": 2},
                      headers=as_user(VISITOR)).status_code == 403
    assert client.put(f"/api/issue-cards/{linked_card['id']}/community",
                      json={"community_id": 3, "recommendation_proposal_id": reco["id"]}, headers=as_user(PARENT)).status_code == 422
    out = client.put(f"/api/issue-cards/{linked_card['id']}/community",
                     json={"community_id": 2, "recommendation_proposal_id": reco["id"]}, headers=as_user(PARENT)).json()
    assert out["community"] == {"id": 2, "name": "ベビーカーで歩く渋谷"}
    p = client.get(f"/api/ai-proposals/{reco['id']}", headers=as_user(PARENT)).json()
    assert p["status"] == "adopted" and p["result_ref"] == f"issue_card:{linked_card['id']}/community:2"
    assert client.get("/api/communities/2", headers=as_user(PARENT)).json()["joined"] is True

    # A new community, chosen by the person.
    bad = client.post("/api/communities", json={"name": "x", "focus_area": "AREA-9"}, headers=as_user(PARENT))
    assert bad.status_code == 422
    new = client.post("/api/communities", json={"name": "代々木の子育て", "description": "代々木周辺で子育てする人の集まり",
                                                 "category": "子育て", "focus_area": "AREA-1", "area": "代々木"}, headers=as_user(PARENT))
    assert new.status_code == 201 and new.json()["joined"] is True and new.json()["member_count"] == 1
    assert client.post("/api/communities", json={"name": "代々木の子育て"}, headers=as_user(VISITOR)).status_code == 409
    out = client.put(f"/api/issue-cards/{loose['id']}/community", json={"community_id": new.json()["id"]}, headers=as_user(PARENT)).json()
    assert out["community_id"] == new.json()["id"]
    assert [c["id"] for c in client.get(f"/api/communities/{new.json()['id']}", headers=as_user(PARENT)).json()["issue_cards"]] == [loose["id"]]


def test_staff_view_counts_linked_community_members(client, monkeypatch):
    card, _ = _published(client, monkeypatch)  # created with community 1
    [item] = client.get("/api/staff/dashboards", headers=as_user(STAFF)).json()["items"]
    assert item["community_id"] == 1 and item["community_members"] == 3  # manager, staff and the author who joined


def test_old_database_is_migrated(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    monkeypatch.setenv("APP_DB_PATH", str(path))
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, display_name TEXT NOT NULL, role TEXT NOT NULL,
            attribute TEXT NOT NULL DEFAULT '', department TEXT NOT NULL DEFAULT '');
        CREATE TABLE annotations (id INTEGER PRIMARY KEY, dashboard_id INTEGER NOT NULL, period TEXT NOT NULL,
            label TEXT NOT NULL, created_by INTEGER NOT NULL, created_at REAL NOT NULL);
        INSERT INTO users VALUES (1, 'a', 'participant', '', '');
        INSERT INTO annotations VALUES (1, 1, '2026-04', '施策開始', 1, 0);
    """)
    conn.close()
    from app.db import get_conn, init_db

    init_db()
    init_db()  # idempotent
    with get_conn() as c:
        row = c.execute("SELECT * FROM annotations").fetchone()
        assert (row["label"], row["kind"], row["news_id"]) == ("施策開始", "event", None)
        assert c.execute("SELECT display_name FROM users").fetchone()[0] == "a"
