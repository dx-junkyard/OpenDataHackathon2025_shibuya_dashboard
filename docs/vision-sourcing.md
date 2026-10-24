# 渋谷区の公開資料から Vision・UX・Feature を導く（ドメイン設定）

**文書の役割:** probe-agent の手法「Vision → UX → Feature の調査手法」を、渋谷共創ダッシュボードに当てはめる設定と実行計画
**手法の正本:** [probe-agent docs/01-specifications/product/vision-to-feature-research.md](https://github.com/dx-junkyard/probe-agent/blob/ura/docs/01-specifications/product/vision-to-feature-research.md)（手順 VF-S0〜S9、区別 VF-D1〜D5、主張の型、現状 C-1〜C-3、仮説構築はそちらが所有する）
**関係する正本:** [Vision](vision.md) → [UX](ux.md) → [Feature](features.md)。この文書はそれらの中身を所有せず、根拠をどう集めて更新するかの渋谷区向けの具体値だけを持つ
**状態:** draft（2026-10-24）。資料の取り込み（S1）は未実施

手法そのもの（何を区別し、どの順で調べ、どう仮説を立てるか）はここに書かない。
ここに書くのは、手法の §7「ドメイン設定」の各項目に対する渋谷区での値である。

---

## 1. Sponsor と受益者

| 手法の役割 | このプロジェクトでの値 |
| --- | --- |
| Sponsor | 渋谷区（Stakeholder key `shibuya-city`）。区の政策目標は、この Stakeholder の Need（`expectation` / `constraint`）として持つ。[Vision の STK-5](vision.md#3-stakeholder-と-need)（区の各課の職員）は利用者としての区であり、Sponsor の方針とは分けて扱う |
| 受益者 | [Vision §3](vision.md#3-stakeholder-と-need) の STK-1 住民、STK-2 来訪者、STK-3 事業者、STK-4 コミュニティ。STK-6 データ提供者は Later |

区の計画書に書かれた課題認識（`problem_statement`）は区の認識であり、STK-1〜4 の困りごとの証拠にはしない
（手法 VF-D2）。本製品の出発点である「ダッシュボードが行政内部の視点に偏る」（[Vision §1](vision.md#1-背景となる行政課題)）は、
まさにこの区別を崩さないための理由である。

## 2. 資料の層の具体名

| 層 | 資料（候補） | 確認事項 |
| --- | --- | --- |
| SL-1 最上位方針 | 渋谷区基本構想（2016 年 10 月策定） | 7 つの分野の目指す姿。[Vision の AREA-1..7](vision.md#渋谷区-7-つの注力分野課題カードの分類軸) の出典頁を付ける |
| SL-2 中長期計画 | 渋谷区長期基本計画 2017-2026 | **計画期間が 2026 年度で終わる**。次期計画（素案・パブリックコメント版を含む）が公開されているかを最初に確認する。素案は `draft` として取り込む |
| SL-3 領域別計画 | 子育て・福祉・防災・DX・都市計画・オープンデータ関連の個別計画 | 代表シナリオの分野（子育て、AREA-1）を優先する |
| SL-4 実行計画・予算・事業 | 実施計画、予算の説明資料、新規事業の発表 | 担当課と事業名（職員ビュー F-13 の担当課の根拠にもなる） |
| SL-5 評価・統計・調査 | 区民意識調査、事業評価、区の統計、SHIBUYA CITY DASHBOARD の公開レポート、都・区のオープンデータ | 現状（C-1）の証拠として使う |

この表の資料名は候補で、存在・版・URL は S1 で確認して台帳に記録する（2026-10-24 時点で、次期長期基本計画の
公開状況は未確認）。

## 3. 主張の型の追加

手法 §3.2 の型に、次の 1 つを追加する。

| 型 | 内容 | 行き先 |
| --- | --- | --- |
| `focus_area` | 区の 7 つの注力分野への分類（AREA-1..7） | 課題カードの注力分野（F-07）、Objective と区の目標の relation の受け皿 |

`indicator`（指標・目標値）は、課題カードの KPI 候補（F-07）の根拠としても使う。区の指標を KPI に採るときも、
採るかどうかは当事者が決める（[Vision P-2](vision.md#7-製品原則)）。

## 4. 現状の証拠源

| 種類 | このプロジェクトでの情報源 |
| --- | --- |
| C-1 環境・受益者の現状 | 区民意識調査、区・都の統計とオープンデータ、SHIBUYA CITY DASHBOARD の既存レポート。データの入手見込みは F-08 の判定を使う |
| C-2 既存の手段と当事者の行動 | 区の既存の声の受け付け（窓口・区民の声・SNS）、既存の SHIBUYA CITY DASHBOARD の使われ方、[UX §5 のペルソナ検証](ux.md#5-代表シナリオでの検証)、聞き取り。本製品がない状態の as-is Journey として書く |
| C-3 本システムの現状 | [features.md §7](features.md#7-実装状況と検証2026-10-20)、probe-agent の System 7（Feature とコードの対応、計測カバレッジ、trace） |

## 5. 台帳の場所

```text
docs/sources/
  README.md      台帳（手法 §3.3 の項目）。取得できなかった資料も行を持つ
  <source_id>.md 本文（ページ境界付き Markdown）
  <source_id>-indicators.csv  指標表（必要なとき）
```

`probe-agent.yml` の `repository.include` にある `docs/**` に含まれるので、設定変更は不要。
転載条件が合わない資料は、本文ではなく要約と頁参照だけを置く。

## 6. 最初の調査目的（S0 の初期値）

> 区の公開方針（次期長期基本計画を含む）に照らして、OBJ-1..5 と F-01..22 の優先度が区の目標に沿っているか、
> 寄与先のない区の目標から新しい Objective が必要かを判断する。

対象範囲は、まず代表シナリオの分野（AREA-1 子育て）と、本製品の前提であるデータ活用・DX 分野に絞る。

## 7. 最初の一周の計画

| 手順 | このプロジェクトでやること | 結果の反映先 |
| --- | --- | --- |
| S1 | §2 の資料を台帳に載せ、取り込めたもの・取り込めなかったものを記録してコミットする | `docs/sources/` |
| S2〜S3 | 基本構想・長期基本計画から目指す姿・政策目標・指標を抽出し、AREA-1..7 に頁根拠を付ける。新旧計画の食い違いを矛盾として出す | [vision.md §5](vision.md#5-product-objective-と-milestone) |
| S4 | OBJ-1..5 と区の政策目標の relation を確定する。寄与先のない区の目標を一覧にする | vision.md、probe-agent の Purpose relation |
| S5〜S6 | AREA-1 の as-is Journey（本製品がない状態で、保護者が授乳・おむつ替えの困りごとをどう伝えているか）を書き、J-1..6 の baseline にする | [ux.md](ux.md) |
| S7〜S8 | 代表シナリオの Gap ごとに競合する原因仮説を 2 つ以上立て、調べてから埋め方（既存 F-xx の拡張・新規・運用・区の判断）を選ぶ | [features.md](features.md)、probe-agent の Gap / Feature |
| S9 | 次期長期基本計画が確定・公開されたら台帳を更新し、要再確認になった relation・Gap・Feature を見直す | 各文書 |

各手順の結果はコミットし、probe-agent の snapshot・System Understanding・Interview を更新してから次へ進む。
手法側の不足（外部資料の自動取得をしない、PDF を直接読まない等。手法 §9）は、この計画では
「外で取り込んでコミットする」「候補は文書に書いて Interview に読ませる」で回避する。
