"""The single network boundary of the ingest package (replaced in tests)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

USER_AGENT = "shibuya-cocreation-dashboard/0.1 (Open Data Hackathon 2025)"


class FetchError(RuntimeError):
    def __init__(self, url: str, reason: str):
        super().__init__(f"{url}: {reason}")
        self.url = url
        self.reason = reason


@dataclass
class Fetched:
    url: str
    content: bytes
    content_type: str


def fetch(url: str) -> Fetched:
    try:
        r = httpx.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=60)
    except httpx.HTTPError as exc:
        raise FetchError(url, f"接続できませんでした（{type(exc).__name__}）") from exc
    if r.status_code != 200:
        raise FetchError(url, f"HTTP {r.status_code}")
    return Fetched(url=str(r.url), content=r.content, content_type=r.headers.get("content-type", ""))


def fetch_json(url: str) -> Any:
    try:
        return json.loads(fetch(url).content)
    except ValueError as exc:
        raise FetchError(url, "JSON として読めませんでした") from exc


def decode_text(data: bytes) -> str:
    """Japanese government files are UTF-8 or Shift_JIS (cp932)."""
    for enc in ("utf-8-sig", "cp932"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("文字コードを判定できませんでした（UTF-8 / Shift_JIS 以外）")
