import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, type DashboardView, type Proposal } from "../api";
import { AiBadge, Button, ErrorNote } from "./ui";

type Draft = { title: string; body: string; category: string; annotation_label: string };
const EMPTY: Draft = { title: "", body: "", category: "", annotation_label: "施策開始" };
const CATEGORIES = ["子育て", "移動", "安全", "観光", "産業", "福祉", "その他"];

/** 施策ニュース化 (docs/features.md F-14): AI draft → staff edits → publish. */
export function PolicyNewsComposer({ d, onDone }: { d: DashboardView; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [proposal, setProposal] = useState<Proposal<Draft> | null>(null);
  const [form, setForm] = useState<Draft>(EMPTY);
  const [period, setPeriod] = useState(new Date().toISOString().slice(0, 7));
  const [manualNote, setManualNote] = useState("");
  const draft = useMutation({
    mutationFn: () => api<Proposal<Draft>>(`/issue-cards/${d.issue_card_id}/policy-news-drafts`, { method: "POST" }),
    onSuccess: (p) => {
      setProposal(p);
      setForm(p.payload);
      setManualNote("");
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === "ai_unavailable") setManualNote(`${e.message}。手入力で書けます。`);
    },
  });
  const publish = useMutation({
    mutationFn: () =>
      api<{ news_id: number }>(`/issue-cards/${d.issue_card_id}/policy-news`, {
        method: "POST",
        json: { ...form, proposal_id: proposal?.id ?? null, start_period: period },
      }),
    onSuccess: () => {
      setOpen(false);
      setProposal(null);
      setForm(EMPTY);
      onDone();
    },
  });
  const reject = useMutation({
    mutationFn: () => api(`/ai-proposals/${proposal!.id}/reject`, { method: "POST" }),
    onSuccess: () => {
      setProposal(null);
      setManualNote("AI の提案を却下しました。手入力で書けます。");
    },
  });
  const set = (k: keyof Draft) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm({ ...form, [k]: e.target.value });

  return (
    <div className="mt-3 rounded-lg border border-brand bg-brand-soft/40 p-3">
      <h3 className="font-semibold">施策ニュース</h3>
      {d.policy_news.length > 0 && (
        <ul className="mb-2 text-xs">
          {d.policy_news.map((n) => (
            <li key={n.id}>
              📣 <Link className="underline" to={`/news/${n.id}`}>{n.title}</Link>（{n.published_at} 配信済み）
            </li>
          ))}
        </ul>
      )}
      {!open ? (
        <Button variant="secondary" onClick={() => setOpen(true)}>
          {d.policy_news.length ? "続報の施策ニュースを書く" : "施策ニュースを書いて配信する"}
        </Button>
      ) : (
        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            publish.mutate();
          }}
        >
          <p className="text-xs text-muted">配信すると、ニュース一覧に載り、ダッシュボードに施策開始の注釈が付き、当事者とコミュニティに通知されます。</p>
          <div className="flex flex-wrap items-center gap-2">
            {proposal ? (
              <AiBadge status={proposal.status} />
            ) : (
              <Button type="button" variant="secondary" onClick={() => draft.mutate()} disabled={draft.isPending}>
                {draft.isPending ? "下書きを作っています…" : "AI に下書きを頼む"}
              </Button>
            )}
          </div>
          {manualNote && <p className="rounded-lg bg-warn-soft p-2 text-xs text-warn">{manualNote}</p>}
          {!(draft.error instanceof ApiError && draft.error.code === "ai_unavailable") && <ErrorNote error={draft.error} />}
          {proposal && <p className="text-xs text-muted">AI の下書きです。事実と違う箇所や効果を言い切る表現がないか確認し、直してから配信してください。</p>}
          <label className="block text-sm">
            タイトル
            <input required maxLength={120} className="input mt-1" value={form.title} onChange={set("title")} />
          </label>
          <label className="block text-sm">
            本文
            <textarea required className="input mt-1 min-h-40" value={form.body} onChange={set("body")} />
          </label>
          <div className="flex flex-wrap gap-2">
            <label className="text-sm">
              カテゴリ
              <select required className="input mt-1 w-32" value={form.category} onChange={set("category")}>
                <option value="">選ぶ</option>
                {[...new Set([form.category, ...CATEGORIES].filter(Boolean))].map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
            <label className="text-sm">
              施策の開始時期
              <input type="month" required className="input mt-1 w-40" value={period} onChange={(e) => setPeriod(e.target.value)} />
            </label>
          </div>
          <label className="block text-sm">
            ダッシュボードの注釈
            <input required maxLength={40} className="input mt-1" value={form.annotation_label} onChange={set("annotation_label")} />
          </label>
          <div className="flex flex-wrap gap-2">
            <Button disabled={publish.isPending || !form.title.trim() || !form.body.trim() || !form.category}>配信する</Button>
            {proposal?.status === "proposed" && (
              <Button type="button" variant="secondary" onClick={() => reject.mutate()}>AI の提案を却下</Button>
            )}
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>閉じる</Button>
          </div>
          <ErrorNote error={publish.error || reject.error} />
        </form>
      )}
    </div>
  );
}
