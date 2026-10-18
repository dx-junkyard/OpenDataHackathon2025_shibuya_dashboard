import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, roleLabel } from "../api";
import { Button, Card, ErrorNote, Loading } from "../components/ui";

type Community = {
  id: number;
  name: string;
  description: string;
  category: string;
  area: string;
  hot_topic: string;
  focus_area_label: string;
  member_count: number;
  joined: boolean;
};
type CommunityDetail = Community & {
  threads: { id: number; title: string; post_count: number }[];
  issue_cards: { id: number; title: string; status: string }[];
};
type Thread = {
  id: number;
  community_id: number;
  title: string;
  posts: { id: number; text: string; display_name: string; role: string; attribute: string; department: string }[];
};

/** コミュ参加: search, list and join (docs/ux.md §2). */
export function CommunitySearch() {
  const [params] = useSearchParams();
  const focus = Number(params.get("focus")) || null;
  const [q, setQ] = useState("");
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["communities", q], queryFn: () => api<{ items: Community[] }>(`/communities?q=${encodeURIComponent(q)}`) });
  const join = useMutation({ mutationFn: (id: number) => api(`/communities/${id}/join`, { method: "POST" }), onSuccess: () => qc.invalidateQueries() });
  return (
    <>
      <label className="block">
        <span className="sr-only">コミュニティを探す</span>
        <input className="input" placeholder="関心・地域で探す（例: 子育て、駅周辺）" value={q} onChange={(e) => setQ(e.target.value)} />
      </label>
      {list.isLoading && <Loading />}
      {list.data?.items.length === 0 && (
        <Card><p className="text-sm text-muted">合うコミュニティが見つかりませんでした。新しく作ることもできます（次の段階で対応予定）。</p></Card>
      )}
      {list.data?.items.map((c) => (
        <Card key={c.id} className={focus === c.id ? "border-brand ring-2 ring-brand" : ""}>
          <p className="text-xs text-muted">{c.category}・{c.area}・メンバー {c.member_count}</p>
          <h2 className="font-bold">{c.name}</h2>
          <p className="text-sm">{c.description}</p>
          {c.hot_topic && <p className="mt-1 text-xs">Hot: {c.hot_topic}</p>}
          <div className="mt-2">
            {c.joined ? (
              <Link className="text-sm font-semibold text-brand-strong underline" to={`/community/${c.id}`}>参加中 — 開く</Link>
            ) : (
              <Button onClick={() => join.mutate(c.id)} disabled={join.isPending}>参加する</Button>
            )}
          </div>
        </Card>
      ))}
      <ErrorNote error={join.error} />
    </>
  );
}

/** コミュ: joined communities, threads and posts. */
export function CommunityHome() {
  const { id } = useParams();
  const me = useQuery({ queryKey: ["me"], queryFn: () => api<{ communities: { id: number; name: string }[] }>("/me") });
  const cid = id ? Number(id) : me.data?.communities[0]?.id;
  if (me.isLoading) return <Loading />;
  if (!cid) {
    return (
      <Card>
        <p className="text-sm">まだコミュニティに参加していません。</p>
        <Link className="text-sm font-semibold text-brand-strong underline" to="/communities">コミュニティを探す</Link>
      </Card>
    );
  }
  return (
    <>
      {(me.data?.communities.length ?? 0) > 1 && (
        <nav className="flex gap-2 overflow-x-auto text-sm" aria-label="参加中のコミュニティ">
          {me.data!.communities.map((c) => (
            <Link key={c.id} to={`/community/${c.id}`} className={`rounded-full border px-3 py-1 ${c.id === cid ? "border-brand bg-brand text-white" : "border-line bg-white"}`}>
              {c.name}
            </Link>
          ))}
        </nav>
      )}
      <CommunityView cid={cid} />
    </>
  );
}

function CommunityView({ cid }: { cid: number }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState<number | null>(null);
  const [tab, setTab] = useState<"threads" | "cards">("threads");
  const [newTitle, setNewTitle] = useState("");
  const [newText, setNewText] = useState("");
  const c = useQuery({ queryKey: ["community", cid], queryFn: () => api<CommunityDetail>(`/communities/${cid}`) });
  const create = useMutation({
    mutationFn: () => api<Thread>(`/communities/${cid}/threads`, { method: "POST", json: { title: newTitle, text: newText } }),
    onSuccess: (t) => {
      setNewTitle("");
      setNewText("");
      setOpen(t.id);
      qc.invalidateQueries({ queryKey: ["community", cid] });
    },
  });
  if (!c.data) return <ErrorNote error={c.error} />;
  return (
    <>
      <Card>
        <h2 className="text-lg font-bold">{c.data.name}</h2>
        <p className="text-sm text-muted">メンバー {c.data.member_count}｜Hot: {c.data.hot_topic}</p>
      </Card>
      <div className="flex gap-2" role="tablist">
        <Button role="tab" aria-selected={tab === "threads"} variant={tab === "threads" ? "primary" : "secondary"} onClick={() => setTab("threads")}>スレッド</Button>
        <Button role="tab" aria-selected={tab === "cards"} variant={tab === "cards" ? "primary" : "secondary"} onClick={() => setTab("cards")}>課題カード</Button>
      </div>
      {tab === "threads" && (
        <>
          {c.data.threads.map((t) => (
            <Card key={t.id}>
              <button className="flex w-full items-center justify-between text-left" aria-expanded={open === t.id} onClick={() => setOpen(open === t.id ? null : t.id)}>
                <span className="font-semibold">{t.title}</span>
                <span className="text-xs text-muted">返信 {t.post_count}</span>
              </button>
              {open === t.id && <ThreadView id={t.id} communityId={cid} />}
            </Card>
          ))}
          {c.data.joined && (
            <Card>
              <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
                <h3 className="font-semibold">スレッドを作る</h3>
                <input className="input" aria-label="スレッドのタイトル" placeholder="タイトル" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} />
                <textarea className="input" aria-label="最初の投稿" placeholder="最初の投稿" value={newText} onChange={(e) => setNewText(e.target.value)} />
                <Button disabled={!newTitle.trim() || !newText.trim() || create.isPending}>作成</Button>
                <ErrorNote error={create.error} />
              </form>
            </Card>
          )}
        </>
      )}
      {tab === "cards" &&
        (c.data.issue_cards.length === 0 ? (
          <Card><p className="text-sm text-muted">このコミュニティの課題カードはまだありません。</p></Card>
        ) : (
          c.data.issue_cards.map((ic) => (
            <Link key={ic.id} to={`/issues/${ic.id}`} className="block"><Card className="hover:border-brand">{ic.title}</Card></Link>
          ))
        ))}
    </>
  );
}

function ThreadView({ id, communityId }: { id: number; communityId: number }) {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const t = useQuery({ queryKey: ["thread", id], queryFn: () => api<Thread>(`/threads/${id}`) });
  const post = useMutation({
    mutationFn: () => api<Thread>(`/threads/${id}/posts`, { method: "POST", json: { text } }),
    onSuccess: () => {
      setText("");
      qc.invalidateQueries({ queryKey: ["thread", id] });
      qc.invalidateQueries({ queryKey: ["community", communityId] });
    },
  });
  if (!t.data) return <Loading />;
  return (
    <div className="mt-3 space-y-2">
      {t.data.posts.map((p) => (
        <p key={p.id} className={`rounded-xl border p-2 text-sm ${p.role === "staff" ? "border-brand bg-brand-soft" : "border-line"}`}>
          <span className="mr-1 text-xs font-semibold">
            {p.role === "staff" ? "🏛 " : ""}
            {p.display_name}（{roleLabel(p)}）
          </span>
          {p.text}
        </p>
      ))}
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); post.mutate(); }}>
        <input className="input" aria-label="返信" placeholder="メッセージを入力…" value={text} onChange={(e) => setText(e.target.value)} />
        <Button disabled={!text.trim() || post.isPending}>送信</Button>
      </form>
      <ErrorNote error={post.error} />
      <Button variant="secondary" onClick={() => nav(`/issues/new?origin=thread:${id}&community=${communityId}`)}>このスレッドから課題カードを作る</Button>
    </div>
  );
}
