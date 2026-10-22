import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, type Kpi, type Proposal, type Survey, type SurveyDraft } from "../api";
import { AiBadge, Button, ErrorNote } from "./ui";

const EMPTY: SurveyDraft = {
  kind: "survey", title: "", question: "", answer_type: "rating5", unit: "点", min_value: 1, max_value: 5, audience: "", reason: "",
};
const STATUS = { draft: "下書き（まだ回答を受け付けていません）", open: "回答を受付中", closed: "締め切り済み" } as const;

/** Progress toward the next KPI value: a month counts once enough people answered. */
export function SurveyProgress({ survey }: { survey: Survey }) {
  const left = Math.max(0, survey.min_responses - survey.current_period_responses);
  return (
    <p className="text-xs" role="status">
      {survey.current_period} の回答 {survey.current_period_responses} 件
      {survey.status === "open" && (left > 0
        ? `（あと ${left} 件集まると KPI に反映。それまでは「収集中」と表示し、0 とは見せません）`
        : "（KPI に反映済み）")}
    </p>
  );
}

/** アンケート・現場観測 (F-11): the card author drafts (AI or by hand), saves and opens collection. */
export function SurveyComposer({ kpi, onDone }: { kpi: Kpi; onDone: () => void }) {
  const [form, setForm] = useState<SurveyDraft | null>(null);
  const [proposal, setProposal] = useState<Proposal<SurveyDraft> | null>(null);
  const [manualNote, setManualNote] = useState<string | null>(null);
  const draft = useMutation({
    mutationFn: () => api<Proposal<SurveyDraft>>(`/kpis/${kpi.id}/survey-drafts`, { method: "POST" }),
    onSuccess: (p) => { setProposal(p); setForm(p.payload); },
    onError: (e) => {
      if (e instanceof ApiError && e.code === "ai_unavailable") {
        setManualNote(`${e.message}。手入力で作れます。`);
        setForm({ ...EMPTY, unit: kpi.unit || "点" });
      }
    },
  });
  const save = useMutation({
    mutationFn: () => api<Survey>(`/kpis/${kpi.id}/surveys`, { method: "POST", json: { ...form, proposal_id: proposal?.id ?? null } }),
    onSuccess: () => { setForm(null); setProposal(null); onDone(); },
  });
  const reject = useMutation({
    mutationFn: () => api(`/ai-proposals/${proposal!.id}/reject`, { method: "POST" }),
    onSuccess: () => { setProposal(null); setForm({ ...EMPTY, unit: kpi.unit || "点" }); setManualNote("AI の下書きを却下しました。手入力で作れます。"); },
  });
  const status = useMutation({
    mutationFn: (to: "open" | "close") => api<Survey>(`/surveys/${kpi.survey!.id}/${to}`, { method: "POST" }),
    onSuccess: onDone,
  });
  const s = kpi.survey;

  if (s && s.status !== "closed") {
    return (
      <div className="space-y-2 rounded-lg border border-line p-3 text-sm">
        <p className="font-semibold">{s.kind === "observation" ? "📋 現場観測" : "📝 アンケート"}: {s.title}</p>
        <p className="text-xs text-muted">{STATUS[s.status]}・設問: {s.question}</p>
        <SurveyProgress survey={s} />
        <div className="flex flex-wrap gap-2">
          {s.status === "draft" && <Button onClick={() => status.mutate("open")} disabled={status.isPending}>回答の受付を始める</Button>}
          {s.status === "open" && (
            <>
              <Link className="rounded-xl border border-line px-3 py-2 text-sm font-semibold" to={`/surveys/${s.id}`}>回答ページを開く</Link>
              <Button variant="ghost" onClick={() => status.mutate("close")} disabled={status.isPending}>締め切る</Button>
            </>
          )}
        </div>
        {s.status === "open" && <p className="text-xs text-muted">コミュニティのメンバーに回答のお願いを通知しました。回答ページの URL を共有することもできます。</p>}
        <ErrorNote error={status.error} />
      </div>
    );
  }

  if (!form) {
    return (
      <div className="space-y-1">
        {s?.status === "closed" && <p className="text-xs text-muted">前回の「{s.title}」は締め切り済み（回答 {s.total_responses} 件）。</p>}
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => draft.mutate()} disabled={draft.isPending}>
            {draft.isPending ? "AI が設問を考えています…" : "アンケート・現場観測で集める"}
          </Button>
          <Button variant="ghost" onClick={() => setForm({ ...EMPTY, unit: kpi.unit || "点" })}>手入力で作る</Button>
        </div>
        {!(draft.error instanceof ApiError && draft.error.code === "ai_unavailable") && <ErrorNote error={draft.error} />}
      </div>
    );
  }

  const set = <K extends keyof SurveyDraft>(k: K, v: SurveyDraft[K]) => setForm({ ...form, [k]: v });
  return (
    <form className="space-y-2 rounded-lg bg-ai-soft/40 p-3 text-sm" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      {proposal && <AiBadge status={proposal.status} />}
      {manualNote && <p className="rounded bg-warn-soft p-2 text-xs text-warn">{manualNote}</p>}
      {proposal && <p className="text-xs text-muted">AI の下書きです。すべて編集できます。保存するまでアンケートにはなりません。{form.reason && `（${form.reason}）`}</p>}
      <div className="flex gap-2" role="radiogroup" aria-label="種類">
        {(["survey", "observation"] as const).map((k) => (
          <label key={k} className="flex items-center gap-1 text-xs">
            <input type="radio" checked={form.kind === k} onChange={() => set("kind", k)} />
            {k === "survey" ? "アンケート（感想・経験を尋ねる）" : "現場観測（現地で数える・観察する）"}
          </label>
        ))}
      </div>
      <label className="block text-xs font-semibold text-muted">タイトル
        <input className="input mt-1" required value={form.title} onChange={(e) => set("title", e.target.value)} />
      </label>
      <label className="block text-xs font-semibold text-muted">設問
        <textarea className="input mt-1" required value={form.question} onChange={(e) => set("question", e.target.value)} />
      </label>
      <label className="block text-xs font-semibold text-muted">回答してほしい人
        <input className="input mt-1" value={form.audience} onChange={(e) => set("audience", e.target.value)} placeholder="例: 乳幼児連れで外出する保護者" />
      </label>
      <div className="flex flex-wrap items-end gap-2 text-xs">
        <label className="font-semibold text-muted">回答の形式
          <select className="input mt-1" value={form.answer_type} onChange={(e) => {
            const t = e.target.value as SurveyDraft["answer_type"];
            setForm({ ...form, answer_type: t, ...(t === "rating5" ? { min_value: 1, max_value: 5, unit: "点" } : { min_value: 0, max_value: null }) });
          }}>
            <option value="rating5">5 段階評価</option>
            <option value="number">数値</option>
          </select>
        </label>
        {form.answer_type === "number" && (
          <>
            <label className="font-semibold text-muted">単位<input className="input mt-1 w-20" value={form.unit} onChange={(e) => set("unit", e.target.value)} /></label>
            <label className="font-semibold text-muted">最小<input className="input mt-1 w-20" inputMode="decimal" value={form.min_value ?? ""} onChange={(e) => set("min_value", e.target.value === "" ? null : Number(e.target.value))} /></label>
            <label className="font-semibold text-muted">最大<input className="input mt-1 w-20" inputMode="decimal" value={form.max_value ?? ""} onChange={(e) => set("max_value", e.target.value === "" ? null : Number(e.target.value))} /></label>
          </>
        )}
      </div>
      <p className="text-xs text-muted">自由記述は受け付けません。回答は月ごとに集計し、5 件以上集まった月だけ KPI に反映します。個別の回答は誰にも表示されません。</p>
      <ErrorNote error={save.error} />
      <div className="flex gap-2">
        <Button disabled={save.isPending || !form.title || !form.question}>保存する（下書き）</Button>
        {proposal?.status === "proposed" && <Button type="button" variant="secondary" onClick={() => reject.mutate()}>AI の下書きを却下</Button>}
        <Button type="button" variant="ghost" onClick={() => { setForm(null); setProposal(null); }}>やめる</Button>
      </div>
    </form>
  );
}
