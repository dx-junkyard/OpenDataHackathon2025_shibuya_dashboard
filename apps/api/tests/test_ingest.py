"""Real-data ingest (F-01 / F-08) with the network replaced by fixed responses."""
import json

import pytest

from app.agents import shaping
from app.db import get_conn
from app.ingest import http, news, opendata

from .conftest import as_user
from .test_flow import PARENT, _card_from_conversation

CKAN = opendata.TOKYO_CKAN
HUB = opendata.SHIBUYA_HUB
SRC = opendata.CKAN_SOURCES[0]
HUB_SRC = opendata.HUB_SOURCES[0]
CSV_URL = "https://www.fukushi.metro.tokyo.lg.jp/documents/d/fukushi/flat_r81007.csv"

PACKAGE = {"result": {
    "name": SRC.package_id, "title": "赤ちゃん・ふらっと一覧", "license_id": "CC-BY-4.0",
    "license_title": "クリエイティブ・コモンズ 表示（CC BY）", "metadata_modified": "2025-12-12T07:46:10",
    "organization": {"title": "東京都福祉局"},
    "resources": [{"format": "XLS", "url": "https://example.invalid/old.xlsx"},
                  {"format": "CSV", "url": "https://www.fukushi.metro.tokyo.lg.jp/documents/d/fukushi/old_csv",
                   "last_modified": "2017-09-21T15:00:00"}],
}}
LANDING = f"""<html><main><h1>赤ちゃん・ふらっと事業</h1><p>更新日</p><p>2026年10月7日</p>
<a href="/documents/d/fukushi/flat_r81007.csv">{SRC.landing_link_text}</a></main></html>"""
FLAT_CSV = ("登録番号,地域,施設名,設置者\n4,渋谷区,東京ウィメンズプラザ,東京都生活文化局\n156,渋谷区,西武渋谷店,株式会社そごう・西武\n"
            "88,千代田区,いずみこどもプラザ,千代田区\n").encode("cp932")
HUB_ITEM = {"properties": {"title": "子育て関連施設の利用状況", "license": "CC-BY-4.0", "modified": 1758527437000,
                           "description": "<p>利用者数です。</p><p>・2025年4月1日時点の情報です。</p>"}}
HUB_CSV = "﻿年度,施設名,月,利用者数\n2023,本町子育て支援センター,4,237\n".encode("utf-8")


class FakeWeb:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def fetch(self, url):
        self.calls.append(url)
        for prefix, body in self.routes.items():
            if url.startswith(prefix):
                if isinstance(body, int):
                    raise http.FetchError(url, f"HTTP {body}")
                data = json.dumps(body, ensure_ascii=False).encode() if isinstance(body, dict) else body
                return http.Fetched(url=url, content=data if isinstance(data, bytes) else data.encode(), content_type="")
        raise http.FetchError(url, "HTTP 404")


def _web(**overrides):
    routes = {
        f"{CKAN}/api/3/action/package_search": {"result": {"count": 0, "results": []}},
        f"{HUB}/api/search/v1/collections/dataset/items?": {"numberMatched": 0, "features": []},
        f"{CKAN}/api/3/action/package_show": PACKAGE,
        PACKAGE["result"]["resources"][1]["url"]: 404,
        SRC.landing_page: LANDING,
        CSV_URL: FLAT_CSV,
        f"{HUB}/api/search/v1/collections/dataset/items/{HUB_SRC.item_id}": HUB_ITEM,
        f"{HUB}/api/download/v1/items/{HUB_SRC.item_id}/csv": HUB_CSV,
    }
    routes.update(overrides)
    return FakeWeb(routes)


def _ingest(monkeypatch, tmp_path, web):
    monkeypatch.setattr(http, "fetch", web.fetch)
    with get_conn() as conn:
        return opendata.run(conn, str(tmp_path / "datasets"))


def _runs(kind="dataset"):
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM ingest_runs WHERE kind = ? ORDER BY id", (kind,))]


def test_dataset_is_registered_with_source_metadata(client, monkeypatch, tmp_path):
    assert _ingest(monkeypatch, tmp_path, _web()) == {SRC.package_id: "ok", HUB_SRC.item_id: "ok"}
    items = {d["title"]: d for d in client.get("/api/datasets").json()["items"]}
    flat = items["赤ちゃん・ふらっと一覧"]
    assert flat["is_sample"] is False and flat["publisher"] == "東京都福祉局" and flat["license"] == "CC-BY-4.0"
    assert flat["source_url"] == f"{CKAN}/dataset/{SRC.package_id}" and flat["file_url"] == CSV_URL
    # The as-of date comes from the bureau's page, not from the stale CKAN resource date.
    assert flat["updated_on"] == "2026-10-07"
    assert "404" in flat["description"] and SRC.landing_page in flat["description"]
    hub = items["子育て関連施設の利用状況"]
    assert hub["publisher"] == "渋谷区" and hub["license"] == "CC-BY-4.0" and hub["updated_on"] == "2025-04-01"
    # The search scope is recorded, including what was not found.
    statuses = {r["source"]: r["status"] for r in _runs()}
    assert statuses["検索: 東京都オープンデータカタログ（渋谷区）「授乳」"] == "not_found"
    assert client.get("/api/ingest-runs?kind=dataset").json()["items"][0]["kind"] == "dataset"
    # Sample data stays and stays labelled.
    assert any(d["is_sample"] for d in items.values())


def test_reingest_of_the_same_file_is_unchanged_and_a_new_version_adds_a_snapshot(client, monkeypatch, tmp_path):
    _ingest(monkeypatch, tmp_path, _web())
    assert _ingest(monkeypatch, tmp_path, _web())[SRC.package_id] == "unchanged"
    newer = LANDING.replace("2026年10月7日", "2026年11月4日")
    more = FLAT_CSV + "200,渋谷区,新しい施設,渋谷区\n".encode("cp932")
    assert _ingest(monkeypatch, tmp_path, _web(**{SRC.landing_page: newer, CSV_URL: more}))[SRC.package_id] == "ok"
    with get_conn() as conn:
        snaps = [r["as_of"] for r in conn.execute(
            "SELECT as_of FROM dataset_snapshots s JOIN datasets d ON d.id = s.dataset_id WHERE d.title = ? ORDER BY as_of",
            ("赤ちゃん・ふらっと一覧",))]
    assert snaps == ["2026-10-07", "2026-11-04"]


def test_unreachable_source_is_recorded_and_not_filled_in(client, monkeypatch, tmp_path):
    web = _web(**{SRC.landing_page: 503})
    assert _ingest(monkeypatch, tmp_path, web)[SRC.package_id] == "failed"
    failed = [r for r in _runs() if r["status"] == "failed"]
    assert len(failed) == 1 and "503" in failed[0]["message"]
    titles = [d["title"] for d in client.get("/api/datasets").json()["items"]]
    assert "赤ちゃん・ふらっと一覧" not in titles


def test_missing_license_is_not_registered(client, monkeypatch, tmp_path):
    pkg = {"result": {**PACKAGE["result"], "license_id": "", "license_title": ""}}
    assert _ingest(monkeypatch, tmp_path, _web(**{f"{CKAN}/api/3/action/package_show": pkg}))[SRC.package_id] == "failed"


def test_spot_count_kpi_from_real_dataset_snapshots(client, monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATASETS_DIR", str(tmp_path / "datasets"))
    _ingest(monkeypatch, tmp_path, _web())
    _ingest(monkeypatch, tmp_path, _web(**{SRC.landing_page: LANDING.replace("2026年10月7日", "2026年11月4日"),
                                           CSV_URL: FLAT_CSV + "200,渋谷区,新しい施設,渋谷区\n".encode("cp932")}))
    _, card = _card_from_conversation(client, monkeypatch)
    kpi = card["kpis"][0]
    flat = next(d for d in client.get("/api/datasets").json()["items"] if d["title"] == "赤ちゃん・ふらっと一覧")
    plan = {"feasible": True, "table_index": 0, "header_row": 0, "unpivot_columns": [], "date_column": "取得時点",
            "value_column": "", "filter_column": "", "filter_value": "", "aggregation": "count_rows",
            "period": "month", "cumulative": False, "steps": ["取得時点ごとに数える"]}
    notes = []
    monkeypatch.setattr(shaping, "propose_plan", lambda k, tables, note: notes.append(note) or plan)
    prop = client.post(f"/api/kpis/{kpi['id']}/shaping-plans", json={"dataset_id": flat["id"]}, headers=as_user(PARENT)).json()
    assert "2026-10-07、2026-11-04" in notes[0]
    p = prop["payload"]
    assert p["snapshots"] == ["2026-10-07", "2026-11-04"] and "取得時点" in p["columns"]
    assert any("「地域」に渋谷区以外（千代田区）" in w for w in p["warnings"])  # area filter missing
    fixed = {**plan, "filter_column": "地域", "filter_value": "渋谷区"}
    adopted = client.post(f"/api/shaping-plans/{prop['id']}/adopt", json={"plan": fixed}, headers=as_user(PARENT)).json()
    assert adopted["points"] == [{"period": "2026-10", "value": 2.0}, {"period": "2026-11", "value": 3.0}]
    assert client.get(f"/api/ai-proposals/{prop['id']}", headers=as_user(PARENT)).json()["status"] == "adopted_edited"
    pub = client.post(f"/api/issue-cards/{card['id']}/dashboard/publish", json={}, headers=as_user(PARENT)).json()
    view = client.get(f"/api/public/dashboards/{pub['dashboard']['public_slug']}").json()
    spot = next(k for k in view["kpis"] if k["name"] == "スポット設置数")
    assert spot["data_status"] == "available" and spot["source"]["is_sample"] is False
    assert spot["source"]["license"] == "CC-BY-4.0"


# ---------------------------------------------------------------- news

LIST_HTML = """<main><ul class="m-list-links">
<li><a href="/kodomo/kosodate/akachan.html" class="link-inner is-link" data-gtm><p class="date">2026年10月19日</p>
<p class="title">授乳室の案内を更新しました</p><ul class="label-list"><li>子育て・教育・生涯学習</li></ul></a></li>
<li><a href="/contents/koho-news/" class="link-inner is-link" data-gtm><p class="date">2026年10月13日</p>
<p class="title">しぶや区ニュースを公開しました</p><ul class="label-list"><li>区政情報</li></ul></a></li>
<li><a href="/kenko/event.html#h2-x" class="link-inner is-link" data-gtm><p class="date">2026年10月1日</p>
<p class="title">健康イベント</p><ul class="label-list"><li>健康・福祉</li></ul></a></li>
</ul></main>"""


def _article(lead, body, dept):
    return (f'<main><div class="hdg"><h1 class="e-hdg-lv1">t</h1></div><p class="text">{lead}</p>'
            f'<div class="u-rich-editor-contents rich-text"><div class="rich-text-wrap"><p>{body}</p></div></div>'
            f'<div class="info-wrap"><h2 class="e-hdg-lv2">お問い合わせ</h2><div><h4 class="e-hdg-lv4">{dept}</h4>'
            f'<table><tr><th>電話</th><td>03-0000-0000</td></tr></table></div></div></main>')


def _news_web():
    return FakeWeb({
        news.LISTS[0]: LIST_HTML,
        news.LISTS[1]: LIST_HTML,
        f"{news.SITE}/kodomo/kosodate/akachan.html": _article("区内の授乳室の一覧です。", "設置場所を更新しました。", "子育て支援課子育て支援係"),
        f"{news.SITE}/kenko/event.html": _article("", "健康づくりのイベントです。", ""),
    })


def test_news_from_the_city_site(client, monkeypatch):
    web = _news_web()
    monkeypatch.setattr(http, "fetch", web.fetch)
    with get_conn() as conn:
        assert news.run(conn, delay=0) == {"ok": 2, "unchanged": 0, "failed": 1}
    items = {n["title"]: n for n in client.get("/api/news").json()["items"]}
    a = items["授乳室の案内を更新しました"]
    assert a["is_sample"] is False and a["department"] == "子育て支援課子育て支援係"
    assert a["published_at"] == "2026-10-19" and a["category"] == "子育て・教育・生涯学習" and a["focus_area"] == "AREA-1"
    assert a["source_url"] == f"{news.SITE}/kodomo/kosodate/akachan.html" and a["source_name"] == "渋谷区ホームページ"
    assert a["body"] == "区内の授乳室の一覧です。\n設置場所を更新しました。"
    e = items["健康イベント"]
    assert e["source_url"].endswith("#h2-x") and e["focus_area"] == "" and e["department"] == ""
    assert "しぶや区ニュースを公開しました" not in items
    assert any(r["status"] == "failed" and r["source"].endswith("/contents/koho-news/") for r in _runs("news"))
    # The sample articles remain, labelled.
    assert any(n["is_sample"] for n in items.values())
    with get_conn() as conn:
        assert news.run(conn, delay=0) == {"ok": 0, "unchanged": 2, "failed": 1}


@pytest.mark.parametrize("html_text,expected", [("<p>更新日</p><p>令和8年10月7日</p>", "2026-10-07"), ("<p>なし</p>", None)])
def test_as_of_date_from_page(html_text, expected):
    from app import jpdate
    from app.ingest import html

    assert jpdate.find_iso_date(html.page_text(html_text), after="更新日") == expected


def test_a_new_dataset_version_updates_the_kpi_with_the_edited_plan(client, monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATASETS_DIR", str(tmp_path / "datasets"))
    _ingest(monkeypatch, tmp_path, _web())
    _, card = _card_from_conversation(client, monkeypatch)
    kpi = card["kpis"][0]
    flat = next(d for d in client.get("/api/datasets").json()["items"] if d["title"] == "赤ちゃん・ふらっと一覧")
    plan = {"feasible": True, "table_index": 0, "header_row": 0, "unpivot_columns": [], "date_column": "取得時点",
            "value_column": "", "filter_column": "", "filter_value": "", "aggregation": "count_rows",
            "period": "month", "cumulative": False, "steps": []}
    monkeypatch.setattr(shaping, "propose_plan", lambda k, tables, note: plan)
    prop = client.post(f"/api/kpis/{kpi['id']}/shaping-plans", json={"dataset_id": flat["id"]}, headers=as_user(PARENT)).json()
    edited = {**plan, "filter_column": "地域", "filter_value": "渋谷区"}  # the person's fix, not the AI's plan
    client.post(f"/api/shaping-plans/{prop['id']}/adopt", json={"plan": edited}, headers=as_user(PARENT))

    # The next scheduled ingest finds a new version: the KPI follows it with the edited plan.
    _ingest(monkeypatch, tmp_path, _web(**{SRC.landing_page: LANDING.replace("2026年10月7日", "2026年11月4日"),
                                           CSV_URL: FLAT_CSV + "200,渋谷区,新しい施設,渋谷区\n".encode("cp932")}))
    k = client.get(f"/api/issue-cards/{card['id']}/dashboard", headers=as_user(PARENT)).json()["kpis"][0]
    assert [(p["period"], p["value"]) for p in k["points"]] == [("2026-10", 2.0), ("2026-11", 3.0)]
    assert k["data_as_of"] == "2026-11-04" and k["refresh_error"] == ""
    notes = [n["text"] for n in client.get("/api/me/notifications", headers=as_user(PARENT)).json()["items"]]
    assert any("2026-11-04 時点の版に更新" in t for t in notes)

    # A later version renamed the filter column: the old points stay and the card says so.
    renamed = "登録番号,区市町村,施設名,設置者\n4,渋谷区,東京ウィメンズプラザ,東京都\n".encode("cp932")
    _ingest(monkeypatch, tmp_path, _web(**{SRC.landing_page: LANDING.replace("2026年10月7日", "2026年12月2日"), CSV_URL: renamed}))
    k = client.get(f"/api/issue-cards/{card['id']}/dashboard", headers=as_user(PARENT)).json()["kpis"][0]
    assert [p["value"] for p in k["points"]] == [2.0, 3.0] and k["data_as_of"] == "2026-11-04"
    assert "2026-12-02 時点のデータを反映できませんでした" in k["refresh_error"]
