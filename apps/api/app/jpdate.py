"""Dates as Japanese public bodies write them: 西暦 / 和暦, 年・年度・年月・年月日.

A year without an era (e.g. 「26年度」) is ambiguous and is rejected rather
than guessed.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional, Tuple

ERA_OFFSETS = {"令和": 2018, "平成": 1988, "昭和": 1925, "R": 2018, "H": 1988, "S": 1925}

_ERA = r"(令和|平成|昭和|R|H|S)\s*(元|\d{1,2})"
_YEAR = rf"(?:(\d{{4}})|{_ERA})"
_PATTERN = re.compile(
    rf"^{_YEAR}\s*(?:年度|年|[-/.])?\s*(?:(\d{{1,2}})\s*(?:月|[-/.])?\s*(?:(\d{{1,2}})\s*日?)?)?\s*(度)?$")


def normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip()


def parse(value: str) -> Optional[Tuple[int, Optional[int], Optional[int]]]:
    """Return (year, month, day) or None. month/day are None when absent."""
    v = normalize(value)
    m = _PATTERN.match(v)
    if not m:
        return None
    western, era, era_year, month, day, _ = m.groups()
    if western:
        year = int(western)
    else:
        year = ERA_OFFSETS[era] + (1 if era_year == "元" else int(era_year))
    mo = int(month) if month else None
    d = int(day) if day else None
    if mo is not None and not 1 <= mo <= 12 or d is not None and not 1 <= d <= 31:
        return None
    return year, mo, d


def to_iso_date(value: str) -> Optional[str]:
    p = parse(value)
    if p is None or p[1] is None or p[2] is None:
        return None
    return f"{p[0]:04d}-{p[1]:02d}-{p[2]:02d}"


DATE_IN_TEXT = re.compile(r"((?:\d{4}|(?:令和|平成)\s*(?:元|\d{1,2}))\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)")


def find_iso_date(text: str, after: str = "") -> Optional[str]:
    """First 年月日 in text (optionally the first one following `after`)."""
    t = normalize(text)
    if after:
        i = t.find(after)
        if i < 0:
            return None
        t = t[i + len(after):]
    m = DATE_IN_TEXT.search(t)
    return to_iso_date(m.group(1).replace(" ", "")) if m else None
