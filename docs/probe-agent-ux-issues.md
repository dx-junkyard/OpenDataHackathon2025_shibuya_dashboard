# probe-agent の UX 上の問題点

- 調査日: 2026-10-21
- 対象: ローカルの probe-agent（control-server / dashboard、ブランチ `ura`、commit `e7733e9` で再ビルドしたコンテナ）
- 方法: ダッシュボード（http://localhost:8501）を実際に操作した。対象は System 7「渋谷共創ダッシュボード」（trace なし）と System 5「probe-agent」（trace 185 件）。遅延は API の所要時間を計測し、原因は退避したデータのコピーをプロファイルして特定した。
- 観点: (1) probe を入れた箇所の動作確認を視覚的にしやすいか、(2) システム全体の動作を理解しやすいか

## 優先度の一覧

| # | 問題 | 観点 | 優先度 | 規模感 |
| --- | --- | --- | --- | --- |
| P-1 | どのページも開くたびに 15〜25 秒止まる（`/system-state` が遅い） | 基盤 | **最優先** | 小（10 行程度＋キャッシュ） |
| P-2 | 「probe を入れた所」と「trace が届いた所」の対応が見えない | 動作確認 | 高 | 中 |
| P-3 | `observe.observed(...)` で包む計測方式を計測点として認識しない | 動作確認 | 高 | 小〜中 |
| P-4 | アプリを操作しながら probe の動作を確かめる手段がない | 動作確認 | 中 | 中〜大 |
| P-5 | trace 1 件の中身（コード位置・呼び出し元・前後関係）が分からない | 動作確認 | 中 | 中 |
| P-6 | 呼び出しグラフに誤った辺があり、重要な辺が未解決 | 全体理解 | 高 | 中 |
| P-7 | 画面によって計測メタデータの有無の表示が食い違う | 全体理解 | 中 | 小 |
| P-8 | エントリーポイントのパスにルーターの前置き（`/api`）がない | 全体理解 | 低 | 小 |
| P-9 | 全体像をつかむ入口がない（ナビゲーション 30 項目以上、英日混在） | 全体理解 | 中 | 大 |
| P-10 | 観測状況の重ね表示が、trace がないと何も見せない | 動作確認 | 低 | 小 |

## 修正と再検証の結果（2026-10-21）

probe-agent を指摘に沿って修正し（ブランチ `ura`）、コンテナを作り直して、渋谷共創ダッシュボード（System 7）で検証し直した。
検証では、渋谷共創ダッシュボードの API を probe-agent の SDK 付きで起動し（AI の応答はスタブ。System 7 専用のテスト用トークンで送信）、
アプリを操作しながら probe-agent の画面を確認した。

| # | 修正 | 再検証の結果 |
| --- | --- | --- |
| P-1 | 照合の索引を 1 回だけ作る。API とエントリーポイントの照合を索引で引く。Gap ごとのグラフ全走査をやめる（結果は旧実装とランダム 3,000 通りずつで一致） | System 5 の `/system-state` が 24,969 ms → 1,087〜2,140 ms。ログイン確認は 20 ms で、15 秒のタイムアウトに当たらなくなった |
| P-2 | 「計測カバレッジ」画面（`/instrumentation-coverage`）と API を追加。計測点ごとに 受信中 / エラーあり / 未受信 / 説明のみ を、アイコンと文字で示す | 操作前は AI エージェント 7 件が「未受信」。4 つの操作の後、該当する 4 件が「受信中」になり、通らなかった 3 件は「未受信」のまま残った |
| P-3 | `probe-agent.yml` の `instrumentation.decorators` で計測用ラッパーを宣言できるようにし、索引で component id を結び付ける | `observe.observed(...)` の 7 エージェントすべてが計測点として認識された（修正前は 0 件） |
| P-4 | 計測カバレッジ画面に「ライブ表示」（3 秒ごと）。直近の trace を、コードの位置・所要時間・秘匿処理済みの入出力の先頭付きで流し、今届いた行を強調する | アプリを操作して 2 秒以内に 4 件が流れ、表の行に「今届いた」が付いた。失敗させた検索エージェントは「エラーあり」と `LLMUnavailable` が出た |
| P-5 | trace の詳細に「記録したコード（ファイル:行・シンボル）・入口」を表示 | `apps/api/app/agents/thread_summary.py:63 summarize` が表示された |
| P-6 | 呼び出し先を import で解決する（`llm.complete_json` → `app/llm.py`）。リテラル・式に対するメソッド呼び出しは同名の関数に結び付けない。未知のオブジェクトのメソッドは、そのクラスがファイルに出てくるときだけ推測とする | `summarize_thread → summarize → complete_json → provider` がすべて「解決済み」になり、確度は 50% → 100%。誤った `join`・`_HtmlTables.close` の辺は消えた |
| P-7 | 階層が未分類のとき、ソースのメタデータで分類する | API Role が「classified」になり、Capability・Role・Probe value が表示された |
| P-8 | `for r in (...): app.include_router(r, prefix=...)` を展開する | `POST /api/threads/{tid}/summary` と表示された |
| P-9 | 「システムマップ」画面（`/system-map`）。Feature ごとに、その番号をメタデータに書いたコード・入口・受信状況を並べる。サイドバーの目的別の入口に「全体を見渡す」「動作を確かめる」を追加 | Feature 22 件中 10 件がコードと結び付いた。未実装の F-11 は「コードなし」と出た（GAP-4.1-A と一致） |
| P-10 | Flow Explorer のノードに、計測なし / 計測あり・未観測 / 観測済み / エラー を常に表示 | `summarize` に「観測済み 1 trace」、他のノードに「計測なし」が出た |

**再検証で新たに見つけて直したもの**

| # | 見つかったこと | 対応 |
| --- | --- | --- |
| A | 計測カバレッジの入口の列に `/api` の前置きがなかった（シンボル索引の値を使っていた） | 前置きを付けて組み立て済みのエントリーポイントから取る |
| B | システムマップの 22 件中 20 件が「コードなし」だった | 渋谷共創ダッシュボード側で、計測メタデータの capability に Feature 番号を書いた（推薦エージェントにはメタデータを追加） |
| C | 右下の通知の吹き出しが閉じられず、未接続の案内やライブ表示の行を覆っていた | 閉じるボタンを付け、閉じた内容はそのタブでは再表示しない |
| D | 候補フローに、途中だけが違う経路が同じ表記で 2 回並んだ（`a → b → … → provider`） | 6 ノードまでは全部表示し、長い場合も最後から 2 番目を残す |

**まだ残っていること**

- P-5 のうち、呼び出し元の HTTP リクエストと前後の呼び出しのウォーターフォール。SDK が trace の親子関係を送っていないため、SDK 側の変更が必要。
- P-1 の `/system-state` は、System 5 でまだ 1〜2 秒かかる。照合の結果を snapshot ごとに保存して再利用すれば、さらに短くできる。
- システムマップの Feature とコードの対応は、メタデータに番号が書かれていることが前提。F-01・F-04・F-10 などは実装済みだが、ルート関数にメタデータがないため「コードなし」と出る（書き漏れが見える形になった）。
- 実際の LLM での trace はまだ送っていない（AI の応答はスタブ）。

---

## P-1 どのページも開くたびに 15〜25 秒止まる

**現象**

- System 5 では、どのページを開いても「サーバーの応答を待っています」が長く続く。
- 全ページで最初に呼ばれる `/api/system-state` の所要時間を計測した（同じ条件で順に呼んだもの）。

| API | System 5 | System 7 |
| --- | --- | --- |
| `/api/system-state` | **24,969 ms** | 52 ms |
| `/api/auth/me` | 21 ms（単独）／15,003 ms（system-state と同時） | — |
| `/api/components` ほか | 15〜30 ms | — |

- `/api/auth/me` は画面側で 15 秒のタイムアウト（`AUTH_BOOTSTRAP_TIMEOUT_MS`）が設定されている。そのため、system-state と同時に出ると、毎回ちょうど 15,003 ms で打ち切られる。

**原因**

- `build_system_state` → `_open_gap_triage_item` → `_load_gaps_from_reconciler` → `docs_code_reconciler.reconcile` が、リクエストのたびに「ドキュメントとコードの照合」を最初から計算している。
- その中の `_match_symbols_to_code` が、呼ばれるたびにシンボル名の索引（約 1.2 万件）を作り直している。呼び出しはドキュメントの要素ごとに 5,259 回ある。
- 名前の正規化 `_normalize_symbol` は **6,481 万回**呼ばれていた（プロファイルでは 79 秒のうち 74 秒）。
- control-server は DB へのアクセスをプロセス全体で 1 つのロックで直列にしている（`app/db.py`）。そのため、この 1 本が全リクエストを止める。

**提案**

1. 索引（正規化済みの名前 → シンボル、末尾の名前 → シンボル）を `reconcile` で 1 回だけ作り、`_match_symbols_to_code` に渡す。
2. 照合の結果を snapshot ごとに保存し、`system-state` はそれを読むだけにする。
3. 回帰テスト: シンボル 1 万件・ドキュメントの要素 5 千件で、`system-state` が 1 秒以内に返ること。

**該当箇所:** `apps/control-server/app/docs_code_reconciler.py`（`_match_symbols_to_code`、`reconcile`）、`app/system_state.py`（`_open_gap_triage_item`）

---

## P-2 「probe を入れた所」と「trace が届いた所」の対応が見えない

**現象**

- Components 画面は、trace を受信した component だけを一覧にする。
- System 7 には `probe-agent:` メタデータ付きの関数が 16 個あり、AI エージェントの component id もコードにある。それなのに画面には「component がありません」と Setup Guide へのリンクしか出ない。
- 計測を入れた後に「どれが動いていて、どれがまだ一度も呼ばれていないか」を確かめる画面がない。

**影響**

- probe を入れた直後の確認（届いているか、入れ漏れがないか）を、利用者が頭の中で突き合わせるしかない。

**提案**

- **計測カバレッジ表**を作る。
  - 行: コード上の計測点（`@probe`、`observed(...)`、`probe-agent:` メタデータの component）
  - 列: 状態（未接続 / 計測あり・未受信 / 受信中 / エラーあり）、最後に受信した時刻、件数、エラー率、コードへのリンク、対応する Feature・Journey
- SDK が未接続の場合は、計測点一覧の上に「未接続」と次の操作（Connect SDK）を出す。

---

## P-3 `observe.observed(...)` で包む計測方式を計測点として認識しない

**現象**

- 渋谷共創ダッシュボードは、SDK がなくても動くように `observe.observed("thread-summary-agent")` で包んで計測している。しかし、シンボル索引の `component_id` は空のまま（`summarize_thread` などで確認）。
- materialize は、この方式を前提にせず、`@probe` と無条件の `from probe_agent import probe` を追加する。SDK を任意の依存にしているリポジトリでは、そのまま採用するとアプリが起動しない。

**提案**

- 設定（`probe-agent.yml`）で計測用のラッパー（例: `observe.observed` の第 1 引数が component id）を宣言できるようにし、索引で component id を結び付ける。
- materialize は、ラッパーが宣言されていればそれを使う。宣言がなければ、import を SDK の有無で切り替える形で入れる。

---

## P-4 アプリを操作しながら probe の動作を確かめる手段がない

**現象**

- trace は Components 画面の表（ID・mode・時間・状態）で後から見るだけ。
- 「この画面のこのボタンを押したら、どの probe が動いたか」をその場で確かめられない。

**提案**

- **ライブ表示**: 受信した trace を新しい順に流す（component・所要時間・成否・入出力の要約）。
- 同時に、Flow Explorer のグラフ上で該当する計測点を光らせる。
- 開発用の画面と並べて使うことを想定し、狭い幅でも見られる表示にする。

---

## P-5 trace 1 件の中身が分からない

**現象**

- trace の詳細は「入力: オブジェクト 2 件・39 B / 出力: 文字列 978 B」と「中身を表示」ボタン、操作ボタンだけ（System 5 の `get_screen_context`）。
- 次の情報がない。
  - コードのどこで記録されたか（ファイルと行）
  - どの HTTP リクエスト・画面操作から呼ばれたか
  - 同じリクエストの中の前後の呼び出し
- 一覧の Duration が全件「<1ms」と表示され、比較の手がかりにならない。

**提案**

- 1 回のリクエストの中の呼び出しを、時系列の帯（ウォーターフォール）で表示する。
- コード位置へのリンクと、呼び出し元のエントリーポイントを表示する。
- 入出力の要約は、秘匿処理をしたうえで最初から見せる（開かなくても主要な値が分かる）。

---

## P-6 呼び出しグラフに誤った辺があり、重要な辺が未解決

**現象**（Flow Explorer で `POST /threads/{tid}/summary` を選択）

- `summarize` → `join`: 実際は文字列の `"\n\n".join(lines)`。名前が同じだけのコミュニティ参加 API の `join`（`routes/communities.py`）につながっている。
- `summarize` → `_HtmlTables.close`: 無関係な `agents/shaping.py` のメソッドにつながっている。
- `summarize` → `complete_json()`: LLM を呼ぶ一番重要な辺が `unresolved` のまま（`llm.complete_json` のモジュール属性呼び出し）。
- 全ノードの確度が `low`、候補フローの確度が 50%。

**影響**

- グラフを見て理解した内容が誤りになる。probe を置く場所の選択（Flow Explorer → Probe Plan）を誤らせる。

**提案**

- import 文とモジュール属性（`from .. import llm` → `llm.complete_json`）で呼び出し先を解決する。
- `str.join` や `list.append` など組み込み型のメソッド名は、同名の関数に結び付けない。
- 確度の低い推測の辺は初期状態で隠し、「推測を表示」で出す。

**該当箇所:** `apps/control-server/app/` のフロー解析（`repository/flow-graphs`）

---

## P-7 画面によって計測メタデータの有無の表示が食い違う

**現象**

- `summarize_thread` には `probe-agent:` メタデータがある。シンボル索引の `source_metadata` にも入っている。
- それなのに、Flow Explorer の API Role は「unclassified / No source-authored explanation yet. Add a probe-agent docstring block」と表示し、Freshness は `stale` になっている。

**提案**

- API Role の説明を、シンボル索引のメタデータから作る。古い説明が残っている場合は、その理由（どの snapshot の説明か）を表示する。

---

## P-8 エントリーポイントのパスにルーターの前置きがない

**現象**

- Flow Explorer のエントリーポイント一覧が `GET /communities` のように表示される。実際の URL は `GET /api/communities`（`app.include_router(..., prefix="/api")`）。`main.py` に直接書かれた `GET /api/health` だけが正しい。

**提案**

- `include_router` の `prefix` を解析して、パスに反映する。

---

## P-9 全体像をつかむ入口がない

**現象**

- ナビゲーションが 30 項目以上ある（System Understanding、Interview、UX Design Studio、Capability Map、Feature Map、Flow Explorer、Stakeholder Value Network、Journey Service Blueprint、Functional Lineage、Objective Map、Probe Planner、Probe Patterns、Components / Traces、Experiments、Trace Lineage、Trace Analyzers、Cell Fabric、Evolution Node など）。
- 英語と日本語の表記が混在している。
- 登録した Objective・Journey・Feature と、コード（エントリーポイント・エージェント）と、実行時の状況（trace）を 1 枚で追える画面がない。

**提案**

- **システムマップ**を入口にする: Feature（例: F-05）→ エントリーポイント → AI エージェント・LLM・DB を 1 枚に並べ、各要素に受信の状況（P-2）を重ねる。各要素から詳細画面（Flow Explorer、Components 等）へ移れるようにする。
- ナビゲーションは、目的（理解する・設計する・計測する・比較評価する）の 4 つの入口に絞る。それ以外の画面は各入口の中から開く。

---

## P-10 観測状況の重ね表示が、trace がないと何も見せない

**現象**

- Flow Explorer の候補フローに「observed 0/7 nodes」と出る。観測済みと未観測を区別する良い仕組みだが、重ね表示（Runtime overlay）は手動で「Apply overlay」を押す必要がある。trace がないと何も変わらない。

**提案**

- 重ね表示を初期状態で有効にし、ノードを「未計測 / 計測あり・未観測 / 観測済み / エラー」で色分けする（色だけに頼らず、記号も付ける）。

---

## 参考: 同じ調査の過程で見つけて修正済みの問題

probe-agent のブランチ `ura`、commit `e94f88d` と `e7733e9` で修正した。

| 問題 | 原因 | 修正 |
| --- | --- | --- |
| Interview で回答済みの質問が言い換えて繰り返し出る | 回答の予算 4,000 字を新しい回答から切っていた。回答をグラフの後ろに置き、プロンプトも末尾から切っていた | 回答をグラフの前に置き、新しいものから項目単位で収める。再質問の除去も加えた |
| 回答後の自動の理解更新が「待機中」のまま残り、画面が「更新中」で止まる | スレッドが失われたジョブを拾う仕組みがない | 起動時に、残ったジョブを理由付きの失敗として閉じる |
| 提案を編集しても元の値のまま見える | 一覧が編集値を返していなかった | `edited_metadata` を返し、画面にも出す |
| 1 件でも差分にできないと materialize 全体が失敗する | パス由来のモジュール名を扱えない | モジュールの docstring として扱う |
| ルート関数の `@probe` が計測されない | `@router.post` の外側に入れていた | `def` の直上に入れる |
| 名指ししたファイルが提案の対象にできない | コンテキストパックが上限で、パス順の後ろを落としていた | 名指しされたファイルを優先して残す |
