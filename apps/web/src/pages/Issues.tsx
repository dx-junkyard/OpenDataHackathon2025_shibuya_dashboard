import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError, getUserId, type Dataset, type DashboardView, type IssueCard, type Kpi, type Proposal } from "../api";
import { CommunityLink } from "../components/CommunityLink";
import { DashboardAnnotations } from "../components/DashboardAnnotations";
import { KpiCard } from "../components/KpiCard";
import { SurveyComposer } from "../components/SurveyComposer";
import { AiBadge, Button, Card, ErrorNote, Loading, SampleBadge } from "../components/ui";

const AVAIL = { open_data: "公開データあり", survey_needed: "アンケートが必要", unknown: "入手方法は不明" };

export function IssueList() {
  const q = useQuery({ queryKey: ["issues"], queryFn: () => api<{ items: IssueCard[] }>("/issue-cards") });
  return (
    <>
      <div className="flex justify-end">
        <Link to="/issues/new" className="text-sm font-semibold text-brand-strong underline">＋ 手入力で課題カードを作る</Link>
      </div>
      {q.isLoading && <Loading />}
      <ErrorNote error={q.error} />
      {q.data?.items.length === 0 && <Card><p className="text-sm text-muted">まだ課題カードはありません。ニュースから作ってみましょう。</p></Card>}
      {q.data?.items.map((c) => (
        <Link key={c.id} to={`/issues/${c.id}`} className="block">
          <Card className="hover:border-brand">
            <p className="text-xs text-muted">{c.status_label}・{c.focus_area_label || "注力分野 未設定"}</p>
            <h2 className="mt-1 font-bold">{c.title}</h2>
            <p className="mt-1 text-xs text-muted">KPI: {c.kpis.map((k) => k.name).join("、") || "なし"}</p>
          </Card>
        </Link>
      ))}
    </>
  );
}

type Candidates = { searched_count: number; candidates: { dataset: Dataset; reason: string }[] };
type Plan = {
  dataset_id: number;
  plan: { feasible: boolean; steps: string[]; aggregation: string; period: string; cumulative: boolean };
  columns: string[];
  before_sample: Record<string, string>[];
  after_preview: { period: string; value: number }[];
  preview_error: string;
  warnings: string[];
};

function KpiData({ kpi, onDone }: { kpi: Kpi; onDone: () => void }) {
  const [search, setSearch] = useState<Proposal<Candidates> | null>(null);
  const [plan, setPlan] = useState<Proposal<Plan> | null>(null);
  const [target, setTarget] = useState(kpi.target_value?.toString() ?? "");
  const [direction, setDirection] = useState<"increase" | "decrease">(kpi.target_direction ?? "increase");
  const find = useMutation({ mutationFn: () => api<Proposal<Candidates>>(`/kpis/${kpi.id}/dataset-search`, { method: "POST" }), onSuccess: setSearch });
  const shape = useMutation({
    mutationFn: (datasetId: number) =>
      api<Proposal<Plan>>(`/kpis/${kpi.id}/shaping-plans`, { method: "POST", json: { dataset_id: datasetId, search_proposal_id: search?.id } }),
    onSuccess: setPlan,
  });
  const adopt = useMutation({
    mutationFn: () => api(`/shaping-plans/${plan!.id}/adopt`, { method: "POST", json: {} }),
    onSuccess: () => {
      setPlan(null);
      setSearch(null);
      onDone();
    },
  });
  const reject = useMutation({ mutationFn: (id: number) => api(`/ai-proposals/${id}/reject`, { method: "POST" }), onSuccess: () => setPlan(null) });
  const saveTarget = useMutation({
    mutationFn: () => api(`/kpis/${kpi.id}/target`, { method: "PUT", json: { target_value: target === "" ? null : Number(target), target_direction: direction } }),
    onSuccess: onDone,
  });
  return (
    <div className="space-y-3 rounded-xl border border-line p-3">
      <div className="flex items-baseline justify-between">
        <h3 className="font-bold">{kpi.name}</h3>
        <span className="text-xs text-muted">{AVAIL[kpi.data_availability]}</span>
      </div>
      <p className="text-xs text-muted">{kpi.measurement}</p>
      {kpi.dataset ? (
        <p className="text-sm">
          ✓ データ設定済み: {kpi.dataset.title}（{kpi.points.length} 期間） {kpi.dataset.is_sample && <SampleBadge />}
        </p>
      ) : kpi.survey && kpi.points.length > 0 ? (
        <p className="text-sm">✓ {kpi.survey.kind === "observation" ? "現場観測" : "アンケート"}の集計: {kpi.points.length} 期間（回答 {kpi.survey.total_responses} 件）</p>
      ) : (
        <p className="text-sm text-muted">{kpi.survey?.status === "open" ? "収集中" : "データ未取得"}</p>
      )}
      {!kpi.dataset && <SurveyComposer kpi={kpi} onDone={onDone} />}
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-sm">
          目標値
          <input className="input mt-1 w-28" inputMode="decimal" value={target} onChange={(e) => setTarget(e.target.value)} />
        </label>
        <span className="pb-3 text-sm">{kpi.unit}</span>
        <label className="text-sm">
          向き
          <select className="input mt-1" value={direction} onChange={(e) => setDirection(e.target.value as "increase" | "decrease")}>
            <option value="increase">増やしたい（以上で到達）</option>
            <option value="decrease">減らしたい（以下で到達）</option>
          </select>
        </label>
        <Button variant="secondary" onClick={() => saveTarget.mutate()} disabled={saveTarget.isPending}>目標を保存</Button>
        <Button onClick={() => find.mutate()} disabled={find.isPending}>{find.isPending ? "探しています…" : kpi.dataset ? "データを探し直す" : "データを探す"}</Button>
      </div>
      <ErrorNote error={find.error || saveTarget.error} />
      {search && !plan && (
        <div className="space-y-2">
          <AiBadge status={search.status} />
          {search.payload.candidates.length === 0 && (
            <p className="text-sm text-muted">
              登録済みのデータ {search.payload.searched_count} 件の中には見つかりませんでした。データは「未取得」のまま公開でき、アンケートでの収集も検討できます。
            </p>
          )}
          {search.payload.candidates.map((c) => (
            <div key={c.dataset.id} className="rounded-lg bg-brand-soft p-3 text-sm">
              <p className="font-semibold">
                {c.dataset.title} {c.dataset.is_sample && <SampleBadge />}
              </p>
              <p className="text-xs text-muted">
                {c.dataset.publisher}・{c.dataset.license}・{c.dataset.file_format.toUpperCase()}・更新 {c.dataset.updated_on}・{c.dataset.granularity}
              </p>
              <p className="mt-1 text-xs">理由: {c.reason}</p>
              {!!c.dataset.variant_notes?.length && (
                <ul className="mt-1 space-y-0.5 text-xs" aria-label="同じデータの別の版との違い">
                  {c.dataset.variant_notes.map((v, i) => (
                    <li key={i} className={v.kind === "other_version" ? "text-muted" : "text-warn"}>
                      {v.kind === "other_version" ? "ℹ " : "⚠ "}
                      {v.text}
                    </li>
                  ))}
                </ul>
              )}
              <Button className="mt-2" variant="secondary" onClick={() => shape.mutate(c.dataset.id)} disabled={shape.isPending}>
                {shape.isPending ? "整形案を作っています…" : "このデータを使う"}
              </Button>
            </div>
          ))}
          <ErrorNote error={shape.error} />
        </div>
      )}
      {plan && (
        <div className="space-y-2 rounded-lg bg-ai-soft p-3 text-sm">
          <AiBadge status={plan.status} />
          <p className="font-semibold">整形の手順</p>
          <ol className="list-decimal pl-5">
            {plan.payload.plan.steps.map((s, i) => <li key={i}>{s}</li>)}
          </ol>
          <details>
            <summary className="cursor-pointer text-xs">整形前のデータ（先頭 5 行）</summary>
            <div className="overflow-x-auto">
              <table className="mt-1 text-xs">
                <thead><tr>{plan.payload.columns.map((c) => <th key={c} className="px-1 text-left">{c}</th>)}</tr></thead>
                <tbody>
                  {plan.payload.before_sample.map((r, i) => (
                    <tr key={i}>{plan.payload.columns.map((c) => <td key={c} className="px-1">{r[c]}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
          {plan.payload.warnings.map((w) => (
            <p key={w} role="alert" className="rounded bg-warn-soft p-2 text-warn">⚠ {w}</p>
          ))}
          {plan.payload.preview_error ? (
            <p className="text-warn">この案は実行できません: {plan.payload.preview_error}</p>
          ) : (
            <p>
              整形後: {plan.payload.after_preview.length} 期間（{plan.payload.after_preview[0]?.period}〜{plan.payload.after_preview.at(-1)?.period}、最新値{" "}
              {plan.payload.after_preview.at(-1)?.value}
              {kpi.unit}）
            </p>
          )}
          <div className="flex gap-2">
            <Button onClick={() => adopt.mutate()} disabled={adopt.isPending || !!plan.payload.preview_error}>この整形を採用</Button>
            <Button variant="secondary" onClick={() => reject.mutate(plan.id)}>却下</Button>
          </div>
          <ErrorNote error={adopt.error} />
        </div>
      )}
    </div>
  );
}

export function IssueDetail() {
  const { id } = useParams();
  const qc = useQueryClient();
  const card = useQuery({ queryKey: ["issue", id], queryFn: () => api<IssueCard>(`/issue-cards/${id}`) });
  const me = useQuery({ queryKey: ["me"], queryFn: () => api<{ role: string }>("/me") }).data;
  const preview = useQuery({
    queryKey: ["issue-dashboard", id],
    queryFn: () => api<DashboardView>(`/issue-cards/${id}/dashboard`),
    enabled: !!card.data,
  });
  const [ack, setAck] = useState(false);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["issue", id] });
    qc.invalidateQueries({ queryKey: ["issue-dashboard", id] });
    qc.invalidateQueries({ queryKey: ["me"] });
    qc.invalidateQueries({ queryKey: ["community-candidates", Number(id)] });
  };
  const publish = useMutation({
    mutationFn: () => api(`/issue-cards/${id}/dashboard/publish`, { method: "POST", json: { acknowledge_personal_info: ack } }),
    onSuccess: refresh,
  });
  if (card.isLoading) return <Loading />;
  if (!card.data) return <ErrorNote error={card.error} />;
  const c = card.data;
  const mine = c.author_id === getUserId();
  const published = c.dashboard?.status === "published";
  const url = c.dashboard ? `${location.origin}/d/${c.dashboard.public_slug}` : "";
  return (
    <>
      <Card>
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs text-muted">{c.status_label}・作成: {c.author_name}</p>
          {c.origin_proposal && <AiBadge status={c.origin_proposal.status} />}
        </div>
        <h2 className="mt-1 text-lg font-bold">{c.title}</h2>
        <dl className="mt-2 grid grid-cols-[6rem_1fr] gap-y-1 text-sm">
          <dt className="text-muted">対象者</dt><dd>{c.target || "—"}</dd>
          <dt className="text-muted">場所・時間帯</dt><dd>{c.place_time || "—"}</dd>
          <dt className="text-muted">注力分野</dt><dd>{c.focus_area_label || "—"}</dd>
        </dl>
        {c.origin && (
          <p className="mt-2 text-xs text-muted">
            起点: {{ thread: "スレッド", news: "記事", conversation: "" }[c.origin.kind]}
            {c.origin.path ? <Link className="ml-1 text-brand-strong underline" to={c.origin.path}>{c.origin.label}</Link> : <span className="ml-1">{c.origin.label}</span>}
          </p>
        )}
        {c.evidence.length > 0 && (
          <>
            <h3 className="mt-3 text-sm font-semibold text-muted">根拠</h3>
            <ul className="list-disc pl-5 text-sm">
              {c.evidence.map((e, i) => (
                <li key={i}>
                  <span className="text-xs text-muted">[{{ news: "記事", conversation: "作成者の発言", observation: "観測", thread: "スレッドの発言", data: "データ" }[e.kind] ?? e.kind}]</span> {e.text}
                  {e.quote && <span className="block text-xs text-muted">原文: 「{e.quote}」</span>}
                </li>
              ))}
            </ul>
          </>
        )}
        {c.latest_decision && (
          <p className="mt-3 rounded-lg bg-brand-soft p-3 text-sm">
            🏛 {c.latest_decision.department}: <strong>{{ under_review: "検討中", adopted: "採用", declined: "見送り" }[c.latest_decision.state]}</strong>
            <span className="block text-xs">理由: {c.latest_decision.reason}</span>
          </p>
        )}
        {c.policy_news.length > 0 && (
          <div className="mt-3 rounded-lg border border-brand p-3 text-sm">
            <p className="font-semibold">📣 この課題から始まった施策</p>
            <ul>
              {c.policy_news.map((n) => (
                <li key={n.id}>
                  <Link className="text-brand-strong underline" to={`/news/${n.id}`}>{n.title}</Link>
                  <span className="ml-1 text-xs text-muted">{n.published_at}・{n.department}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {!mine && c.community && (
          <p className="mt-3 text-sm">👥 <Link className="underline" to={`/community/${c.community.id}`}>{c.community.name}</Link></p>
        )}
      </Card>

      {mine && <CommunityLink card={c} onDone={refresh} />}

      {mine && (
        <Card>
          <h2 className="mb-2 font-bold">KPI のデータを用意する</h2>
          <div className="space-y-3">
            {c.kpis.map((k) => <KpiData key={k.id} kpi={k} onDone={refresh} />)}
            {c.kpis.length === 0 && <p className="text-sm text-muted">KPI がありません。</p>}
          </div>
        </Card>
      )}

      {preview.data && (
        <section aria-label="ダッシュボード" className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-bold">{published ? "公開中のダッシュボード" : "ダッシュボードのプレビュー"}</h2>
            {published && <Link className="text-sm text-brand-strong underline" to={`/d/${c.dashboard!.public_slug}`}>公開ページ</Link>}
          </div>
          {preview.data.kpis.map((k) => <KpiCard key={k.id} kpi={k} annotations={preview.data!.annotations} />)}
          {c.dashboard && (
            <DashboardAnnotations view={preview.data} cardId={c.id} canEdit={mine || me?.role === "staff"} onDone={refresh} />
          )}
          {mine && (
            <Card>
              {published ? (
                <p className="break-all text-sm">公開 URL: <a className="underline" href={url}>{url}</a></p>
              ) : (
                <>
                  <p className="mb-2 text-sm text-muted">公開すると固定の URL が発行され、誰でも閲覧・CSV ダウンロードできます。個別の発言や名前は公開されません。</p>
                  {publish.error instanceof ApiError && publish.error.code === "personal_info" && (
                    <label className="mb-2 flex gap-2 text-sm text-warn">
                      <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
                      {publish.error.message}。確認したうえで公開します。
                    </label>
                  )}
                  <Button onClick={() => publish.mutate()} disabled={publish.isPending}>ダッシュボードを公開する</Button>
                  {!(publish.error instanceof ApiError && publish.error.code === "personal_info") && <ErrorNote error={publish.error} />}
                </>
              )}
            </Card>
          )}
        </section>
      )}
    </>
  );
}
