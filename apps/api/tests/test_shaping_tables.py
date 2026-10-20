"""F-09: PDF / HTML tables → KPI time series (plan by AI, deterministic execution)."""
import pytest

from app import jpdate
from app.agents import shaping

from .conftest import as_user
from .test_flow import PARENT, _card_from_conversation

WIDE_HTML = """<html><body><main>
<table><tr><th>電話</th><td>03-0000-0000</td></tr></table>
<table>
  <caption>子育て家庭の外出環境の整備</caption>
  <tr><td colspan="4">単位：か所（各年度末）</td></tr>
  <tr><th>項目</th><th>令和3年度</th><th>令和4年度</th><th>令和5年度</th></tr>
  <tr><td>授乳室</td><td>1,262</td><td>1,361か所</td><td>－</td></tr>
  <tr><td rowspan="2">おむつ替え</td><td>10</td><td>12</td><td>15</td></tr>
  <tr><td>△1</td><td>2</td><td>3</td></tr>
</table></main></body></html>"""

WIDE_PLAN = {
    "feasible": True, "table_index": 1, "header_row": 1, "unpivot_columns": ["令和3年度", "令和4年度", "令和5年度"],
    "date_column": "期間", "value_column": "値", "filter_column": "項目", "filter_value": "授乳室",
    "aggregation": "last_value", "period": "year", "cumulative": False, "steps": ["授乳室の行を年度ごとに並べる"],
}


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return str(p)


def test_html_tables_expand_spans_and_unpivot(tmp_path):
    tables = shaping.read_tables(_write(tmp_path, "t.html", WIDE_HTML), "html")
    assert len(tables) == 2 and tables[1]["name"] == "子育て家庭の外出環境の整備"
    assert tables[1]["rows"][0] == ["単位：か所（各年度末）"] * 4  # colspan
    assert tables[1]["rows"][4][0] == "おむつ替え"  # rowspan carried down
    rows = shaping.table_rows(tables, WIDE_PLAN)
    assert rows[0] == {"項目": "授乳室", "期間": "令和3年度", "値": "1,262"}
    assert shaping.apply_plan(rows, WIDE_PLAN) == [{"period": "2021", "value": 1262.0}, {"period": "2022", "value": 1361.0}]
    warnings = shaping.plan_warnings(WIDE_PLAN, shaping.profile_columns(rows))
    assert warnings == ["年度（4月〜翌3月）を西暦の年（例: 令和5年度→2023）として表示します"]
    # Negative marks (△) and sums over the rowspan rows.
    plan = {**WIDE_PLAN, "filter_value": "おむつ替え", "aggregation": "sum"}
    assert [p["value"] for p in shaping.apply_plan(rows, plan)] == [9.0, 14.0, 18.0]


def test_ambiguous_or_inexact_values_are_reported_not_guessed():
    with pytest.raises(shaping.ShapingError, match="元号のない"):
        shaping.apply_plan([{"年度": "26年度", "値": "1"}], {**WIDE_PLAN, "date_column": "年度", "filter_column": ""})
    with pytest.raises(shaping.ShapingError, match="数値として解釈できない"):
        shaping.apply_plan([{"期間": "2024", "値": "約0.3km"}], {**WIDE_PLAN, "filter_column": ""})
    assert jpdate.parse("令和元年度") == (2019, None, None)
    assert jpdate.parse("H26") == (2014, None, None)
    assert jpdate.to_iso_date("令和8年10月7日") == "2026-10-07"
    assert jpdate.parse("26年度") is None


def test_plan_errors_point_at_the_table(tmp_path):
    tables = shaping.read_tables(_write(tmp_path, "t.html", WIDE_HTML), "html")
    with pytest.raises(shaping.ShapingError, match="表 5 はありません"):
        shaping.table_rows(tables, {**WIDE_PLAN, "table_index": 5})
    with pytest.raises(shaping.ShapingError, match="列が見つかりません: 令和9年度"):
        shaping.table_rows(tables, {**WIDE_PLAN, "unpivot_columns": ["令和9年度"]})
    with pytest.raises(shaping.ShapingError, match="table 要素"):
        shaping.read_tables(_write(tmp_path, "n.html", "<p>表なし</p>"), "html")


def _ruled_pdf(rows):
    """A one-page PDF with a ruled grid table (ASCII text, Helvetica) — enough for pdfplumber."""
    col_w, row_h, x0, y_top = 100, 20, 50, 750
    ops = []
    n_rows, n_cols = len(rows), len(rows[0])
    for i in range(n_rows + 1):
        y = y_top - i * row_h
        ops.append(f"{x0} {y} m {x0 + n_cols * col_w} {y} l S")
    for j in range(n_cols + 1):
        x = x0 + j * col_w
        ops.append(f"{x} {y_top} m {x} {y_top - n_rows * row_h} l S")
    for i, r in enumerate(rows):
        for j, cell in enumerate(r):
            ops.append(f"BT /F1 10 Tf {x0 + j * col_w + 5} {y_top - (i + 1) * row_h + 6} Td ({cell}) Tj ET")
    stream = "\n".join(ops).encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out


PDF_ROWS = [["year", "area", "spots"], ["2024", "Shibuya", "40"], ["2025", "Shibuya", "43"], ["2025", "Shinjuku", "50"]]
PDF_PLAN = {
    "feasible": True, "table_index": 0, "header_row": 0, "unpivot_columns": [], "date_column": "year",
    "value_column": "spots", "filter_column": "area", "filter_value": "Shibuya", "aggregation": "last_value",
    "period": "year", "cumulative": False, "steps": ["Shibuya の行を年ごとに"],
}


def test_pdf_ruled_table_to_series(tmp_path):
    tables = shaping.read_tables(_write(tmp_path, "t.pdf", _ruled_pdf(PDF_ROWS)), "pdf")
    assert tables[0]["name"] == "1 ページ目の表 1" and tables[0]["rows"] == PDF_ROWS
    rows = shaping.table_rows(tables, PDF_PLAN)
    assert shaping.apply_plan(rows, PDF_PLAN) == [{"period": "2024", "value": 40.0}, {"period": "2025", "value": 43.0}]
    with pytest.raises(shaping.ShapingError, match="PDF を読めませんでした"):
        shaping.read_tables(_write(tmp_path, "broken.pdf", b"not a pdf"), "pdf")


def test_uploaded_pdf_goes_through_proposal_and_adoption(client, monkeypatch, tmp_path):
    _, card = _card_from_conversation(client, monkeypatch)
    kpi = card["kpis"][0]
    r = client.post("/api/datasets", data={"title": "PDF の表", "publisher": "テスト", "license": "CC-BY-4.0"},
                    files={"file": ("table.pdf", _ruled_pdf(PDF_ROWS), "application/pdf")}, headers=as_user(PARENT))
    assert r.status_code == 201 and r.json()["file_format"] == "pdf"
    seen = {}

    def fake_plan(k, tables, note):
        seen["tables"] = tables
        return PDF_PLAN

    monkeypatch.setattr(shaping, "propose_plan", fake_plan)
    prop = client.post(f"/api/kpis/{kpi['id']}/shaping-plans", json={"dataset_id": r.json()["id"]}, headers=as_user(PARENT)).json()
    assert seen["tables"][0]["rows"][0] == ["year", "area", "spots"]
    p = prop["payload"]
    assert p["tables"] == [{"index": 0, "name": "1 ページ目の表 1", "row_count": 4}]
    assert p["columns"] == ["year", "area", "spots"] and p["preview_error"] == ""
    assert p["after_preview"][-1] == {"period": "2025", "value": 43.0}
    # Not on the KPI until a person adopts it.
    assert client.get(f"/api/issue-cards/{card['id']}", headers=as_user(PARENT)).json()["kpis"][0]["points"] == []
    adopted = client.post(f"/api/shaping-plans/{prop['id']}/adopt", json={}, headers=as_user(PARENT)).json()
    assert adopted["points"] == [{"period": "2024", "value": 40.0}, {"period": "2025", "value": 43.0}]


def test_upload_rejects_other_formats(client):
    r = client.post("/api/datasets", data={"title": "t", "publisher": "p", "license": "l"},
                    files={"file": ("a.docx", b"x", "application/octet-stream")}, headers=as_user(PARENT))
    assert r.status_code == 422
