import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type DashboardView, type IssueCard, type User } from "../api";
import { DashboardAnnotations } from "../components/DashboardAnnotations";
import { KpiCard } from "../components/KpiCard";
import { PolicyNewsComposer } from "../components/PolicyNewsComposer";
import { Button, Card, ErrorNote, Loading } from "../components/ui";

const STATE_LABEL: Record<string, string> = { under_review: "検討中", adopted: "採用", declined: "見送り" };

export function Dash() {
  const me = useQuery({ queryKey: ["me"], queryFn: () => api<User>("/me") });
  const cards = useQuery({ queryKey: ["issues"], queryFn: () => api<{ items: IssueCard[] }>("/issue-cards") });
  const published = cards.data?.items.filter((c) => c.dashboard?.status === "published") ?? [];
  return (
    <>
      {me.data?.role === "staff" && <StaffView department={me.data.department} />}
      <h2 className="font-bold">公開中のダッシュボード</h2>
      {cards.isLoading && <Loading />}
      {published.length === 0 && !cards.isLoading && <Card><p className="text-sm text-muted">まだ公開されたダッシュボードはありません。</p></Card>}
      {published.map((c) => (
        <Link key={c.id} to={`/d/${c.dashboard!.public_slug}`} className="block">
          <Card className="hover:border-brand">
            <p className="text-xs text-muted">{c.status_label}・{c.focus_area_label}</p>
            <h3 className="font-bold">{c.title}</h3>
            <p className="text-xs text-muted">KPI: {c.kpis.map((k) => k.name).join("、")}</p>
          </Card>
        </Link>
      ))}
    </>
  );
}

function StaffView({ department }: { department: string }) {
  const qc = useQueryClient();
  const [area, setArea] = useState("");
  const list = useQuery({
    queryKey: ["staff-dashboards", area],
    queryFn: () =>
      api<{ items: DashboardView[]; focus_areas: { key: string; label: string }[] }>(`/staff/dashboards${area ? `?focus_area=${area}` : ""}`),
  });
  return (
    <Card className="border-brand">
      <h2 className="font-bold">職員ビュー（{department}）</h2>
      <p className="mb-2 text-xs text-muted">区民が公開したダッシュボードを比較し、検討状況を記録します。記録は当事者とコミュニティに通知されます。</p>
      <label className="text-sm">
        注力分野
        <select className="input mt-1" value={area} onChange={(e) => setArea(e.target.value)}>
          <option value="">すべて</option>
          {list.data?.focus_areas.map((a) => <option key={a.key} value={a.key}>{a.label}</option>)}
        </select>
      </label>
      <ErrorNote error={list.error} />
      <div className="mt-3 space-y-3">
        {list.data?.items.length === 0 && <p className="text-sm text-muted">該当するダッシュボードはありません。</p>}
        {list.data?.items.map((d) => (
          <StaffItem key={d.issue_card_id} d={d} onDone={() => qc.invalidateQueries()} />
        ))}
      </div>
    </Card>
  );
}

function StaffItem({ d, onDone }: { d: DashboardView; onDone: () => void }) {
  const [state, setState] = useState("under_review");
  const [reason, setReason] = useState("");
  const decide = useMutation({
    mutationFn: () => api(`/dashboards/${d.dashboard!.id}/decisions`, { method: "POST", json: { state, reason } }),
    onSuccess: () => {
      setReason("");
      onDone();
    },
  });
  return (
    <div className="rounded-xl border border-line p-3 text-sm">
      <p className="text-xs text-muted">{d.focus_area_label}・{d.community_id ? `コミュニティ参加者 ${d.community_members ?? 0} 人` : "コミュニティ未接続"}</p>
      <Link className="font-bold underline" to={`/d/${d.dashboard!.public_slug}`}>{d.title}</Link>
      <ul className="mt-1 text-xs">
        {d.kpis.map((k) => (
          <li key={k.id}>
            {k.name}: {k.data_status === "available" ? `${k.current_value}${k.unit}` : "未取得"}
            {k.target_value != null && ` / 目標 ${k.target_value}${k.unit}`}
          </li>
        ))}
      </ul>
      {d.latest_decision && (
        <p className="mt-1 text-xs">現在: <strong>{STATE_LABEL[d.latest_decision.state]}</strong>（{d.latest_decision.reason}）</p>
      )}
      {d.latest_decision?.state === "adopted" && <PolicyNewsComposer d={d} onDone={onDone} />}
      <form
        className="mt-2 space-y-2"
        onSubmit={(e) => {
          e.preventDefault();
          decide.mutate();
        }}
      >
        <fieldset className="flex gap-3">
          <legend className="sr-only">判断</legend>
          {Object.entries(STATE_LABEL).map(([k, v]) => (
            <label key={k} className="flex items-center gap-1">
              <input type="radio" name={`state-${d.issue_card_id}`} checked={state === k} onChange={() => setState(k)} /> {v}
            </label>
          ))}
        </fieldset>
        <textarea required className="input" placeholder="理由（当事者に通知されます）" value={reason} onChange={(e) => setReason(e.target.value)} />
        <Button disabled={!reason.trim() || decide.isPending}>判断を記録する</Button>
        <ErrorNote error={decide.error} />
      </form>
    </div>
  );
}

export function PublicDashboard() {
  const { slug } = useParams();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["public", slug], queryFn: () => api<DashboardView>(`/public/dashboards/${slug}`) });
  const me = useQuery({ queryKey: ["me"], queryFn: () => api<User>("/me") });
  const card = useQuery({
    queryKey: ["issue", String(q.data?.issue_card_id)],
    queryFn: () => api<IssueCard>(`/issue-cards/${q.data!.issue_card_id}`),
    enabled: !!q.data,
  });
  if (q.isLoading) return <Loading />;
  if (!q.data) return <ErrorNote error={q.error} />;
  const d = q.data;
  const canEdit = me.data?.role === "staff" || (!!me.data && card.data?.author_id === me.data.id);
  return (
    <>
      <Card>
        <p className="text-xs text-muted">{d.status_label}・{d.focus_area_label}</p>
        <h2 className="text-lg font-bold">{d.title}</h2>
        <p className="text-sm">対象: {d.target || "—"}　場所・時間帯: {d.place_time || "—"}</p>
        {d.evidence_sources.length > 0 && (
          <p className="mt-1 text-xs text-muted">根拠: {d.evidence_sources.map((e) => e.text).join(" / ")}</p>
        )}
        {d.latest_decision && (
          <p className="mt-2 rounded-lg bg-brand-soft p-2 text-sm">
            🏛 {d.latest_decision.department}: <strong>{STATE_LABEL[d.latest_decision.state]}</strong>（{d.latest_decision.reason}）
          </p>
        )}
        {d.policy_news.map((n) => (
          <p key={n.id} className="mt-2 text-sm">
            📣 施策ニュース: <Link className="text-brand-strong underline" to={`/news/${n.id}`}>{n.title}</Link>
            <span className="ml-1 text-xs text-muted">{n.published_at}</span>
          </p>
        ))}
        <a className="mt-2 inline-block text-sm text-brand-strong underline" href={`/api/public/dashboards/${slug}/export.csv`}>
          KPI データを CSV でダウンロード（出典付き）
        </a>
      </Card>
      {d.kpis.map((k) => <KpiCard key={k.id} kpi={k} annotations={d.annotations} />)}
      <DashboardAnnotations view={d} cardId={d.issue_card_id} canEdit={canEdit} onDone={() => qc.invalidateQueries()} />
      <Link to={`/issues/${d.issue_card_id}`} className="block text-center text-sm text-brand-strong underline">課題カードを見る</Link>
    </>
  );
}
