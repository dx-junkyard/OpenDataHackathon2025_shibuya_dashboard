# 渋谷共創ダッシュボード

都知事杯 Open Data Hackathon 2025 渋谷区課題「ダッシュボードの新規レポートの開発」への提案。

> **住民の声がダッシュボードになる。** ニュースを起点に区民・来訪者・事業者の関心を AI 対話で言葉にし、
> 根拠と KPI を持つ課題カードへ整理して、当事者が KPI 追跡ダッシュボードとして公開し、区が採用判断する。

- 目的・対象者・到達目標: [docs/vision.md](docs/vision.md)
- 利用体験（Journey / UX Requirement）: [docs/ux.md](docs/ux.md)
- 機能（Feature）と MVP の範囲: [docs/features.md](docs/features.md)

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
| `LLM_API_KEY` | OpenAI 互換 API のキー。未設定なら AI は使えず、手入力で操作できる（AI 失敗を成功に見せない） |
| `LLM_MODEL` | 既定 `gpt-5.4-mini` |
| `PROBE_ENABLED` / `PROBE_SERVER_URL` / `PROBE_API_KEY` | probe-agent へ trace を送る。SDK は `pip install -e <probe-agent>/packages/python-probe` |

テスト: `apps/api/.venv/bin/python -m pytest apps/api/tests`

## データについて

シードのニュースとデータセットはすべて **架空のデモ用サンプル** で、画面と CSV に「サンプル（架空）」と表示する。
実データは「データセット登録」API（CSV / Excel）から出典・ライセンス付きで登録する。
