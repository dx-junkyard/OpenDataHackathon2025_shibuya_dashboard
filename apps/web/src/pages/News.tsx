import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type Proposal } from "../api";
import { AiBadge, Button, Card, Chip, ErrorNote, Loading, ORG_KIND_LABEL, SampleBadge } from "../components/ui";

type News = {
  id: number;
  title: string;
  body: string;
  category: string;
  department: string;
  source_name: string;
  source_url: string;
  is_sample: boolean;
  published_at: string;
  kind: "local" | "policy";
  issue_card?: { id: number; title: string; dashboard_slug: string | null } | null;
};

function PolicyBadge() {
  return <span className="inline-block rounded-md bg-brand px-2 py-0.5 text-xs font-semibold text-white">📣 施策ニュース</span>;
}

type Message = {
  id: number;
  speaker: "user" | "ai";
  text: string;
  ai_status: "ok" | "unavailable" | "failed";
  organization: { kind: string; text: string; source_message_index: number }[];
};
type Conversation = { id: number; messages: Message[]; ai_available: boolean };
type Reco = { communities: { id: number; name: string; reason: string }[]; issue_cards: { id: number; title: string; reason: string }[] };

export function NewsList() {
  const [cat, setCat] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ["news", cat],
    queryFn: () => api<{ categories: string[]; items: News[] }>(`/news${cat ? `?category=${encodeURIComponent(cat)}` : ""}`),
  });
  return (
    <>
      <div className="flex gap-2 overflow-x-auto pb-1 [&>button]:shrink-0 [&>button]:whitespace-nowrap" role="group" aria-label="カテゴリで絞り込む">
        <Chip active={cat === null} onClick={() => setCat(null)}>すべて</Chip>
        {q.data?.categories.map((c) => (
          <Chip key={c} active={cat === c} onClick={() => setCat(c)}>{c}</Chip>
        ))}
      </div>
      {q.isLoading && <Loading />}
      <ErrorNote error={q.error} />
      {q.data?.items.map((n) => (
        <Link key={n.id} to={`/news/${n.id}`} className="block">
          <Card className="hover:border-brand">
            <p className="text-xs text-muted">
              {n.kind === "policy" && <PolicyBadge />} {n.category}・{n.department}・{n.published_at} {n.is_sample && <SampleBadge />}
            </p>
            <h2 className="mt-1 font-bold">{n.title}</h2>
            {n.issue_card && <p className="mt-1 text-xs text-muted">区民の課題カード「{n.issue_card.title}」から</p>}
          </Card>
        </Link>
      ))}
    </>
  );
}

export function NewsDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const news = useQuery({ queryKey: ["news-item", id], queryFn: () => api<News>(`/news/${id}`) });
  const [conv, setConv] = useState<Conversation | null>(null);
  const [text, setText] = useState("");
  const start = useMutation({
    mutationFn: () => api<Conversation>("/conversations", { method: "POST", json: { news_id: Number(id) } }),
    onSuccess: setConv,
  });
  const send = useMutation({
    mutationFn: (t: string) => api<Conversation>(`/conversations/${conv!.id}/messages`, { method: "POST", json: { text: t } }),
    onSuccess: (c) => {
      setConv(c);
      setText("");
    },
  });
  const reco = useMutation({
    mutationFn: () => api<Proposal<Reco>>(`/conversations/${conv!.id}/recommendations`, { method: "POST" }),
  });
  if (news.isLoading) return <Loading />;
  if (!news.data) return <ErrorNote error={news.error} />;
  const n = news.data;
  const org = conv?.messages.filter((m) => m.speaker === "ai" && m.ai_status === "ok").at(-1)?.organization ?? [];
  const hasUserTurn = conv?.messages.some((m) => m.speaker === "user");
  return (
    <>
      <Card>
        <p className="text-xs text-muted">
          {n.kind === "policy" && <PolicyBadge />} {n.category}・{n.published_at} {n.is_sample && <SampleBadge />}
        </p>
        <h2 className="mt-1 text-lg font-bold">{n.title}</h2>
        <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">{n.body}</p>
        {n.issue_card && (
          <div className="mt-3 rounded-lg bg-brand-soft p-3 text-sm">
            <p className="text-xs text-muted">この施策は区民の課題カードから始まりました</p>
            <Link className="font-semibold text-brand-strong underline" to={`/issues/${n.issue_card.id}`}>🗂 {n.issue_card.title}</Link>
            {n.issue_card.dashboard_slug && (
              <Link className="mt-1 block text-brand-strong underline" to={`/d/${n.issue_card.dashboard_slug}`}>📊 KPI の変化をダッシュボードで見る</Link>
            )}
          </div>
        )}
        <p className="mt-3 text-xs text-muted">
          出典: {n.source_name}（担当: {n.department}）
          {n.source_url && (
            <a className="ml-1 underline" href={n.source_url} target="_blank" rel="noreferrer">元の記事</a>
          )}
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {!conv && <Button onClick={() => start.mutate()} disabled={start.isPending}>この記事について AI と話す</Button>}
          <Button variant="secondary" onClick={() => nav(`/issues/new?origin=news:${n.id}`)}>課題カードを作る</Button>
        </div>
        <ErrorNote error={start.error} />
      </Card>

      {conv && (
        <Card>
          <h2 className="mb-2 font-bold">AI と話す</h2>
          <p className="mb-3 text-xs text-muted">思ったことを気軽にどうぞ。話すだけで終えても大丈夫です。</p>
          <ol className="space-y-2" aria-live="polite">
            {conv.messages.map((m) => (
              <li key={m.id} className={m.speaker === "user" ? "text-right" : ""}>
                <span
                  className={`inline-block max-w-[85%] rounded-2xl px-3 py-2 text-left text-sm ${
                    m.speaker === "user" ? "bg-brand text-white" : m.ai_status === "ok" ? "bg-ai-soft" : "bg-warn-soft text-warn"
                  }`}
                >
                  {m.speaker === "ai" && m.ai_status !== "ok" && "⚠ "}
                  {m.text}
                </span>
              </li>
            ))}
          </ol>
          <form
            className="mt-3 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (text.trim()) send.mutate(text.trim());
            }}
          >
            <label className="sr-only" htmlFor="chat-input">メッセージ</label>
            <input
              id="chat-input"
              className="min-h-11 flex-1 rounded-xl border border-line px-3 text-sm"
              placeholder="自由に入力してください…"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            <Button disabled={send.isPending || !text.trim()}>{send.isPending ? "送信中…" : "送信"}</Button>
          </form>
          <ErrorNote error={send.error} />
          {!conv.ai_available && (
            <p className="mt-2 text-xs text-warn">AI が使えない状態です。発言は保存されます。課題カードは手入力で作れます。</p>
          )}
        </Card>
      )}

      {org.length > 0 && (
        <Card>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-bold">ここまでの整理</h2>
            <AiBadge />
          </div>
          <ul className="space-y-1 text-sm">
            {org.map((o, i) => (
              <li key={i}>
                <span className={`mr-2 rounded px-1.5 py-0.5 text-xs ${o.kind === "ai_inference" ? "bg-ai-soft text-ai" : "bg-brand-soft text-brand-strong"}`}>
                  {ORG_KIND_LABEL[o.kind] ?? o.kind}
                </span>
                {o.text}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {hasUserTurn && (
        <Card>
          <h2 className="font-bold">次にできること</h2>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button onClick={() => nav(`/issues/new?origin=conversation:${conv!.id}`)}>この話から課題カードを作る</Button>
            <Button variant="secondary" onClick={() => reco.mutate()} disabled={reco.isPending}>
              {reco.isPending ? "探しています…" : "同じ関心のコミュニティを探す"}
            </Button>
          </div>
          <ErrorNote error={reco.error} />
          {reco.data && (
            <div className="mt-3 space-y-2 text-sm">
              <AiBadge />
              {reco.data.payload.communities.length + reco.data.payload.issue_cards.length === 0 && (
                <p className="text-muted">関連するコミュニティ・課題は見つかりませんでした。</p>
              )}
              {reco.data.payload.communities.map((c) => (
                <p key={`c${c.id}`}>
                  <Link className="font-semibold text-brand-strong underline" to={`/communities?focus=${c.id}`}>👥 {c.name}</Link>
                  <span className="block text-xs text-muted">理由: {c.reason}</span>
                </p>
              ))}
              {reco.data.payload.issue_cards.map((c) => (
                <p key={`i${c.id}`}>
                  <Link className="font-semibold text-brand-strong underline" to={`/issues/${c.id}`}>🗂 {c.title}</Link>
                  <span className="block text-xs text-muted">理由: {c.reason}</span>
                </p>
              ))}
            </div>
          )}
        </Card>
      )}
    </>
  );
}
