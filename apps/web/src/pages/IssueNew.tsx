import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError, type IssueCard, type Proposal } from "../api";
import { AiBadge, Button, Card, Chip, ErrorNote, Loading } from "../components/ui";

type KpiCand = { name: string; unit: string; measurement: string; data_availability: "open_data" | "survey_needed" | "unknown" };
type Draft = {
  title: string;
  target: string;
  place_time: string;
  evidence: { kind: "news" | "conversation" | "observation" | "thread"; text: string; quote: string }[];
  focus_area: string;
  focus_reason: string;
  kpi_candidates: KpiCand[];
  origin_fit?: "resident_issue" | "announcement" | "personal_incident";
  fit_note?: string;
};

const FIT: Record<string, string> = {
  announcement: "この記事は区のお知らせで、住民の困りごとは書かれていません。課題にする前に、コミュニティで当事者の声を集めることをおすすめします。",
  personal_incident: "特定の個人に関わる事案の記事です。個人や事案そのものは課題や KPI にせず、扱うなら仕組みの困りごとに絞ってください。KPI 候補は出していません。",
};

// Where each piece of evidence came from, so a fact with a source, someone's words and an
// added observation are told apart (UXP-4). The quote stays verbatim; only the summary is editable.
const EVIDENCE_KIND = {
  news: "記事（出典のある事実）",
  conversation: "あなたの発言（AI との対話）",
  thread: "スレッドの発言",
  observation: "観測・自分で追加",
} as const;

const AVAIL = { open_data: "公開データあり", survey_needed: "アンケートが必要", unknown: "入手方法は不明" };
const EMPTY: Draft = { title: "", target: "", place_time: "", evidence: [], focus_area: "", focus_reason: "", kpi_candidates: [] };

export function IssueNew() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const origin = params.get("origin") ?? "";
  const [kind, ref] = origin.split(":");
  // "<summary proposal id>:<candidate index>" when started from a thread's AI issue candidate (F-05).
  const [summaryId, candidateIndex] = (params.get("candidate") ?? "").split(":").map((x) => (x === "" ? null : Number(x)));
  const areas = useQuery({
    queryKey: ["focus-areas"],
    queryFn: () => api<{ items: { key: string; label: string }[]; max_kpis: number }>("/focus-areas"),
  });
  const [proposal, setProposal] = useState<Proposal<Draft> | null>(null);
  const [form, setForm] = useState<Draft>(EMPTY);
  const [picked, setPicked] = useState<number[]>([]);
  const [manual, setManual] = useState<string | null>(null);
  const [visibility, setVisibility] = useState<"public" | "community" | "private">("public");
  const [ackPii, setAckPii] = useState(false);
  const [communityId, setCommunityId] = useState(kind === "thread" ? params.get("community") ?? "" : "");
  const communities = useQuery({
    queryKey: ["communities", ""],
    queryFn: () => api<{ items: { id: number; name: string; joined: boolean }[] }>("/communities?q="),
  });
  const requested = useRef(false);

  const draft = useMutation({
    mutationFn: () => api<Proposal<Draft>>("/issue-drafts", { method: "POST", json: { origin_kind: kind, origin_ref: Number(ref), summary_proposal_id: summaryId ?? null, candidate_index: candidateIndex ?? null } }),
    onSuccess: (p) => {
      setProposal(p);
      setForm(p.payload);
      setPicked([]);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === "ai_unavailable") setManual(e.message);
    },
  });
  useEffect(() => {
    if (!requested.current && (kind === "news" || kind === "conversation" || kind === "thread")) {
      requested.current = true;
      draft.mutate();
    } else if (!kind) setManual("");
  }, [kind]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = useMutation({
    mutationFn: () =>
      api<IssueCard>("/issue-cards", {
        method: "POST",
        json: {
          proposal_id: proposal?.id ?? null,
          title: form.title,
          target: form.target,
          place_time: form.place_time,
          evidence: form.evidence,
          focus_area: form.focus_area,
          focus_reason: form.focus_reason,
          kpis: picked.map((i) => form.kpi_candidates[i]),
          origin_kind: kind && ref ? kind : "manual",
          origin_ref: ref ?? "",
          community_id: Number(communityId) || null,
          visibility,
          acknowledge_personal_info: ackPii,
        },
      }),
    onSuccess: (c) => nav(`/issues/${c.id}`),
  });
  const reject = useMutation({
    mutationFn: () => api(`/ai-proposals/${proposal!.id}/reject`, { method: "POST" }),
    onSuccess: () => {
      setProposal(null);
      setForm(EMPTY);
      setManual("AI の提案を却下しました。手入力で作成できます。");
    },
  });
  const max = areas.data?.max_kpis ?? 3;
  const set = (k: keyof Draft) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm({ ...form, [k]: e.target.value });
  const [newKpi, setNewKpi] = useState("");
  const piiError = save.error instanceof ApiError && save.error.code === "personal_info";

  if (draft.isPending) return <Card><Loading /><p className="text-sm text-muted">AI が文脈から課題カードの下書きを作っています…</p></Card>;

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-bold">課題カード</h2>
        {proposal && <AiBadge status={proposal.status} />}
      </div>
      {manual !== null && (
        <p className="mb-3 rounded-lg bg-warn-soft p-3 text-sm text-warn">
          {manual || "手入力で課題カードを作成します。"}
          {manual && " 内容は手入力で作成できます。"}
        </p>
      )}
      {proposal && (
        <p className="mb-3 text-xs text-muted">
          AI の下書きです。すべて編集できます。保存するまで課題カードにはなりません。根拠: {proposal.evidence.map((e) => e.label).join("、")}
        </p>
      )}
      {proposal?.payload.origin_fit && FIT[proposal.payload.origin_fit] && (
        <div role="note" className="mb-3 rounded-lg bg-warn-soft p-3 text-sm text-warn">
          <p>{FIT[proposal.payload.origin_fit]}</p>
          {proposal.payload.fit_note && <p className="mt-1">AI より: {proposal.payload.fit_note}</p>}
          {proposal.payload.origin_fit === "announcement" && (
            <Link className="mt-1 inline-block underline" to="/communities">コミュニティで声を集める</Link>
          )}
        </div>
      )}
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <Field label="タイトル">
          <input required className="input" value={form.title} onChange={set("title")} />
        </Field>
        <Field label="対象者">
          <input className="input" value={form.target} onChange={set("target")} placeholder="例: 子育て世帯" />
        </Field>
        <Field label="場所・時間帯">
          <input className="input" value={form.place_time} onChange={set("place_time")} placeholder="例: 代々木上原周辺／夕方" />
        </Field>
        <fieldset>
          <legend className="text-sm font-semibold text-muted">根拠（ニュース・観測など）</legend>
          {form.evidence.length === 0 && <p className="text-xs text-muted">まだありません</p>}
          {form.evidence.map((ev, i) => (
            <div key={i} className="mt-2 rounded-lg border border-line p-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold">根拠 {i + 1}: {EVIDENCE_KIND[ev.kind] ?? ev.kind}</span>
                <button type="button" className="text-xs text-muted underline" aria-label={`根拠 ${i + 1} を削除`}
                  onClick={() => setForm({ ...form, evidence: form.evidence.filter((_, j) => j !== i) })}>
                  削除
                </button>
              </div>
              {ev.quote && (
                <blockquote className="mt-1 border-l-2 border-line pl-2 text-sm">
                  <span className="text-xs text-muted">原文（そのまま残します）</span>
                  <br />「{ev.quote}」
                </blockquote>
              )}
              <label className="mt-1 block text-xs text-muted">
                {ev.quote ? "要約（編集できます）" : "内容"}
                <textarea
                  aria-label={`根拠 ${i + 1} の${ev.quote ? "要約" : "内容"}`}
                  className="input mt-1 min-h-16 w-full"
                  value={ev.text}
                  onChange={(e) => {
                    const evidence = [...form.evidence];
                    evidence[i] = { ...ev, text: e.target.value };
                    setForm({ ...form, evidence });
                  }}
                />
              </label>
            </div>
          ))}
          <Button type="button" variant="ghost" onClick={() => setForm({ ...form, evidence: [...form.evidence, { kind: "observation", text: "", quote: "" }] })}>
            ＋ 根拠を追加
          </Button>
        </fieldset>
        <Field label="渋谷区の注力分野">
          <select
            className="input"
            value={form.focus_area}
            onChange={(e) =>
              // A human override drops the AI's reason, which no longer explains the choice.
              setForm({ ...form, focus_area: e.target.value, focus_reason: e.target.value === proposal?.payload.focus_area ? proposal.payload.focus_reason : "" })
            }
          >
            <option value="">選んでください</option>
            {areas.data?.items.map((a) => (
              <option key={a.key} value={a.key}>{a.label}</option>
            ))}
            <option value="NONE">どれにも当てはまらない</option>
          </select>
          {form.focus_reason && <p className="mt-1 text-xs text-muted">AI の判定理由: {form.focus_reason}</p>}
          {proposal && form.focus_area !== proposal.payload.focus_area && <p className="mt-1 text-xs text-muted">あなたが AI の判定から変更しました</p>}
        </Field>
        <fieldset>
          <legend className="text-sm font-semibold text-muted">
            KPI（タップで選択・最大 {max} 件）<span className="ml-2">{picked.length}/{max}</span>
          </legend>
          <div className="mt-1 flex flex-wrap gap-2">
            {form.kpi_candidates.map((k, i) => (
              <Chip
                key={i}
                type="button"
                active={picked.includes(i)}
                disabled={!picked.includes(i) && picked.length >= max}
                onClick={() => setPicked(picked.includes(i) ? picked.filter((p) => p !== i) : [...picked, i])}
              >
                {k.name}
              </Chip>
            ))}
          </div>
          {picked.map((i) => (
            <p key={i} className="mt-1 text-xs text-muted">
              {form.kpi_candidates[i].name}: {form.kpi_candidates[i].measurement || "測り方未定"}（{AVAIL[form.kpi_candidates[i].data_availability]}）
            </p>
          ))}
          <div className="mt-2 flex gap-2">
            <input className="input flex-1" aria-label="KPI を自分で追加" placeholder="KPI を自分で追加" value={newKpi} onChange={(e) => setNewKpi(e.target.value)} />
            <Button
              type="button"
              variant="secondary"
              disabled={!newKpi.trim()}
              onClick={() => {
                setForm({ ...form, kpi_candidates: [...form.kpi_candidates, { name: newKpi.trim(), unit: "", measurement: "", data_availability: "unknown" }] });
                setNewKpi("");
              }}
            >
              追加
            </Button>
          </div>
        </fieldset>
        <Field label="コミュニティ（任意・あとからでも選べます）">
          <select className="input" value={communityId} onChange={(e) => setCommunityId(e.target.value)}>
            <option value="">つながない</option>
            {communities.data?.items.map((c) => (
              <option key={c.id} value={c.id}>{c.name}{c.joined ? "（参加中）" : ""}</option>
            ))}
          </select>
          {communityId && <p className="mt-1 text-xs text-muted">保存するとこのコミュニティに参加し、区の判断や施策ニュースがメンバーにも届きます。</p>}
        </Field>
        <Field label="公開範囲">
          <select className="input" value={visibility} onChange={(e) => setVisibility(e.target.value as typeof visibility)}>
            <option value="public">全体公開</option>
            <option value="community">コミュニティ内</option>
            <option value="private">自分だけ（下書き）</option>
          </select>
        </Field>
        {piiError && (
          <label className="flex items-start gap-2 rounded-lg bg-warn-soft p-3 text-sm text-warn">
            <input type="checkbox" checked={ackPii} onChange={(e) => setAckPii(e.target.checked)} />
            {save.error!.message}。確認したうえで公開します。
          </label>
        )}
        {!piiError && <ErrorNote error={save.error} />}
        <div className="flex gap-2">
          <Button disabled={save.isPending || !form.title}>保存して公開</Button>
          {proposal?.status === "proposed" && (
            <Button type="button" variant="secondary" onClick={() => reject.mutate()}>AI の提案を却下</Button>
          )}
        </div>
      </form>
    </Card>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-sm font-semibold text-muted">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}
