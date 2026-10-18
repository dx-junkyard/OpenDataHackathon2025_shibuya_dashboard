"""Demo data for the representative scenario (docs/vision.md §6).

Every news article and dataset created here is FICTIONAL and stored with
`is_sample=1`, so the UI and CSV export label it 「サンプル（架空）」.
Run: python -m app.seed  (resets the database)
"""
from __future__ import annotations

import csv
import os
import random
import time

from .db import db_path, get_conn, init_db
from .routes.data import datasets_dir

SAMPLE_PUBLISHER = "デモ用サンプル（架空）"

USERS = [
    (1, "さくら（保護者）", "participant", "resident", ""),
    (2, "ハル（来訪者）", "participant", "visitor", ""),
    (3, "子育て支援課 職員", "staff", "", "子ども家庭部 子育て支援課"),
    (4, "子育て@渋谷 運営", "community_manager", "resident", ""),
    (5, "カフェ店主", "participant", "business", ""),
]

NEWS = [
    ("区内の授乳・おむつ替えスペース、設置状況を公開しました",
     "区では、乳幼児を連れて外出する保護者が安心して過ごせるよう、授乳やおむつ替えができるスペースの設置を進めています。"
     "区内の公共施設を中心に設置状況を取りまとめました。民間施設への設置協力も呼びかけています。",
     "子育て", "AREA-1", "子ども家庭部 子育て支援課", "2026-10-10"),
    ("子育て世帯向け「外出しやすいまち」アンケートを実施します",
     "ベビーカーでの移動や外出先での困りごとについて、区民の声を集めるアンケートを実施します。結果は今後の施策検討に活用します。",
     "子育て", "AREA-1", "子ども家庭部 子育て支援課", "2026-10-05"),
    ("駅周辺のバリアフリー点検を行いました",
     "主要駅周辺の段差や通路幅について点検を行いました。改善が必要な箇所は関係機関と協議します。",
     "移動", "AREA-5", "都市整備部 交通政策課", "2026-09-28"),
    ("秋の地域防災訓練の参加者を募集しています",
     "地域ごとの防災訓練を実施します。初めての方や子ども連れの方も参加できます。",
     "安全", "AREA-4", "危機管理対策部 防災課", "2026-09-20"),
    ("区内観光案内所の多言語対応を拡充します",
     "来訪者が安心して区内を巡れるよう、観光案内所での多言語対応を拡充します。",
     "観光", "AREA-6", "産業観光文化部 観光課", "2026-09-15"),
]

COMMUNITIES = [
    ("子育て@渋谷", "区内で子育てする人が、外出・保育・遊び場について話す場", "子育て", "AREA-1", "区全域", "授乳・おむつ替えスポットの不足"),
    ("ベビーカーで歩く渋谷", "ベビーカーや車いすでの移動の困りごとを共有する", "移動", "AREA-5", "駅周辺", "駅の段差とエレベーター"),
    ("渋谷の防災を考える会", "地域の防災・安全について話し合う", "安全", "AREA-4", "区全域", "子ども連れの避難"),
    ("商店街とまちづくり", "事業者と住民で商店街の未来を考える", "産業", "AREA-7", "商店街", "空き店舗の活用"),
]


def _write_samples(d: str) -> list[tuple]:
    os.makedirs(d, exist_ok=True)
    rnd = random.Random(42)
    # 1) スポット一覧（設置日つき）
    with open(os.path.join(d, "sample_nursing_spots.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["施設名", "区名", "設置日", "授乳室", "おむつ替え台"])
        n = 0
        for y in (2024, 2025, 2026):
            for m in range(1, 13):
                if (y, m) > (2026, 9):
                    break
                for _ in range(rnd.choice([1, 1, 2, 2, 3])):
                    n += 1
                    w.writerow([f"サンプル施設{n:03d}", "渋谷区", f"{y}-{m:02d}-{rnd.randint(1, 28):02d}", "有", "有"])
                if rnd.random() < 0.5:
                    w.writerow([f"サンプル施設X{n:03d}", "新宿区", f"{y}-{m:02d}-15", "有", "無"])
    # 2) 月次の平均利用件数
    with open(os.path.join(d, "sample_spot_usage.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["年月", "区名", "日別平均利用件数"])
        v = 18.0
        for y in (2025, 2026):
            for m in range(1, 13):
                if (y, m) > (2026, 9):
                    break
                v += rnd.uniform(0.5, 2.0)
                w.writerow([f"{y}/{m}", "渋谷区", round(v, 1)])
    # 3) 満足度調査（Excel）
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["調査時期", "回答数", "満足度（5段階平均）"])
    for i, (period, s) in enumerate([("2025-03", 3.6), ("2025-09", 3.8), ("2026-03", 4.0), ("2026-09", 4.3)]):
        ws.append([period, 120 + i * 15, s])
    wb.save(os.path.join(d, "sample_satisfaction.xlsx"))
    # 4) 関係の薄いデータ（検索で選ばれないことの確認用）
    with open(os.path.join(d, "sample_parks.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["公園名", "面積", "開園年"])
        for i in range(10):
            w.writerow([f"サンプル公園{i}", 1000 + i * 120, 1980 + i * 3])
    return [
        ("授乳・おむつ替えスポット一覧（サンプル）", "区内外の授乳室・おむつ替え台のある施設の一覧と設置日", "csv",
         "sample_nursing_spots.csv", "施設単位・設置日", "子育て,授乳,おむつ替え,施設"),
        ("授乳・おむつ替えスポットの月次平均利用件数（サンプル）", "スポットの日別平均利用件数（月次）", "csv",
         "sample_spot_usage.csv", "区・月次", "子育て,利用件数"),
        ("子育て世帯の外出満足度調査（サンプル）", "外出しやすさに関する満足度（5段階）の半期ごとの平均", "xlsx",
         "sample_satisfaction.xlsx", "区・半期", "子育て,満足度,アンケート"),
        ("区立公園一覧（サンプル）", "区立公園の名称・面積・開園年", "csv", "sample_parks.csv", "公園単位", "公園,緑地"),
    ]


def seed() -> None:
    if os.path.exists(db_path()):
        os.remove(db_path())
    init_db()
    now = time.time()
    with get_conn() as conn:
        conn.executemany("INSERT INTO users (id, display_name, role, attribute, department) VALUES (?,?,?,?,?)", USERS)
        for title, body, cat, area, dept, date in NEWS:
            conn.execute(
                "INSERT INTO news (title, body, category, focus_area, department, source_name, is_sample, published_at)"
                " VALUES (?,?,?,?,?,?,1,?)", (title, body, cat, area, dept, SAMPLE_PUBLISHER, date))
        for c in COMMUNITIES:
            conn.execute("INSERT INTO communities (name, description, category, focus_area, area, hot_topic) VALUES (?,?,?,?,?,?)", c)
        for uid in (4, 3):
            conn.execute("INSERT INTO community_members VALUES (1, ?, ?)", (uid, now))
        cur = conn.execute("INSERT INTO threads (community_id, title, created_by, created_at) VALUES (1, ?, 4, ?)",
                           ("授乳・おむつ替えスペースの不足について", now))
        tid = cur.lastrowid
        conn.execute("INSERT INTO posts (thread_id, user_id, text, created_at) VALUES (?,?,?,?)",
                     (tid, 4, "駅周辺に授乳スペースがもっと欲しいです。外出中に困りました。", now))
        conn.execute("INSERT INTO posts (thread_id, user_id, text, created_at) VALUES (?,?,?,?)",
                     (tid, 3, "現状の設置場所と混雑状況を把握したいです。情報提供をお願いします。", now + 1))
        for title, desc, fmt, path, gran, tags in _write_samples(os.path.abspath(datasets_dir())):
            conn.execute(
                "INSERT INTO datasets (title, publisher, description, source_url, license, file_format, file_path,"
                " updated_on, granularity, tags, is_sample) VALUES (?,?,?,?,?,?,?,?,?,?,1)",
                (title, SAMPLE_PUBLISHER, desc, "", "サンプル（架空データ・利用条件なし）", fmt, path, "2026-10-01", gran, tags))
    print(f"seeded {db_path()}")


if __name__ == "__main__":
    seed()
