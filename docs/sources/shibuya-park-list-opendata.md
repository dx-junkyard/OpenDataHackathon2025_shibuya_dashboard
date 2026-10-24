---
probe_source:
  source_id: SRC-shibuya-park-list-opendata
  layer: SL-5
  title: 【渋谷区】都市公園・都立公園一覧（オープンデータ、CSV）
  publisher: 渋谷区（東京都オープンデータカタログ掲載）
  url: https://catalog.data.metro.tokyo.lg.jp/dataset/t131130d2025000003
  issued: 2026-03-30
  edition: final
  retrieved: 2026-10-24
  content_digest: sha256:cb43d14cb88fa6fa1a8e5792d1e49311dd2071a18144ad7acba60ebc885d2bbe
  coverage: CSV 全 123 行を集計した内容の説明（CSV 本体は https://www.opendata.metro.tokyo.lg.jp/shibuya/131130_shibuyaku_toshitoritukouen.csv、取得時 sha256:70348f02764b6ee996ef5d1b455dcdddc7f28796303251dd5ce23e208fe09ba9）
  status: current
  license_note: CC BY（クリエイティブ・コモンズ 表示）。集計値と列の説明のみを置く
---
# 渋谷区 都市公園・都立公園一覧（オープンデータ）の内容

カタログの最終更新は 2026-03-30（CSV ファイル自体の更新日は 2026-01-26）。

## 件数と分類（2026-10-24 取得時）

- 全 123 件。名称で分けると、公園 77 件、児童遊園地 43 件、緑地など 3 件（臨川四季の森、鶯谷緑地、羽澤緑地）。
- プレーパークのある公園も含まれる: はるのおがわコミュニティパーク、恵比寿南一公園。
- 表題は「都市公園・都立公園一覧」だが、代々木公園など都立公園の名称は一覧に見当たらない（名称の一致で確認）。

## 列と欠けている値

- 列: 全国地方公共団体コード、ID、地方公共団体名、名称、所在地（連結表記・町字・番地以下）、緯度、経度、面積(㎡)、備考。
- 面積(㎡) はすべて空欄。公園の広さや区民 1 人当たりの面積はこのデータからは測れない。
- 備考に開園時間が書かれているのは 10 件のみ。遊具、ボール遊びの可否、プレーパークの有無などの列はない。
- 各行に緯度・経度がある。
