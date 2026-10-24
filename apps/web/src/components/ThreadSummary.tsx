import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError, type Proposal } from "../api";
import { AiBadge, Button, ErrorNote } from "./ui";

type Cited = { post_numbers: number[]; post_ids: number[] };
export type ThreadSummaryPayload = {
  summary: string;
  points: (Cited & { kind: "experience" | "opinion" | "question" | "staff_info"; text: string })[];
  issue_candidates: (Cited & { title: string; target: string; reason: string })[];
  open_questions: string[];
  post_count: number;
};
export type ThreadSummaryOut = Proposal<ThreadSummaryPayload> & {
  stale: boolean;
  issue_cards: { candidate_index: number; id: number; title: string }[];
};

const POINT_LABEL = { experience: "経験", opinion: "意見・要望", question: "疑問・依頼", staff_info: "区からの情報" };

/** Community 形成支援 Agent の要約と課題候補 (F-05 / UXR-7). Shown only on request, so it never interrupts the discussion. */
export function ThreadSummary({
  threadId,
  communityId,
  summary,
  canRequest,
}: {
  threadId: number;
  communityId: number;
  summary: ThreadSummaryOut | null;
  canRequest: boolean;
}) {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const refresh = () => qc.invalidateQueries({ queryKey: ["thread", threadId] });
  const make = useMutation({
    mutationFn: () => api<ThreadSummaryOut>(`/threads/${threadId}/summary`, { method: "POST" }),
    onSuccess: () => {
      setOpen(true);
      refresh();
    },
  });
  const reject = useMutation({
    mutationFn: () => api(`/ai-proposals/${summary!.id}/reject`, { method: "POST" }),
    onSuccess: refresh,
  });
  const aiDown = make.error instanceof ApiError && make.error.code === "ai_unavailable";
  const cite = (c: Cited) => (
    <span className="ml-1 whitespace-nowrap text-xs">
      {c.post_ids.map((pid, i) => (
        <a key={pid} href={`#post-${pid}`} className="mr-1 text-brand-strong underline">
          発言{c.post_numbers[i]}
        </a>
      ))}
    </span>
  );

  if (!summary) {
    if (!canRequest) return null;
    return (
      <div className="rounded-xl border border-dashed border-line p-3">
        <p className="text-xs text-muted">議論が進んだら、AI がここまでの要点と課題の候補を根拠の発言付きでまとめます。</p>
        <Button variant="secondary" className="mt-2" onClick={() => make.mutate()} disabled={make.isPending}>
          {make.isPending ? "AI がまとめています…" : "AI に要約と課題候補を頼む"}
        </Button>
        {aiDown ? (
          <p role="alert" className="mt-2 rounded-lg bg-warn-soft p-3 text-sm text-warn">
            {make.error!.message}。下の「このスレッドから課題カードを作る」から手入力で作れます。
          </p>
        ) : (
          <ErrorNote error={make.error} />
        )}
      </div>
    );
  }

  const p = summary.payload;
  const made = summary.issue_cards.length;
  return (
    <section className="rounded-xl border border-ai bg-ai-soft/40 p-3" aria-label="AI の要約と課題候補">
      <button className="flex w-full items-center justify-between gap-2 text-left" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span>
          <AiBadge status={summary.status} />
          <span className="ml-2 text-sm font-semibold">要約と課題候補 {p.issue_candidates.length} 件{made > 0 && `（カード化 ${made}）`}</span>
        </span>
        <span className="text-xs text-muted">{open ? "閉じる" : "開く"}</span>
      </button>
      {summary.stale && (
        <p className="mt-2 text-xs text-warn">この要約の後に発言が増えています（要約は発言{p.post_count}までが対象）。</p>
      )}
      {open && (
        <div className="mt-2 space-y-3 text-sm">
          <p>{p.summary}</p>
          {p.points.length > 0 && (
            <ul className="space-y-1">
              {p.points.map((pt, i) => (
                <li key={i}>
                  <span className="mr-1 rounded bg-white px-1 text-xs text-muted">{POINT_LABEL[pt.kind]}</span>
                  {pt.text}
                  {cite(pt)}
                </li>
              ))}
            </ul>
          )}
          {p.open_questions.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-muted">まだ分かっていないこと</p>
              <ul className="list-disc pl-5">
                {p.open_questions.map((q, i) => <li key={i}>{q}</li>)}
              </ul>
            </div>
          )}
          <div>
            <p className="text-xs font-semibold text-muted">課題の候補（AI の提案。カードにするかは参加者が決めます）</p>
            {p.issue_candidates.length === 0 && <p className="text-xs text-muted">発言から言える課題の候補はまだありません。</p>}
            {p.issue_candidates.map((c, i) => (
              <div key={i} className="mt-2 rounded-lg border border-line bg-white p-2">
                <p className="font-semibold">{c.title}</p>
                {c.target && <p className="text-xs text-muted">対象: {c.target}</p>}
                <p className="text-xs">
                  {c.reason}
                  {cite(c)}
                </p>
                {summary.issue_cards.filter((m) => m.candidate_index === i).map((m) => (
                  <Link key={m.id} to={`/issues/${m.id}`} className="mt-1 block text-xs font-semibold text-brand-strong underline">
                    → 課題カード「{m.title}」になりました
                  </Link>
                ))}
                {summary.status !== "rejected" && (
                  <Button className="mt-2" onClick={() => nav(`/issues/new?origin=thread:${threadId}&community=${communityId}&candidate=${summary.id}:${i}`)}>
                    この候補で課題カードを作る
                  </Button>
                )}
              </div>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            {canRequest && (
              <Button variant="secondary" onClick={() => make.mutate()} disabled={make.isPending}>
                {make.isPending ? "AI がまとめています…" : "今の発言でまとめ直す"}
              </Button>
            )}
            {summary.status === "proposed" && canRequest && (
              <Button variant="ghost" onClick={() => reject.mutate()} disabled={reject.isPending}>的外れなので却下</Button>
            )}
          </div>
          <ErrorNote error={make.error ?? reject.error} />
          <p className="text-xs text-muted">AI には発言者の名前と連絡先を渡していません（立場だけを渡しています）。</p>
        </div>
      )}
    </section>
  );
}
