# 渋谷共創ダッシュボード

都知事杯 Open Data Hackathon 2025 渋谷区課題「ダッシュボードの新規レポートの開発」への提案として作った、
**実際に動くシステム（MVP）** と、その目的・UX・機能の正本の文書。代表シナリオ（授乳・おむつ替えスポット）を
ニュースから区の採用判断・施策ニュースまで画面で通しで操作できる（実装状況は [docs/features.md §7](docs/features.md#7-実装状況と検証2026-10-20)）。
System Purpose（目的の正本）は [docs/vision.md §2](docs/vision.md#2-vision) の 1 文だけで、この README の説明は補足である。

> **住民の声がダッシュボードになる。** ニュースを起点に区民・来訪者・事業者の関心を AI 対話で言葉にし、
> 根拠と KPI を持つ課題カードへ整理して、当事者が KPI 追跡ダッシュボードとして公開し、区が採用判断する。

- 目的・対象者・到達目標: [docs/vision.md](docs/vision.md)
- 利用体験（Journey / UX Requirement）: [docs/ux.md](docs/ux.md)
- 機能（Feature）と MVP の範囲: [docs/features.md](docs/features.md)
- 区の公開資料から Vision・UX・Feature を導く設定と計画: [docs/vision-sourcing.md](docs/vision-sourcing.md)

設計と改善は [probe-agent](https://github.com/dx-junkyard/probe-agent) で行っている（インタビューによる UX の磨き込み、
Objective → Journey → Requirement → Feature の登録、AI エージェントの trace と shadow 比較）。

## 構成

```
apps/
  api/   FastAPI + SQLite。AI エージェント（@probe で probe-agent に trace を送る）
  web/   React + Vite + Tailwind。下部 6 タブのモバイル向け画面
docs/    vision / ux / features
probe-agent.yml  probe-agent が読む対象リポジトリ設定
```

## 起動（ローカル）

```bash
cd apps/api
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m app.seed
.venv/bin/python -m app.ingest all   # 実データ（東京都・渋谷区のオープンデータ、区のニュース）を取り込む。任意
LLM_API_KEY=... .venv/bin/uvicorn app.main:app --port 8100
```

```bash
cd apps/web
npm install
npm run dev
```

http://localhost:5180 を開き、右上で利用者（保護者・区職員など）を切り替える。

| 環境変数 | 意味 |
| --- | --- |
| `LLM_PROVIDER` | `openai`（既定）または `anthropic`。`anthropic` にすると Claude API（既定モデル Claude Opus 5.5）を使う |
| `ANTHROPIC_API_KEY` | `LLM_PROVIDER=anthropic` のときの Claude API キー。代わりに `ant auth login` のプロファイルも使える。Claude Code のサブスクリプション（ログイン）は使わない |
| `LLM_EFFORT` | `anthropic` のときの effort（既定 `medium`） |
| `LLM_API_KEY` | `LLM_PROVIDER=openai` のときの OpenAI 互換 API のキー。未設定なら AI は使えず、手入力で操作できる（AI 失敗を成功に見せない） |
| `LLM_MODEL` | モデルを上書きする。既定は `openai` なら `gpt-5.4-mini`、`anthropic` なら `claude-opus-5-5` |
| `PROBE_ENABLED` / `PROBE_SERVER_URL` / `PROBE_API_KEY` | probe-agent へ trace を送る。SDK は `pip install -e <probe-agent>/packages/python-probe` |

テスト: `apps/api/.venv/bin/python -m pytest apps/api/tests`

## データについて

シードのニュースとデータセットはすべて **架空のデモ用サンプル** で、画面と CSV に「サンプル（架空）」と表示する。

実データは次の 2 つの方法で、出典・提供者・ライセンス・更新日付きで登録する。

- `python -m app.ingest [datasets|news|all]`: 東京都オープンデータカタログ（CKAN）・渋谷区オープンデータ（ArcGIS Hub）から
  代表シナリオのデータセットを、渋谷区ホームページの新着情報を担当課・掲載日付きで取り込む。取得できなかったものは
  架空の値で埋めず `GET /api/ingest-runs` に記録する。対象と確認結果は [docs/features.md §7](docs/features.md#7-実装状況と検証2026-10-20)。
- 「データセット登録」API（CSV / Excel / PDF / HTML）。PDF は罫線のある表、HTML は table 要素を読み取る。
