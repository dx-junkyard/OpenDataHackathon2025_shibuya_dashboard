"""Drafts from news that is not a resident's trouble say so (P-7)."""
from app import llm
from app.agents import issue_card


def _fake(fit):
    return lambda system, user, schema, name: {
        "title": "t", "target": "", "place_time": "", "evidence": [], "origin_fit": fit, "fit_note": "n",
        "focus_area": "AREA-1", "focus_reason": "r",
        "kpi_candidates": [{"name": "件数", "unit": "件", "measurement": "", "data_availability": "unknown"}]}


def test_personal_incident_draft_never_proposes_kpis(monkeypatch):
    monkeypatch.setattr(llm, "complete_json", _fake("personal_incident"))
    d = issue_card.draft("記事: 教員の逮捕について")
    assert d["kpi_candidates"] == [] and d["origin_fit"] == "personal_incident"


def test_announcement_draft_keeps_candidates_and_schema_asks_for_fit(monkeypatch):
    monkeypatch.setattr(llm, "complete_json", _fake("announcement"))
    assert len(issue_card.draft("記事: 意見募集")["kpi_candidates"]) == 1
    assert "origin_fit" in issue_card.SCHEMA["required"]
