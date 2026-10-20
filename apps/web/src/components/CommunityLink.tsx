import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, type IssueCard } from "../api";
import { AiBadge, Button, Card, ErrorNote } from "./ui";

type Option = { id: number; name: string; reason: string };
type Candidates = {
  ai_recommendation: { id: number; status: string; model: string; items: Option[] } | null;
  matches: Option[];
  all: { id: number; name: string; member_count: number; joined: boolean }[];
};
export type NewCommunity = { name: string; description: string; category: string; focus_area: string; area: string };

/** Link an issue card to a community: AI-recommended, rule-matched, any existing one, or a new one. */
export function CommunityLink({ card, onDone }: { card: IssueCard; onDone: () => void }) {
  const [editing, setEditing] = useState(!card.community);
  const [creating, setCreating] = useState(false);
  const cands = useQuery({
    queryKey: ["community-candidates", card.id],
    queryFn: () => api<Candidates>(`/issue-cards/${card.id}/community-candidates`),
    enabled: editing,
  });
  const link = useMutation({
    mutationFn: (v: { community_id: number | null; recommendation_proposal_id?: number }) =>
      api(`/issue-cards/${card.id}/community`, { method: "PUT", json: v }),
    onSuccess: () => {
      setEditing(false);
      setCreating(false);
      onDone();
    },
  });
  const [other, setOther] = useState("");
  const ai = cands.data?.ai_recommendation;

  return (
    <Card>
      <h2 className="font-bold">コミュニティ</h2>
      {card.community && !editing && (
        <p className="mt-1 text-sm">
          👥 <Link className="font-semibold underline" to={`/community/${card.community.id}`}>{card.community.name}</Link> とつながっています。
          区の判断や施策ニュースはメンバーにも届きます。
          <Button variant="ghost" onClick={() => setEditing(true)}>変更</Button>
        </p>
      )}
      {editing && (
        <div className="mt-1 space-y-3 text-sm">
          <p className="text-xs text-muted">
            コミュニティとつなぐと、同じ関心の人と課題を育てられ、区の判断や施策ニュースがメンバーにも届きます。選ぶとあなたもそのコミュニティに参加します。
          </p>
          {ai && ai.items.length > 0 && (
            <div className="space-y-1">
              <AiBadge status={ai.status} />
              {ai.items.map((c) => (
                <div key={c.id} className="flex items-center justify-between gap-2 rounded-lg bg-ai-soft p-2">
                  <span>
                    <strong>{c.name}</strong>
                    <span className="block text-xs text-muted">理由: {c.reason}</span>
                  </span>
                  <Button variant="secondary" className="shrink-0" disabled={link.isPending} onClick={() => link.mutate({ community_id: c.id, recommendation_proposal_id: ai.id })}>
                    つなぐ
                  </Button>
                </div>
              ))}
            </div>
          )}
          {cands.data?.matches.map((c) => (
            <div key={c.id} className="flex items-center justify-between gap-2 rounded-lg bg-brand-soft p-2">
              <span>
                <strong>{c.name}</strong>
                <span className="block text-xs text-muted">{c.reason}</span>
              </span>
              <Button variant="secondary" className="shrink-0" disabled={link.isPending} onClick={() => link.mutate({ community_id: c.id })}>つなぐ</Button>
            </div>
          ))}
          <form
            className="flex items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (other) link.mutate({ community_id: Number(other) });
            }}
          >
            <label className="flex-1">
              ほかのコミュニティから選ぶ
              <select className="input mt-1" value={other} onChange={(e) => setOther(e.target.value)}>
                <option value="">選んでください</option>
                {cands.data?.all.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}（{c.member_count} 人）</option>
                ))}
              </select>
            </label>
            <Button variant="secondary" className="shrink-0" disabled={!other || link.isPending}>つなぐ</Button>
          </form>
          {creating ? (
            <NewCommunityForm
              defaults={{ focus_area: card.focus_area === "NONE" ? "" : card.focus_area }}
              onCreated={(id) => link.mutate({ community_id: id })}
              onCancel={() => setCreating(false)}
            />
          ) : (
            <Button variant="ghost" onClick={() => setCreating(true)}>＋ 合うものがなければ新しく作る</Button>
          )}
          <div className="flex gap-2">
            {card.community && <Button variant="ghost" onClick={() => link.mutate({ community_id: null })}>つながりを外す</Button>}
            {card.community && <Button variant="ghost" onClick={() => setEditing(false)}>キャンセル</Button>}
          </div>
          <ErrorNote error={cands.error || link.error} />
        </div>
      )}
    </Card>
  );
}

export function NewCommunityForm({
  defaults = {},
  onCreated,
  onCancel,
}: {
  defaults?: Partial<NewCommunity>;
  onCreated: (id: number) => void;
  onCancel?: () => void;
}) {
  const [f, setF] = useState<NewCommunity>({ name: "", description: "", category: "", focus_area: "", area: "", ...defaults });
  const areas = useQuery({ queryKey: ["focus-areas"], queryFn: () => api<{ items: { key: string; label: string }[] }>("/focus-areas") });
  const create = useMutation({
    mutationFn: () => api<{ id: number }>("/communities", { method: "POST", json: f }),
    onSuccess: (c) => onCreated(c.id),
  });
  const set = (k: keyof NewCommunity) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setF({ ...f, [k]: e.target.value });
  return (
    <form
      className="space-y-2 rounded-lg border border-line p-3"
      onSubmit={(e) => {
        e.preventDefault();
        create.mutate();
      }}
    >
      <h3 className="font-semibold">新しいコミュニティ</h3>
      <label className="block text-sm">名前<input required maxLength={60} className="input mt-1" value={f.name} onChange={set("name")} /></label>
      <label className="block text-sm">説明<textarea maxLength={300} className="input mt-1" value={f.description} onChange={set("description")} /></label>
      <div className="flex flex-wrap gap-2">
        <label className="text-sm">カテゴリ<input maxLength={20} className="input mt-1 w-32" placeholder="例: 子育て" value={f.category} onChange={set("category")} /></label>
        <label className="text-sm">地域<input maxLength={40} className="input mt-1 w-32" placeholder="例: 代々木" value={f.area} onChange={set("area")} /></label>
      </div>
      <label className="block text-sm">
        注力分野
        <select className="input mt-1" value={f.focus_area} onChange={set("focus_area")}>
          <option value="">指定しない</option>
          {areas.data?.items.map((a) => <option key={a.key} value={a.key}>{a.label}</option>)}
        </select>
      </label>
      <div className="flex gap-2">
        <Button disabled={!f.name.trim() || create.isPending}>作成して参加する</Button>
        {onCancel && <Button type="button" variant="ghost" onClick={onCancel}>やめる</Button>}
      </div>
      <ErrorNote error={create.error} />
    </form>
  );
}
