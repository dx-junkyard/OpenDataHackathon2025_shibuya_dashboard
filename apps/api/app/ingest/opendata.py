"""Register real open data for the representative scenario (近所で外遊びできる場所).

Sources (checked by hand; see docs/features.md §7 and docs/sources/):

- 2026-10-24, scenario changed to outdoor play: 渋谷区「都市公園・都立公園一覧」
  on 東京都オープンデータカタログ (CKAN `t131130d2025000003`, CC BY) lists the
  ward's parks and children's play areas with location. It has no area,
  play equipment or ball-play columns. The catalogs hold nothing for
  「遊び場」「プレーパーク」「児童遊園」 (the searches are recorded at run time).
- 2026-10-20, earlier scenario (授乳・おむつ替え): 東京都福祉局「赤ちゃん・ふらっと一覧」
  covers every 区市町村 including 渋谷区 (column 「地域」). Its CKAN resource URL
  returns 404, so the current file is taken from the link on the bureau's own
  page. Kept as real data any issue card can use.
- 渋谷区オープンデータ (ArcGIS Hub, linked from 渋谷区's CKAN record
  「オープンデータ一覧」): 「子育て関連施設の利用状況」 is registered as related data.

Metadata (title, publisher, license, dates) is always taken from the source
at run time, never written here. The catalog searches are recorded too, so
"not found" is visible as a result with its scope.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import quote, urlencode

from .. import jpdate
from ..agents import shaping
from . import html, http

TOKYO_CKAN = "https://catalog.data.metro.tokyo.lg.jp"
SHIBUYA_CKAN_ORG = "t131130"
SHIBUYA_HUB = "https://city-shibuya-data.opendata.arcgis.com"

SEARCH_KEYWORDS = ["公園", "遊び場", "プレーパーク", "児童遊園"]

FORMATS = {"CSV": "csv", "XLSX": "xlsx", "PDF": "pdf"}


@dataclass(frozen=True)
class CkanSource:
    package_id: str
    granularity: str
    tags: str
    note: str
    # Used only when the CKAN resource itself cannot be fetched.
    landing_page: str = ""
    landing_link_text: str = ""


@dataclass(frozen=True)
class HubSource:
    item_id: str
    granularity: str
    tags: str
    note: str


CKAN_SOURCES = [
    CkanSource(
        package_id="t131130d2025000003",
        granularity="公園単位（緯度・経度つき）",
        tags="子育て,外遊び,公園,児童遊園地,遊び場",
        note="渋谷区の都市公園・児童遊園地の一覧。面積の列は空欄で、遊具やボール遊びの可否の列はない。開設日の列はない。",
    ),
    CkanSource(
        package_id="t000054d0000000347",
        granularity="施設単位・区市町村別（列「地域」）",
        tags="子育て,授乳,おむつ替え,施設,赤ちゃん・ふらっと",
        note="都内の授乳・おむつ替えができる施設（赤ちゃん・ふらっと）の届出一覧。列「地域」で区市町村を絞り込む。設置日の列はない。",
        landing_page="https://www.fukushi.metro.tokyo.lg.jp/kodomo/kosodate/akachanflat",
        landing_link_text="赤ちゃん・ふらっと一覧（CSV）",
    ),
]

HUB_SOURCES = [
    HubSource(
        item_id="b58e72bd300d4cd28f114eb41872e326",
        granularity="施設・月別（年度と月の列）",
        tags="子育て,子育て支援センター,子育てひろば,利用者数",
        note="区の子育て支援センター・子育てひろばの月別利用者数。公園やプレーパークの利用者数ではない。",
    ),
]


class IngestFailed(RuntimeError):
    pass


def record(conn: sqlite3.Connection, kind: str, source: str, status: str, message: str = "", result_ref: str = "") -> None:
    conn.execute("INSERT INTO ingest_runs (kind, source, status, message, result_ref, created_at) VALUES (?,?,?,?,?,?)",
                 (kind, source, status, message, result_ref, time.time()))


def _date(value: Optional[str]) -> str:
    return (value or "")[:10]


# ---------------------------------------------------------------- catalog search


def search_scope(conn: sqlite3.Connection) -> None:
    """Record what the Shibuya catalogs hold for the scenario keywords."""
    for kw in SEARCH_KEYWORDS:
        label = f"検索: 東京都オープンデータカタログ（渋谷区）「{kw}」"
        url = f"{TOKYO_CKAN}/api/3/action/package_search?" + urlencode(
            {"q": kw, "fq": f"organization:{SHIBUYA_CKAN_ORG}", "rows": 20})
        try:
            res = http.fetch_json(url)["result"]
            titles = [p["title"] for p in res["results"]]
            record(conn, "dataset", label, "ok" if titles else "not_found",
                   f"{res['count']} 件" + (f": {'、'.join(titles)}" if titles else "（該当なし）"))
        except (http.FetchError, KeyError) as exc:
            record(conn, "dataset", label, "failed", str(exc))
        label = f"検索: 渋谷区オープンデータ（ArcGIS Hub）「{kw}」"
        url = f"{SHIBUYA_HUB}/api/search/v1/collections/dataset/items?" + urlencode({"q": kw, "limit": 20})
        try:
            res = http.fetch_json(url)
            titles = [f["properties"]["title"] for f in res.get("features", [])]
            record(conn, "dataset", label, "ok" if titles else "not_found",
                   f"{res.get('numberMatched', len(titles))} 件" + (f": {'、'.join(titles)}" if titles else "（該当なし）"))
        except (http.FetchError, KeyError) as exc:
            record(conn, "dataset", label, "failed", str(exc))


# ---------------------------------------------------------------- storing


def _to_stored(content: bytes, fmt: str) -> bytes:
    """CSV is stored as UTF-8 so the shaping step reads every file the same way."""
    if fmt == "csv":
        return http.decode_text(content).encode("utf-8")
    return content


def store(conn: sqlite3.Connection, datasets_dir: str, *, source_key: str, meta: Dict[str, str], content: bytes,
          fmt: str, file_url: str, as_of: str) -> str:
    """Upsert the dataset and add a snapshot for `as_of`. Returns 'ok' or 'unchanged'."""
    data = _to_stored(content, fmt)
    sha = hashlib.sha256(data).hexdigest()
    row = conn.execute("SELECT id FROM datasets WHERE source_key = ?", (source_key,)).fetchone()
    if row is not None:
        same = conn.execute("SELECT 1 FROM dataset_snapshots WHERE dataset_id = ? AND sha256 = ?", (row["id"], sha)).fetchone()
        if same:
            return "unchanged"
    os.makedirs(datasets_dir, exist_ok=True)
    safe = "".join(c if c.isalnum() else "-" for c in source_key.split(":")[-1])
    name = f"od-{safe}-{as_of or 'undated'}-{sha[:8]}.{fmt}"
    path = os.path.join(datasets_dir, name)
    with open(path, "wb") as f:
        f.write(data)
    try:
        tables = shaping.read_tables(path, fmt)
        if not any(len(t["rows"]) > 1 for t in tables):
            raise IngestFailed("表データが空です")
    except shaping.ShapingError as exc:
        os.remove(path)
        raise IngestFailed(f"取得したファイルを表として読めませんでした: {exc}") from exc
    cols = dict(meta, file_format=fmt, file_path=name, file_url=file_url, updated_on=as_of)
    if row is None:
        cur = conn.execute(
            "INSERT INTO datasets (title, publisher, description, source_url, license, file_format, file_path, updated_on,"
            " granularity, tags, is_sample, source_key, file_url) VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?)",
            (cols["title"], cols["publisher"], cols["description"], cols["source_url"], cols["license"], fmt, name,
             as_of, cols["granularity"], cols["tags"], source_key, file_url))
        dataset_id = cur.lastrowid
    else:
        dataset_id = row["id"]
        conn.execute(
            "UPDATE datasets SET title=?, publisher=?, description=?, source_url=?, license=?, file_format=?, file_path=?,"
            " updated_on=?, granularity=?, tags=?, file_url=? WHERE id=?",
            (cols["title"], cols["publisher"], cols["description"], cols["source_url"], cols["license"], fmt, name,
             as_of, cols["granularity"], cols["tags"], file_url, dataset_id))
    conn.execute(
        "INSERT INTO dataset_snapshots (dataset_id, as_of, file_format, file_path, file_url, sha256, fetched_at)"
        " VALUES (?,?,?,?,?,?,?) ON CONFLICT (dataset_id, as_of) DO UPDATE SET file_format=excluded.file_format,"
        " file_path=excluded.file_path, file_url=excluded.file_url, sha256=excluded.sha256, fetched_at=excluded.fetched_at",
        (dataset_id, as_of, fmt, name, file_url, sha, time.time()))
    from ..kpi_refresh import refresh_dataset
    refresh_dataset(conn, dataset_id)  # KPIs built on this dataset follow the new version
    return "ok"


# ---------------------------------------------------------------- CKAN


def _pick_resource(resources: List[dict]) -> Optional[dict]:
    for wanted in FORMATS:
        for r in resources:
            if (r.get("format") or "").upper() == wanted and r.get("url"):
                return r
    return None


def _from_landing_page(src: CkanSource) -> tuple[http.Fetched, str]:
    page = http.fetch(src.landing_page)
    body = http.decode_text(page.content)
    hrefs = [h for h, text in html.links(body, page.url) if text == src.landing_link_text]
    if not hrefs:
        raise IngestFailed(f"提供者ページ {src.landing_page} にリンク「{src.landing_link_text}」が見つかりません")
    as_of = jpdate.find_iso_date(html.page_text(body), after="更新日") or ""
    return http.fetch(hrefs[0]), as_of


def ingest_ckan(conn: sqlite3.Connection, datasets_dir: str, src: CkanSource) -> str:
    label = f"東京都オープンデータカタログ {src.package_id}"
    try:
        pkg = http.fetch_json(f"{TOKYO_CKAN}/api/3/action/package_show?id={quote(src.package_id)}")["result"]
        res = _pick_resource(pkg.get("resources", []))
        if res is None:
            raise IngestFailed("CSV / Excel / PDF のリソースがありません")
        fmt = FORMATS[res["format"].upper()]
        note = ""
        try:
            got = http.fetch(res["url"])
            as_of = _date(res.get("last_modified") or pkg.get("metadata_modified"))
        except http.FetchError as exc:
            if not src.landing_page:
                raise IngestFailed(f"リソースを取得できませんでした（{exc.reason}）: {res['url']}") from exc
            got, as_of = _from_landing_page(src)
            note = f"カタログのリソース URL が {exc.reason} のため、提供者ページ {src.landing_page} のリンクから取得。"
        meta = {
            "title": pkg["title"],
            "publisher": (pkg.get("organization") or {}).get("title", ""),
            "description": f"{src.note} {note}".strip(),
            "source_url": f"{TOKYO_CKAN}/dataset/{pkg['name']}",
            "license": pkg.get("license_id") or pkg.get("license_title") or "",
            "granularity": src.granularity,
            "tags": src.tags,
        }
        if not meta["license"] or not meta["publisher"]:
            raise IngestFailed("カタログにライセンスまたは提供者の記載がありません")
        status = store(conn, datasets_dir, source_key=f"ckan:{TOKYO_CKAN}:{src.package_id}", meta=meta,
                       content=got.content, fmt=fmt, file_url=got.url, as_of=as_of)
    except (http.FetchError, IngestFailed, KeyError, ValueError) as exc:
        record(conn, "dataset", label, "failed", str(exc))
        return "failed"
    record(conn, "dataset", label, status, f"{meta['title']}（{as_of} 時点）{note}", f"source:{src.package_id}")
    return status


# ---------------------------------------------------------------- ArcGIS Hub


def ingest_hub(conn: sqlite3.Connection, datasets_dir: str, src: HubSource) -> str:
    label = f"渋谷区オープンデータ（ArcGIS Hub）{src.item_id}"
    try:
        item = http.fetch_json(f"{SHIBUYA_HUB}/api/search/v1/collections/dataset/items/{src.item_id}")
        p = item["properties"]
        desc = html.strip_tags(p.get("description") or "")
        modified = datetime.fromtimestamp(p["modified"] / 1000, tz=timezone.utc).date().isoformat()
        as_of = jpdate.find_iso_date(desc) or modified
        lic = p.get("license") or html.strip_tags(p.get("licenseInfo") or "")
        if not lic:
            raise IngestFailed("ライセンスの記載がありません")
        got = http.fetch(f"{SHIBUYA_HUB}/api/download/v1/items/{src.item_id}/csv?layers=0")
        meta = {
            "title": p["title"],
            # The Hub site is the portal 渋谷区 links from its own catalog record.
            "publisher": "渋谷区",
            "description": f"{src.note} 提供元の説明: {desc.replace(chr(10), ' ')}",
            "source_url": f"{SHIBUYA_HUB}/datasets/{src.item_id}",
            "license": lic,
            "granularity": src.granularity,
            "tags": src.tags,
        }
        status = store(conn, datasets_dir, source_key=f"hub:{SHIBUYA_HUB}:{src.item_id}", meta=meta,
                       content=got.content, fmt="csv",
                       file_url=f"{SHIBUYA_HUB}/api/download/v1/items/{src.item_id}/csv?layers=0", as_of=as_of)
    except (http.FetchError, IngestFailed, KeyError, ValueError, TypeError) as exc:
        record(conn, "dataset", label, "failed", str(exc))
        return "failed"
    record(conn, "dataset", label, status, f"{meta['title']}（{as_of} 時点）", f"source:{src.item_id}")
    return status


def run(conn: sqlite3.Connection, datasets_dir: str) -> Dict[str, str]:
    search_scope(conn)
    out = {}
    for c in CKAN_SOURCES:
        out[c.package_id] = ingest_ckan(conn, datasets_dir, c)
    for h in HUB_SOURCES:
        out[h.item_id] = ingest_hub(conn, datasets_dir, h)
    return out


def recent_runs(conn: sqlite3.Connection, limit: int = 50) -> List[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM ingest_runs ORDER BY id DESC LIMIT ?", (limit,))]

