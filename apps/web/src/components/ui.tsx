import type { ReactNode } from "react";
import { ApiError } from "../api";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-2xl border border-line bg-white p-4 shadow-sm ${className}`}>{children}</div>;
}

export function Button({
  children,
  variant = "primary",
  className = "",
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" }) {
  const styles = {
    primary: "bg-brand text-white hover:bg-brand-strong disabled:opacity-50",
    secondary: "border border-line bg-white text-ink hover:bg-brand-soft disabled:opacity-50",
    ghost: "text-brand-strong underline-offset-2 hover:underline",
  }[variant];
  return (
    <button className={`min-h-11 rounded-xl px-4 py-2 text-sm font-semibold ${styles} ${className}`} {...rest}>
      {children}
    </button>
  );
}

export function Chip({ children, active, ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement> & { active?: boolean }) {
  return (
    <button
      aria-pressed={active}
      className={`min-h-9 max-w-full rounded-2xl border px-3 py-1 text-left text-sm ${
        active ? "border-brand bg-brand text-white" : "border-line bg-white text-ink"
      }`}
      {...rest}
    >
      {active ? "✓ " : ""}
      {children}
    </button>
  );
}

/** Shared label for anything produced by AI (docs/features.md F-21). */
export function AiBadge({ status }: { status?: string }) {
  const label =
    status === "adopted" ? "AI の提案 → 採用" : status === "adopted_edited" ? "AI の提案 → 編集して採用" : status === "rejected" ? "AI の提案 → 却下" : "AI の提案";
  return <span className="inline-block rounded-md bg-ai-soft px-2 py-0.5 text-xs font-semibold text-ai">🤖 {label}</span>;
}

export function SampleBadge() {
  return <span className="inline-block rounded-md bg-warn-soft px-2 py-0.5 text-xs font-semibold text-warn">サンプル（架空）</span>;
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const msg = error instanceof ApiError || error instanceof Error ? error.message : String(error);
  return (
    <p role="alert" className="rounded-lg bg-warn-soft p-3 text-sm text-warn">
      {msg}
    </p>
  );
}

export function Loading() {
  return <p className="p-4 text-sm text-muted">読み込み中…</p>;
}

export const ORG_KIND_LABEL: Record<string, string> = {
  experience: "あなたの経験",
  opinion: "あなたの意見",
  question: "あなたの疑問",
  article_fact: "記事の事実",
  ai_inference: "AI の推測",
};
