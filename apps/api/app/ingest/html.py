"""Small stdlib HTML helpers for the public pages we read."""
from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from typing import List, Tuple
from urllib.parse import urljoin


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: List[Tuple[str, str]] = []
        self._href: str | None = None
        self._text: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.out.append((self._href, squash("".join(self._text))))
            self._href = None


def links(html: str, base_url: str) -> List[Tuple[str, str]]:
    p = _Links()
    p.feed(html)
    return [(urljoin(base_url, h), t) for h, t in p.out if h]


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def strip_tags(fragment: str) -> str:
    """Visible text of an HTML fragment, paragraphs separated by newlines."""
    s = re.sub(r"<(script|style|noscript|svg)\b.*?</\1>", "", fragment, flags=re.S | re.I)
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = re.sub(r"<br\s*/?>|</(p|h[1-6]|li|tr|div)>", "\n", s, flags=re.I)
    s = unescape(re.sub(r"<[^>]+>", "", s))
    lines = [squash(line) for line in s.splitlines()]
    return "\n".join(line for line in lines if line)


def page_text(html: str) -> str:
    m = re.search(r"<main\b.*?</main>", html, flags=re.S | re.I)
    return strip_tags(m.group(0) if m else html)
