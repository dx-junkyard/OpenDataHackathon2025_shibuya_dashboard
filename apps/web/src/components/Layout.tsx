import { useQuery, useQueryClient } from "@tanstack/react-query";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { api, getUserId, roleLabel, setUserId, type User } from "../api";

const TABS = [
  { to: "/news", label: "ニュース", icon: "📰" },
  { to: "/community", label: "コミュ", icon: "👥" },
  { to: "/communities", label: "コミュ参加", icon: "＋" },
  { to: "/issues", label: "課題", icon: "🗂" },
  { to: "/dash", label: "ダッシュ", icon: "📊" },
  { to: "/me", label: "マイ", icon: "👤" },
];

export function Layout() {
  const qc = useQueryClient();
  const { pathname } = useLocation();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<{ items: User[] }>("/users") });
  const me = useQuery({ queryKey: ["me"], queryFn: () => api<User & { unread_notifications: number }>("/me") });
  const current = TABS.find((t) => pathname.startsWith(t.to) && (t.to !== "/community" || !pathname.startsWith("/communities")));
  return (
    <div className="mx-auto flex min-h-dvh max-w-xl flex-col">
      <header className="sticky top-0 z-10 flex items-center justify-between gap-2 border-b border-line bg-white/95 px-4 py-3 backdrop-blur">
        <h1 className="text-sm font-bold leading-tight">
          課題共創ダッシュボード<span className="text-muted"> — {current?.label ?? (pathname.startsWith("/d/") ? "公開ダッシュボード" : "")}</span>
        </h1>
        <label className="text-xs">
          <span className="sr-only">利用者を切り替える</span>
          <select
            className="max-w-40 rounded-full border border-line bg-brand-soft px-2 py-1"
            value={getUserId()}
            onChange={(e) => {
              setUserId(Number(e.target.value));
              qc.invalidateQueries();
            }}
          >
            {users.data?.items.map((u) => (
              <option key={u.id} value={u.id}>
                {u.display_name}・{roleLabel(u)}
              </option>
            ))}
          </select>
        </label>
      </header>
      <main className="flex-1 space-y-4 px-4 pb-28 pt-4">
        <Outlet />
      </main>
      <nav aria-label="メイン" className="fixed inset-x-0 bottom-0 z-10 border-t border-line bg-white">
        <ul className="mx-auto grid max-w-xl grid-cols-6">
          {TABS.map((t) => (
            <li key={t.to}>
              <NavLink
                to={t.to}
                end={t.to === "/community"}
                className={({ isActive }) =>
                  `relative flex min-h-14 flex-col items-center justify-center text-[11px] ${
                    isActive && (t.to !== "/community" || !pathname.startsWith("/communities")) ? "font-bold text-brand-strong" : "text-muted"
                  }`
                }
              >
                <span aria-hidden className="text-lg">{t.icon}</span>
                {t.label}
                {t.to === "/me" && (me.data?.unread_notifications ?? 0) > 0 && (
                  <span className="absolute right-3 top-1 rounded-full bg-red-600 px-1.5 text-[10px] text-white">
                    {me.data?.unread_notifications}
                    <span className="sr-only">件の未読通知</span>
                  </span>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}
