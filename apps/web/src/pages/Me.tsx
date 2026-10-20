import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, roleLabel, type User } from "../api";
import { Card, Loading } from "../components/ui";

type Me = User & {
  unread_notifications: number;
  issue_cards: { id: number; title: string; status: string; status_label: string; policy_news: { id: number; title: string; published_at: string }[] }[];
  communities: { id: number; name: string }[];
};
type Notification = { id: number; text: string; link: string; is_read: number; created_at: number };

const STEPS = ["published", "verifying", "dashboard_published", "under_review", "adopted"];
const STEP_LABELS = ["課題カード", "検証中", "ダッシュボード公開", "区で検討中", "採用"];

function Progress({ status }: { status: string }) {
  const idx = status === "declined" ? 3 : STEPS.indexOf(status);
  return (
    <ol className="mt-2 flex gap-1" aria-label="進み具合">
      {STEP_LABELS.map((l, i) => (
        <li key={l} className={`flex-1 rounded px-1 py-0.5 text-center text-[10px] ${i <= idx ? "bg-brand text-white" : "bg-canvas text-muted"}`}>
          {i === 3 && status === "declined" ? "見送り" : l}
          {i === idx && <span className="sr-only">（現在）</span>}
        </li>
      ))}
    </ol>
  );
}

export function MePage() {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: () => api<Me>("/me") });
  const notes = useQuery({ queryKey: ["notifications"], queryFn: () => api<{ items: Notification[] }>("/me/notifications") });
  const read = useMutation({
    mutationFn: (id: number) => api(`/me/notifications/${id}/read`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries(),
  });
  if (!me.data) return <Loading />;
  return (
    <>
      <Card>
        <h2 className="font-bold">{me.data.display_name}</h2>
        <p className="text-sm text-muted">{roleLabel(me.data)}</p>
      </Card>
      <Card>
        <h2 className="mb-2 font-bold">通知</h2>
        {notes.data?.items.length === 0 && <p className="text-sm text-muted">通知はありません。</p>}
        <ul className="space-y-2" aria-live="polite">
          {notes.data?.items.map((n) => (
            <li key={n.id} className={`rounded-lg p-2 text-sm ${n.is_read ? "" : "bg-brand-soft"}`}>
              {!n.is_read && <span className="mr-1 text-xs font-bold text-brand-strong">未読</span>}
              <Link to={n.link} className="underline" onClick={() => read.mutate(n.id)}>{n.text}</Link>
            </li>
          ))}
        </ul>
      </Card>
      <Card>
        <h2 className="mb-2 font-bold">あなたの課題カード</h2>
        {me.data.issue_cards.length === 0 && <p className="text-sm text-muted">まだありません。</p>}
        {me.data.issue_cards.map((c) => (
          <div key={c.id} className="mb-3">
            <Link to={`/issues/${c.id}`} className="block">
              <p className="text-sm font-semibold underline">{c.title}</p>
              <Progress status={c.status} />
            </Link>
            {c.policy_news.map((n) => (
              <p key={n.id} className="mt-1 text-xs">
                📣 施策ニュース: <Link className="text-brand-strong underline" to={`/news/${n.id}`}>{n.title}</Link>（{n.published_at}）
              </p>
            ))}
          </div>
        ))}
      </Card>
    </>
  );
}
