import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, type Annotation, type Comparison, type DashboardView } from "../api";
import { Button, Card, ErrorNote } from "./ui";

const KINDS: { key: Annotation["kind"]; label: string }[] = [
  { key: "policy_start", label: "施策開始" },
  { key: "event", label: "イベント" },
  { key: "definition_change", label: "データ定義の変更" },
];

const num = (v: number | null, unit: string) => (v == null ? "—" : `${Number.isInteger(v) ? v : v.toFixed(1)}${unit}`);
const perPeriod = (v: number | null, unit: string) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(1)}${unit}`);

function CompareTable({ c }: { c: Comparison }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-muted">
            <th className="py-1 pr-2 font-normal">KPI</th>
            <th className="py-1 pr-2 font-normal">直前の値</th>
            <th className="py-1 pr-2 font-normal">最新の値</th>
            <th className="py-1 font-normal">1 期間あたりの変化（前 → 後）</th>
          </tr>
        </thead>
        <tbody>
          {c.kpis.map((k) => (
            <tr key={k.kpi_id} className="border-t border-line align-top">
              <td className="py-1 pr-2">{k.name}</td>
              {k.state === "no_data" ? (
                <td colSpan={3} className="py-1 text-muted">データ未取得</td>
              ) : (
                <>
                  <td className="py-1 pr-2">{num(k.before_value, k.unit)}</td>
                  <td className="py-1 pr-2">
                    {k.state === "no_after" ? <span className="text-muted">注釈後のデータはまだありません</span> : `${num(k.after_value, k.unit)}（${k.after_periods} 期間）`}
                  </td>
                  <td className="py-1">
                    {perPeriod(k.before_per_period, k.unit)} → {k.state === "no_after" ? "—" : perPeriod(k.after_per_period, k.unit)}
                  </td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** 注釈と施策前後比較 (docs/features.md F-12). The comparison is arithmetic on
 * the published points and is always shown with the "causality unconfirmed" note. */
export function DashboardAnnotations({
  view,
  cardId,
  canEdit,
  onDone,
}: {
  view: DashboardView;
  cardId: number;
  canEdit: boolean;
  onDone: () => void;
}) {
  const [period, setPeriod] = useState(new Date().toISOString().slice(0, 7));
  const [label, setLabel] = useState("");
  const [kind, setKind] = useState<Annotation["kind"]>("event");
  const add = useMutation({
    mutationFn: () => api(`/issue-cards/${cardId}/dashboard/annotations`, { method: "POST", json: { period, label, kind } }),
    onSuccess: () => {
      setLabel("");
      onDone();
    },
  });
  const byId = new Map(view.annotations.map((a) => [a.id, a]));
  if (view.annotations.length === 0 && !canEdit) return null;
  return (
    <Card>
      <h2 className="font-bold">注釈と前後の比較</h2>
      <p role="note" className="mt-2 rounded-lg bg-warn-soft p-2 text-xs text-warn">⚠ {view.causality_note}</p>
      {view.annotations.length === 0 && <p className="mt-2 text-sm text-muted">まだ注釈はありません。施策の開始やイベントを記録すると、その前後を見比べられます。</p>}
      <div className="mt-3 space-y-4">
        {view.comparisons.map((c) => {
          const a = byId.get(c.annotation_id);
          return (
            <section key={c.annotation_id} aria-label={`${c.period} ${c.label}`}>
              <p className="text-sm">
                <span className="mr-1 rounded bg-[#f6ead9] px-1.5 py-0.5 text-xs text-[#8a5a1c]">{a?.kind_label}</span>
                <strong>{c.period}</strong> {c.label}
                {a?.news_id && (
                  <Link className="ml-2 text-xs text-brand-strong underline" to={`/news/${a.news_id}`}>施策ニュース</Link>
                )}
              </p>
              <CompareTable c={c} />
            </section>
          );
        })}
      </div>
      {canEdit && (
        <form
          className="mt-4 space-y-2 border-t border-line pt-3"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate();
          }}
        >
          <h3 className="text-sm font-semibold">注釈を追加する</h3>
          <div className="flex flex-wrap gap-2">
            <label className="text-sm">
              時期
              <input type="month" required className="input mt-1 w-40" value={period} onChange={(e) => setPeriod(e.target.value)} />
            </label>
            <label className="text-sm">
              種類
              <select className="input mt-1 w-44" value={kind} onChange={(e) => setKind(e.target.value as Annotation["kind"])}>
                {KINDS.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
              </select>
            </label>
          </div>
          <label className="block text-sm">
            内容
            <input required maxLength={100} className="input mt-1" placeholder="例: 駅前に案内表示を設置" value={label} onChange={(e) => setLabel(e.target.value)} />
          </label>
          <Button disabled={!label.trim() || !period || add.isPending}>注釈を追加</Button>
          <ErrorNote error={add.error} />
        </form>
      )}
    </Card>
  );
}
