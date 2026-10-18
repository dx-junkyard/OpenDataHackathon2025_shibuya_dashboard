"""SQLite persistence for the 渋谷共創ダッシュボード API.

Every table keeps who created a row and when, so that the evidence trail
required by docs/features.md F-16 / F-21 can be reconstructed.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('participant','community_manager','staff','admin')),
    attribute TEXT NOT NULL DEFAULT '' CHECK (attribute IN ('','resident','visitor','business')),
    department TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS news (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    category TEXT NOT NULL,
    focus_area TEXT NOT NULL DEFAULT '',
    department TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    source_name TEXT NOT NULL DEFAULT '',
    is_sample INTEGER NOT NULL DEFAULT 0,
    kind TEXT NOT NULL DEFAULT 'local' CHECK (kind IN ('local','policy')),
    issue_card_id INTEGER,
    published_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY,
    news_id INTEGER REFERENCES news(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id),
    speaker TEXT NOT NULL CHECK (speaker IN ('user','ai')),
    text TEXT NOT NULL,
    organization TEXT NOT NULL DEFAULT '[]',
    ai_status TEXT NOT NULL DEFAULT 'ok' CHECK (ai_status IN ('ok','unavailable','failed')),
    model TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_proposals (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('issue_card_draft','dataset_candidates','shaping_plan','recommendation')),
    target_ref TEXT NOT NULL,
    payload TEXT NOT NULL,
    evidence TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'proposed'
        CHECK (status IN ('proposed','adopted','adopted_edited','rejected')),
    model TEXT NOT NULL,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at REAL NOT NULL,
    decided_by INTEGER REFERENCES users(id),
    decided_at REAL,
    decision_method TEXT,
    result_ref TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS issue_cards (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '',
    place_time TEXT NOT NULL DEFAULT '',
    evidence TEXT NOT NULL DEFAULT '[]',
    focus_area TEXT NOT NULL DEFAULT '',
    focus_reason TEXT NOT NULL DEFAULT '',
    origin_kind TEXT NOT NULL CHECK (origin_kind IN ('news','conversation','thread','manual')),
    origin_ref TEXT NOT NULL DEFAULT '',
    community_id INTEGER REFERENCES communities(id),
    author_id INTEGER NOT NULL REFERENCES users(id),
    proposal_id INTEGER REFERENCES ai_proposals(id),
    visibility TEXT NOT NULL DEFAULT 'public' CHECK (visibility IN ('private','community','public')),
    status TEXT NOT NULL DEFAULT 'published' CHECK (status IN (
        'draft','published','verifying','dashboard_published','under_review','adopted','declined')),
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS kpis (
    id INTEGER PRIMARY KEY,
    issue_card_id INTEGER NOT NULL REFERENCES issue_cards(id),
    name TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT '',
    measurement TEXT NOT NULL DEFAULT '',
    data_availability TEXT NOT NULL DEFAULT 'unknown'
        CHECK (data_availability IN ('open_data','survey_needed','unknown')),
    target_value REAL,
    dataset_id INTEGER REFERENCES datasets(id),
    position INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS datasets (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    publisher TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    license TEXT NOT NULL DEFAULT '',
    file_format TEXT NOT NULL CHECK (file_format IN ('csv','xlsx')),
    file_path TEXT NOT NULL,
    updated_on TEXT NOT NULL DEFAULT '',
    granularity TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '',
    is_sample INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS kpi_points (
    id INTEGER PRIMARY KEY,
    kpi_id INTEGER NOT NULL REFERENCES kpis(id),
    period TEXT NOT NULL,
    value REAL NOT NULL,
    proposal_id INTEGER REFERENCES ai_proposals(id),
    UNIQUE (kpi_id, period)
);

CREATE TABLE IF NOT EXISTS dashboards (
    id INTEGER PRIMARY KEY,
    issue_card_id INTEGER NOT NULL UNIQUE REFERENCES issue_cards(id),
    public_slug TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','private')),
    published_by INTEGER REFERENCES users(id),
    published_at REAL
);

CREATE TABLE IF NOT EXISTS annotations (
    id INTEGER PRIMARY KEY,
    dashboard_id INTEGER NOT NULL REFERENCES dashboards(id),
    period TEXT NOT NULL,
    label TEXT NOT NULL,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS adoption_decisions (
    id INTEGER PRIMARY KEY,
    dashboard_id INTEGER NOT NULL REFERENCES dashboards(id),
    state TEXT NOT NULL CHECK (state IN ('under_review','adopted','declined')),
    reason TEXT NOT NULL,
    department TEXT NOT NULL,
    decided_by INTEGER NOT NULL REFERENCES users(id),
    decided_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS communities (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    focus_area TEXT NOT NULL DEFAULT '',
    area TEXT NOT NULL DEFAULT '',
    hot_topic TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS community_members (
    community_id INTEGER NOT NULL REFERENCES communities(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    joined_at REAL NOT NULL,
    PRIMARY KEY (community_id, user_id)
);

CREATE TABLE IF NOT EXISTS threads (
    id INTEGER PRIMARY KEY,
    community_id INTEGER NOT NULL REFERENCES communities(id),
    title TEXT NOT NULL,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY,
    thread_id INTEGER NOT NULL REFERENCES threads(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    text TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    text TEXT NOT NULL,
    link TEXT NOT NULL DEFAULT '',
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
"""


def db_path() -> str:
    return os.getenv("APP_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "app.db"))


def init_db() -> None:
    path = db_path()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
