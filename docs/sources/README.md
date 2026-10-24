# 公開資料（資料台帳）

[vision-sourcing.md](../vision-sourcing.md) の手順 S1 で集めた渋谷区の公開資料。各ファイル先頭の
`probe_source` が台帳の 1 行で、probe-agent はそれを読んで資料ごとの属性と検査結果を出す
（`GET /source-register`）。手法は probe-agent の
[vision-to-feature-research.md](https://github.com/dx-junkyard/probe-agent/blob/ura/docs/01-specifications/product/vision-to-feature-research.md) §3.3。

- 渋谷区サイトの転載条件を確認できなかったため、どのファイルも **原文ではなく要約** で、頁番号で原典に戻れる。
  成果指標・調査結果の数値は原文どおり。
- 読んだ範囲は各ファイルの `coverage` に書く。書いていない部分は読んでいない（「書かれていない」とは別）。

## 取り込み状況（2026-10-24）

| source_id | 層 | 状態 |
| --- | --- | --- |
| SRC-shibuya-basic-concept-2016 | SL-1 | 取り込み済み（未来像・A/G 分野・区政運営の基本姿勢） |
| SRC-shibuya-ltp-2017-2026 | SL-2 | 取り込み済み（A 分野 子育て支援の充実のみ）。計画期間は 2026 年度末まで |
| SRC-shibuya-ltp-2027-2036-outline | SL-2 | 取り込み済み（検討委員会資料・案） |
| SRC-shibuya-ltp-2027-2036-policy-aims | SL-2 | 取り込み済み（検討委員会資料・案） |
| SRC-shibuya-ltp-2027-2036 | SL-2 | **取得不可**: 素案が未公表 |
| SRC-shibuya-ltp-2017-2026-final-eval | SL-5 | 取り込み済み（全体の達成状況のみ） |
| SRC-shibuya-ltp-2027-2036-issues | SL-5 | 取り込み済み（子育て支援、市街地整備・景観デザイン、地域コミュニティ） |
| SRC-shibuya-survey-2025 | SL-5 | 取り込み済み（区民調査の一部） |
| SRC-shibuya-park-list-opendata | SL-5 | 取り込み済み（都市公園一覧オープンデータの集計。外遊びの場の現状） |
| SRC-shibuaso-playparks | SL-5 | 取り込み済み（区外の団体によるプレーパーク 2 か所の説明） |

## まだ探していない資料

台帳に行がないものは、探していない（存在しない、ではない）。次の一周の候補:

- SL-3 子育て分野の個別計画（子ども・子育て支援事業計画、こども計画）。2026-10-24 に Web 検索と区のオープンデータ
  カタログで探したが見つけられなかった（区サイト内の該当ページは未確認）
- SL-3 公園・みどりの計画（みどりの基本計画、「渋谷区魅力ある公園整備計画」（令和3年8月）。後者は区の千原児童遊園地の
  ニュースで言及を確認、2026-10-24）、DX・オープンデータ関連の計画
- SL-4 実施計画 2023-2026、予算資料
- SL-5 区民アンケート調査報告書（詳細版）、在勤者・来街者調査、SHIBUYA CITY DASHBOARD の既存レポート
