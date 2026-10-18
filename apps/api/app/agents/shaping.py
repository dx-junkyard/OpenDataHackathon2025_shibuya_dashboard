"""Data 整形支援 Agent (F-09): proposes a shaping plan; execution is deterministic.

The model only fills a finite plan (which columns, which filter, which
aggregation). `apply_plan` executes it without the model, so the user can
check the steps and before/after samples before adopting (F-21).
"""
from __future__ import annotations

import csv
import io
import os
from collections import OrderedDict
from typing import Any, Dict, List

from .. import llm
from ..observe import observed

AGGREGATIONS = ["count_rows", "sum", "last_value"]
PERIODS = ["month", "year", "as_is"]

SYSTEM = f"""あなたはオープンデータを KPI の時系列データへ整形する手順を提案します。
与えられるのは KPI と、表データの列名と先頭数行です。次の有限の手順だけで表せる整形案を作ります。
- date_column: 期間を表す列（日付・年月・年度）。
- value_column: 値の列。aggregation が count_rows の場合は空文字。
- filter_column / filter_value: 行の絞り込み（例: 区名が「渋谷区」）。不要なら両方空文字。
- aggregation: {AGGREGATIONS} のいずれか。count_rows=期間ごとの行数, sum=期間ごとの合計, last_value=期間ごとの最後の値。
- period: {PERIODS} のいずれか。month=YYYY-MM に丸める, year=YYYY に丸める, as_is=そのまま。
- cumulative: 期間ごとの値を累計にするなら true（例: 設置日からの累計設置数）。
- steps: 利用者向けに、何をするかを日本語で 2〜4 行。
列名は与えられたものだけを使います。整形できない場合は feasible=false にして理由を steps に書きます。"""

SCHEMA = llm.obj(
    {
        "feasible": {"type": "boolean"},
        "date_column": llm.STR,
        "value_column": llm.STR,
        "filter_column": llm.STR,
        "filter_value": llm.STR,
        "aggregation": llm.enum(AGGREGATIONS),
        "period": llm.enum(PERIODS),
        "cumulative": {"type": "boolean"},
        "steps": {"type": "array", "items": llm.STR},
    }
)


class ShapingError(ValueError):
    pass


def read_table(path: str, file_format: str) -> List[Dict[str, str]]:
    if file_format == "csv":
        with open(path, encoding="utf-8-sig", newline="") as f:
            return [dict(r) for r in csv.DictReader(f)]
    if file_format == "xlsx":
        from openpyxl import load_workbook

        ws = load_workbook(path, read_only=True, data_only=True).active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        header = [str(h) if h is not None else "" for h in rows[0]]
        return [{h: ("" if v is None else str(v)) for h, v in zip(header, r)} for r in rows[1:]]
    raise ShapingError(f"未対応の形式です: {file_format}")


def profile_columns(rows: List[Dict[str, str]], max_distinct: int = 12) -> Dict[str, Any]:
    """Per-column summary over ALL rows: distinct values for low-cardinality columns."""
    out: Dict[str, Any] = {}
    for col in (rows[0].keys() if rows else []):
        values = [r.get(col, "") for r in rows]
        distinct = sorted({v for v in values if v != ""})
        out[col] = {"distinct_count": len(distinct), "values": distinct if len(distinct) <= max_distinct else []}
    return out


def _prompt(kpi: Dict[str, Any], columns: List[str], sample: List[Dict[str, str]]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns)
    w.writeheader()
    w.writerows(sample)
    return f"KPI: {kpi['name']}（単位: {kpi['unit']}、測り方: {kpi['measurement']}）\n\n列名: {columns}\n\n先頭行:\n{buf.getvalue()}"


@observed("data-shaping-agent")
def propose_plan(kpi: Dict[str, Any], columns: List[str], sample: List[Dict[str, str]]) -> Dict[str, Any]:
    return llm.complete_json(SYSTEM, _prompt(kpi, columns, sample), SCHEMA, "shaping_plan")


TARGET_AREA = "渋谷区"


def plan_warnings(plan: Dict[str, Any], profile: Dict[str, Any]) -> List[str]:
    """Deterministic checks shown next to an AI shaping plan before adoption.

    A probe-agent shadow comparison (System 6) showed the model sometimes omits
    the area filter, and that a richer prompt did not fix it reliably, so the
    guard is rule-based rather than left to the model."""
    out = []
    for col, p in profile.items():
        values = p["values"]
        if TARGET_AREA in values and len(values) > 1 and plan.get("filter_column") != col:
            others = "・".join(v for v in values if v != TARGET_AREA)
            out.append(f"「{col}」に{TARGET_AREA}以外（{others}）の行が含まれていますが、絞り込みがありません")
    return out


def _period(value: str, period: str) -> str:
    v = value.strip().replace("/", "-").replace(".", "-")
    if period == "as_is":
        return v
    parts = v.split("-")
    if len(parts[0]) != 4 or not parts[0].isdigit():
        raise ShapingError(f"期間として解釈できない値があります: {value!r}")
    if period == "year":
        return parts[0]
    if len(parts) < 2 or not parts[1].isdigit():
        raise ShapingError(f"年月として解釈できない値があります: {value!r}")
    return f"{parts[0]}-{int(parts[1]):02d}"


def apply_plan(rows: List[Dict[str, str]], plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Deterministically turn table rows into [{period, value}] sorted by period."""
    if not plan.get("feasible"):
        raise ShapingError("この整形案は実行できないとされています")
    cols = set(rows[0]) if rows else set()
    for key in ("date_column", "value_column", "filter_column"):
        col = plan.get(key) or ""
        if col and col not in cols:
            raise ShapingError(f"列が見つかりません: {col}")
    agg = plan["aggregation"]
    if agg not in AGGREGATIONS or plan["period"] not in PERIODS:
        raise ShapingError("未対応の集計方法です")
    if agg != "count_rows" and not plan.get("value_column"):
        raise ShapingError("値の列が指定されていません")
    buckets: "OrderedDict[str, float]" = OrderedDict()
    for r in rows:
        if plan.get("filter_column") and r.get(plan["filter_column"], "").strip() != plan.get("filter_value", "").strip():
            continue
        raw_date = r.get(plan["date_column"], "").strip()
        if not raw_date:
            continue
        p = _period(raw_date, plan["period"])
        if agg == "count_rows":
            buckets[p] = buckets.get(p, 0) + 1
            continue
        raw = r.get(plan["value_column"], "").replace(",", "").strip()
        if raw == "":
            continue
        try:
            num = float(raw)
        except ValueError as exc:
            raise ShapingError(f"数値として解釈できない値があります: {raw!r}") from exc
        buckets[p] = buckets.get(p, 0) + num if agg == "sum" else num
    points = [{"period": k, "value": v} for k, v in sorted(buckets.items())]
    if plan.get("cumulative"):
        total = 0.0
        for pt in points:
            total += pt["value"]
            pt["value"] = total
    return points


def dataset_file(datasets_dir: str, file_path: str) -> str:
    path = os.path.normpath(os.path.join(datasets_dir, file_path))
    if not path.startswith(os.path.normpath(datasets_dir) + os.sep):
        raise ShapingError("データセットのパスが不正です")
    return path
