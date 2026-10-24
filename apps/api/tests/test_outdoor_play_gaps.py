"""GAP-OP-1 (F-08: 同じデータの版の食い違い) と GAP-OP-2 (F-01: ニュースの注力分野の推定)."""
import json
import sqlite3

from app import llm
from app.agents import news_area
from app.agents import opendata as opendata_agent
from app.db import db_path, get_conn, init_db
from app.ingest import news, opendata

from .conftest import as_user
from .test_ingest import HUB_PARK_SRC, PARK_SRC, _ingest, _runs, _web

PARENT, STAFF = 1, 3


# ------------------------------------------------------------------ GAP-OP-1


def _parks(client):
    items = {d["title"]: d for d in client.get("/api/datasets").json()["items"]}
    return items["都市公園・都立公園一覧"], items["公園一覧"]


def test_versions_of_the_same_data_are_compared_and_the_differences_shown(client, monkeypatch, tmp_path):
    _ingest(monkeypatch, tmp_path, _web())
    catalog_version, hub_version = _parks(client)
    assert catalog_version["variant_group"] == hub_version["variant_group"] == opendata.PARKS_GROUP
    assert hub_version["updated_on"] == "2026-03-31"  # 「令和8年3月31日時点」 from the provider's description

    kinds = [(n["kind"], n["other_dataset_id"]) for n in catalog_version["variant_notes"]]
    assert ("other_version", hub_version["id"]) in kinds and ("row_count_differs", hub_version["id"]) in kinds
    texts = [n["text"] for n in catalog_version["variant_notes"]]
    assert "この版では「面積(㎡)」がすべて空欄です" in texts
    assert any("この版 2 行、別の版 3 行" in t and "提供者に確認" in t for t in texts)
    # The fuller version has no empty-column note, and says the other count too.
    hub_texts = [n["text"] for n in hub_version["variant_notes"]]
    assert not any("面積" in t for t in hub_texts) and any("この版 3 行、別の版 2 行" in t for t in hub_texts)
    # What was compared is recorded with the ingest.
    assert any(r["source"] == f"版の比較: {opendata.PARKS_GROUP}" and "違いあり" in r["message"] for r in _runs())


def test_same_versions_have_no_difference_notes(client, monkeypatch, tmp_path):
    same = ("﻿全国地方公共団体コード,No,名称,面積（平方メートル）\n131130,1,恵比寿東公園,2666\n"
            "131130,2,豊沢児童遊園地,345\n").encode("utf-8")
    from .test_ingest import PARK_CSV_URL

    _ingest(monkeypatch, tmp_path, _web(**{PARK_CSV_URL: same,
                                           f"{opendata.SHIBUYA_HUB}/api/download/v1/items/{HUB_PARK_SRC.item_id}/csv": same}))
    catalog_version, _ = _parks(client)
    assert [n["kind"] for n in catalog_version["variant_notes"]] == ["other_version"]
    assert any(r["source"] == f"版の比較: {opendata.PARKS_GROUP}" and "違いなし" in r["message"] for r in _runs())


def test_the_search_agent_sees_the_version_notes(client, monkeypatch, tmp_path):
    _ingest(monkeypatch, tmp_path, _web())
    catalog = client.get("/api/datasets").json()["items"]
    prompt = opendata_agent._catalog_prompt({"name": "公園の面積", "unit": "㎡", "measurement": "合計"}, catalog)
    assert "版の注意: この版では「面積(㎡)」がすべて空欄です" in prompt
    assert "空欄でない版を優先" in opendata_agent.SYSTEM


# ------------------------------------------------------------------ GAP-OP-2


def _add_news(title, category="施設案内", department="公園課公園整備係", body="本文"):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO news (title, body, category, department, source_name, is_sample, kind, published_at)"
            " VALUES (?,?,?,?,'渋谷区ホームページ',0,'local','2026-10-20')", (title, body, category, department))
        return cur.lastrowid


def test_unmapped_news_get_an_ai_estimate_with_its_reason(client, monkeypatch):
    park = _add_news("千原児童遊園地の整備内容について", body="子どもが遊べる遊具を新しくします。")
    tender = _add_news("競争入札参加資格登録説明会", category="事業者向け情報", department="契約課")
    seen = []

    def fake(article):
        seen.append(article["title"])
        if "遊園地" in article["title"]:
            return {"focus_area": "AREA-1", "reason": "子どもが遊べる遊具の整備の記事のため"}
        return {"focus_area": "", "reason": "入札の手続きの記事で、どの分野にも当たらない"}

    monkeypatch.setattr(news_area, "estimate", fake)
    assert news.classify_unassigned() == {"estimated": 1, "no_area": 1, "not_judged": 0}
    p = client.get(f"/api/news/{park}").json()
    assert p["focus_area"] == "AREA-1" and p["focus_area_source"] == "ai" and p["focus_area_source_label"] == "AI の推定"
    assert p["focus_area_reason"] == "子どもが遊べる遊具の整備の記事のため" and "子育て" in p["focus_area_label"]
    t = client.get(f"/api/news/{tender}").json()
    assert t["focus_area"] == "" and t["focus_area_source"] == "ai"  # judged: no area (not the same as 未判定)
    # Sample articles keep their own source and are not sent to the AI.
    assert all("サンプル" not in s and "遊び場の再整備" not in s for s in seen)
    # A second run does not re-judge anything.
    seen.clear()
    news.classify_unassigned()
    assert seen == []


def test_ai_unavailable_leaves_news_unjudged_and_says_so(client, monkeypatch):
    nid = _add_news("広尾公園スポーツ広場の利用を開始しました")

    def down(article):
        raise llm.LLMUnavailable("AI が設定されていません")

    monkeypatch.setattr(news_area, "estimate", down)
    out = news.classify_unassigned()
    assert out["estimated"] == 0 and out["not_judged"] >= 1
    n = client.get(f"/api/news/{nid}").json()
    assert n["focus_area"] == "" and n["focus_area_source"] == "" and n["focus_area_source_label"] == "未判定"
    assert any(r["source"] == "注力分野の推定" and r["status"] == "failed" for r in _runs("news"))


def test_news_can_be_filtered_by_focus_area_and_unassigned_is_counted(client, monkeypatch):
    nid = _add_news("千原児童遊園地の整備内容について")
    monkeypatch.setattr(news_area, "estimate", lambda a: {"focus_area": "AREA-1", "reason": "遊具の整備"})
    news.classify_unassigned()
    _add_news("区立七号通り公園の今後の利用")  # left 未判定
    out = client.get("/api/news?focus_area=AREA-1").json()
    assert nid in [i["id"] for i in out["items"]] and all(i["focus_area"] == "AREA-1" for i in out["items"])
    assert next(a for a in out["focus_areas"] if a["id"] == "AREA-1")["count"] >= 1
    assert out["unassigned_count"] >= 1
    un = client.get("/api/news?focus_area=unassigned").json()["items"]
    assert un and all(i["focus_area"] == "" for i in un)
    assert client.get("/api/news?focus_area=AREA-9").status_code == 422


def test_only_staff_can_correct_the_focus_area(client, monkeypatch):
    nid = _add_news("千原児童遊園地の整備内容について")
    monkeypatch.setattr(news_area, "estimate", lambda a: {"focus_area": "AREA-5", "reason": "公園の整備"})
    news.classify_unassigned()
    body = {"focus_area": "AREA-1", "reason": "子どもの遊び場の整備なので子育て"}
    assert client.put(f"/api/news/{nid}/focus-area", json=body, headers=as_user(PARENT)).status_code == 403
    r = client.put(f"/api/news/{nid}/focus-area", json=body, headers=as_user(STAFF))
    assert r.status_code == 200, r.text
    n = r.json()
    assert n["focus_area"] == "AREA-1" and n["focus_area_source"] == "person" and n["focus_area_source_label"] == "区職員が設定"
    assert n["focus_area_reason"] == body["reason"] and "子育て支援課" in n["focus_area_by"]
    # A later estimation run never overwrites a person's decision.
    monkeypatch.setattr(news_area, "estimate", lambda a: {"focus_area": "AREA-7", "reason": "x"})
    news.classify_unassigned()
    assert client.get(f"/api/news/{nid}").json()["focus_area"] == "AREA-1"
    assert client.put(f"/api/news/{nid}/focus-area", json={"focus_area": "AREA-9"}, headers=as_user(STAFF)).status_code == 422


def test_category_mapped_news_say_where_the_area_came_from(client, monkeypatch, tmp_path):
    from .test_ingest import _web as web_routes  # noqa: F401  (keeps the shared fixtures importable)

    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO news (title, body, category, focus_area, focus_area_source, focus_area_reason, department,"
            " source_name, is_sample, kind, published_at) VALUES ('防災訓練','本文','防災・安全','AREA-4','category',"
            "'区のホームページの分類「防災・安全」から','防災課','渋谷区ホームページ',0,'local','2026-10-01')")
        nid = cur.lastrowid
    n = client.get(f"/api/news/{nid}").json()
    assert n["focus_area_source_label"] == "区の分類から" and "防災・安全" in n["focus_area_reason"]


def test_an_existing_database_keeps_its_news_when_the_columns_are_added(client):
    nid = _add_news("既存の記事")
    with get_conn() as conn:  # simulate the table as it was before this change
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("CREATE TABLE news_old AS SELECT id, title, body, category, focus_area, department, source_url,"
                     " source_name, is_sample, kind, issue_card_id, published_at FROM news")
        conn.execute("DROP TABLE news")
        conn.execute("ALTER TABLE news_old RENAME TO news")
    init_db()
    with sqlite3.connect(db_path()) as c:
        cols = [r[1] for r in c.execute("PRAGMA table_info(news)")]
        assert "focus_area_source" in cols
        assert c.execute("SELECT title, focus_area_source FROM news WHERE id = ?", (nid,)).fetchone() == ("既存の記事", "")


def test_hub_download_being_prepared_is_retried_then_reported(client, monkeypatch, tmp_path):
    from app.ingest import http

    from .test_ingest import HUB_PARK_CSV, _web

    monkeypatch.setenv("HUB_DOWNLOAD_WAIT", "0")
    web = _web()
    url = f"{opendata.SHIBUYA_HUB}/api/download/v1/items/{HUB_PARK_SRC.item_id}/csv"
    calls = {"n": 0}

    def fetch(u):
        if u.startswith(url):
            calls["n"] += 1
            if calls["n"] < 3:  # the Hub is still generating the file
                raise http.FetchError(u, "HTTP 202")
            return http.Fetched(url=u, content=HUB_PARK_CSV, content_type="text/csv")
        return web.fetch(u)

    monkeypatch.setattr(http, "fetch", fetch)
    with get_conn() as conn:
        out = opendata.run(conn, str(tmp_path / "datasets"))
    assert out[HUB_PARK_SRC.item_id] == "ok" and calls["n"] == 3

    # Still not ready after every attempt: recorded as such, nothing registered from it.
    monkeypatch.setenv("HUB_DOWNLOAD_ATTEMPTS", "2")
    calls["n"] = -100
    with get_conn() as conn:
        assert opendata.ingest_hub(conn, str(tmp_path / "datasets"), HUB_PARK_SRC) == "failed"
    failed = [r for r in _runs() if r["status"] == "failed"]
    assert failed and "準備中" in failed[-1]["message"] and "2 回" in failed[-1]["message"]


def test_an_already_stored_version_joins_its_group_on_the_next_ingest(client, monkeypatch, tmp_path):
    from app.ingest import http

    from .test_ingest import _web

    # First run: only the catalog version exists in the group (as before this change).
    web = _web()
    hub_url = f"{opendata.SHIBUYA_HUB}/api/download/v1/items/{HUB_PARK_SRC.item_id}/csv"

    def without_hub(u):
        if u.startswith(hub_url):
            raise http.FetchError(u, "HTTP 500")
        return web.fetch(u)

    monkeypatch.setattr(http, "fetch", without_hub)
    with get_conn() as conn:
        opendata.run(conn, str(tmp_path / "datasets"))
        conn.execute("UPDATE datasets SET variant_group = '' WHERE variant_group != ''")  # stored before groups existed
    assert any(r["source"] == f"版の比較: {opendata.PARKS_GROUP}" and r["status"] == "not_found" for r in _runs())

    # Next run: the catalog file is unchanged, the Hub version arrives; both are compared.
    monkeypatch.setattr(http, "fetch", web.fetch)
    with get_conn() as conn:
        out = opendata.run(conn, str(tmp_path / "datasets"))
    assert out[PARK_SRC.package_id] == "unchanged"
    catalog_version, hub_version = _parks(client)
    assert catalog_version["variant_group"] == opendata.PARKS_GROUP
    assert any(n["kind"] == "row_count_differs" for n in catalog_version["variant_notes"])


def test_a_group_with_one_version_says_there_is_nothing_to_compare(client, monkeypatch, tmp_path):
    from app.ingest import http

    from .test_ingest import PARK_CSV_URL, _web

    web = _web()
    monkeypatch.setattr(http, "fetch", lambda u: (_ for _ in ()).throw(http.FetchError(u, "HTTP 500"))
                        if u.startswith(PARK_CSV_URL) else web.fetch(u))
    with get_conn() as conn:
        opendata.run(conn, str(tmp_path / "datasets"))
    runs = [r for r in _runs() if r["source"] == f"版の比較: {opendata.PARKS_GROUP}"]
    assert runs[-1]["status"] == "not_found" and "比べる版がありません" in runs[-1]["message"]


def test_the_estimation_prompt_excludes_administrative_notices():
    # Found on real news (2026-10-24): procurement notices for a child-care centre were put in 子育て.
    assert "公募型プロポーザル" in news_area.SYSTEM and "不祥事" in news_area.SYSTEM
