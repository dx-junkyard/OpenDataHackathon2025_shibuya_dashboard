"""渋谷区ホームページの新着情報を news へ取り込む (docs/features.md F-01).

The list page gives 掲載日・タイトル・区の公式カテゴリ; each article page
gives the body and 担当課 (the first heading under 「お問い合わせ」, which
follows 渋谷区's 組織情報一覧 naming). Articles whose page cannot be read
are recorded in ingest_runs and not stored, so every stored article links to
a source page that existed when it was taken in.
"""
from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urldefrag, urljoin, urlparse

from .. import jpdate
from . import html, http
from .opendata import record

SITE = "https://www.city.shibuya.tokyo.jp"
LISTS = [f"{SITE}/contents/news/", f"{SITE}/contents/news/kodomo.html"]
SOURCE_NAME = "渋谷区ホームページ"
BODY_CHARS = 1500

# Only the official categories that fall inside a single focus area are mapped;
# the others (健康・福祉, 環境・まちづくり, …) span several and are left unclassified.
FOCUS_AREA_BY_CATEGORY = {"子育て・教育・生涯学習": "AREA-1", "防災・安全": "AREA-4"}

_ITEM = re.compile(
    r'<a\s+href="([^"]+)"\s+class="link-inner[^"]*"[^>]*>\s*<p class="date"[^>]*>([^<]+)</p>\s*'
    r'<p class="title"[^>]*>(.*?)</p>(.*?)</a>', re.S)


@dataclass
class ListItem:
    url: str
    published_at: str
    title: str
    categories: List[str]


@dataclass
class Article:
    body: str
    department: str


def parse_list(page: str, base_url: str) -> List[ListItem]:
    out = []
    for href, date, title, rest in _ITEM.findall(page):
        iso = jpdate.to_iso_date(html.strip_tags(date))
        if iso is None:
            continue
        cats = [html.strip_tags(c) for c in re.findall(r"<li[^>]*>(.*?)</li>", rest, re.S)]
        out.append(ListItem(url=urljoin(base_url, href), published_at=iso, title=html.strip_tags(title), categories=cats))
    return out


def parse_article(page: str) -> Article:
    lead = re.search(r"</h1>.*?<p class=\"text\"[^>]*>(.*?)</p>", page, re.S)
    rich = re.search(r'<div class="u-rich-editor-contents[^"]*"[^>]*>(.*?)<div class="info-wrap', page, re.S)
    parts = [html.strip_tags(lead.group(1))] if lead else []
    if rich:
        parts.append(html.strip_tags(rich.group(1)))
    body = "\n".join(p for p in parts if p).strip()
    dept = re.search(r">お問い合わせ</h2>.*?<h4[^>]*>(.*?)</h4>", page, re.S)
    return Article(body=body[:BODY_CHARS], department=html.strip_tags(dept.group(1)) if dept else "")


def _is_article(url: str) -> bool:
    u = urlparse(url)
    return f"{u.scheme}://{u.netloc}" == SITE and u.path.endswith(".html") and not u.path.startswith("/contents/news/")


def run(conn: sqlite3.Connection, limit: int = 30, delay: float = 0.5) -> dict:
    items: List[ListItem] = []
    seen = set()
    for list_url in LISTS:
        try:
            page = http.fetch(list_url)
        except http.FetchError as exc:
            record(conn, "news", f"新着情報一覧 {list_url}", "failed", str(exc))
            continue
        found = parse_list(http.decode_text(page.content), page.url)
        record(conn, "news", f"新着情報一覧 {list_url}", "ok" if found else "not_found", f"{len(found)} 件")
        for it in found:
            if it.url not in seen:
                seen.add(it.url)
                items.append(it)
    items.sort(key=lambda i: i.published_at, reverse=True)
    counts = {"ok": 0, "unchanged": 0, "failed": 0}
    for it in items[:limit]:
        if conn.execute("SELECT 1 FROM news WHERE source_url = ?", (it.url,)).fetchone():
            counts["unchanged"] += 1
            continue
        status, article = _fetch_article(it)
        if article is None:
            record(conn, "news", it.url, "failed", status)
            counts["failed"] += 1
            continue
        cat = it.categories[0] if it.categories else "その他"
        conn.execute(
            "INSERT INTO news (title, body, category, focus_area, department, source_url, source_name, is_sample, kind,"
            " published_at) VALUES (?,?,?,?,?,?,?,0,'local',?)",
            (it.title, article.body, cat, FOCUS_AREA_BY_CATEGORY.get(cat, ""), article.department, it.url,
             SOURCE_NAME, it.published_at))
        record(conn, "news", it.url, "ok", it.title + ("" if article.department else "（担当課の記載なし）"))
        counts["ok"] += 1
        if delay:
            time.sleep(delay)
    return counts


def _fetch_article(it: ListItem) -> tuple[str, Optional[Article]]:
    page_url, _ = urldefrag(it.url)
    if not _is_article(page_url):
        return "区のホームページの記事ページではないため本文を取り込みません", None
    try:
        page = http.fetch(page_url)
    except http.FetchError as exc:
        return str(exc), None
    article = parse_article(http.decode_text(page.content))
    if not article.body:
        return "本文を読み取れませんでした", None
    return "ok", article
