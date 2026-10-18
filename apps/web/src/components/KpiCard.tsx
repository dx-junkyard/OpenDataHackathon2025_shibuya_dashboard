import type { KpiSummary } from "../api";
import { SampleBadge } from "./ui";

const TREND = { up: "↗ 増加傾向", down: "↘ 減少傾向", flat: "→ 横ばい" } as const;

function Chart({ kpi, annotations }: { kpi: KpiSummary; annotations: { period: string; label: string }[] }) {
  const pts = kpi.points;
  const W = 320;
  const H = 96;
  const values = pts.map((p) => p.value).concat(kpi.target_value != null ? [kpi.target_value] : []);
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 1);
  const x = (i: number) => (pts.length <= 1 ? W / 2 : (i / (pts.length - 1)) * (W - 8) + 4);
  const y = (v: number) => H - 6 - ((v - min) / (max - min || 1)) * (H - 12);
  const line = pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-24 w-full" role="img" aria-label={`${kpi.name}の推移（${pts[0]?.period}〜${pts.at(-1)?.period}）`}>
      {kpi.target_value != null && (
        <line x1="0" x2={W} y1={y(kpi.target_value)} y2={y(kpi.target_value)} stroke="#8a95a3" strokeDasharray="4 4" />
      )}
      {annotations.map((a) => {
        const i = pts.findIndex((p) => p.period >= a.period);
        return i < 0 ? null : <line key={a.period + a.label} x1={x(i)} x2={x(i)} y1="0" y2={H} stroke="#c7863c" strokeWidth="1.5" />;
      })}
      <path d={line} fill="none" stroke="#2f7f99" strokeWidth="2.5" strokeLinejoin="round" />
    </svg>
  );
}

export function KpiCard({ kpi, annotations = [] }: { kpi: KpiSummary; annotations?: { period: string; label: string }[] }) {
  const fmt = (v: number | null) => (v == null ? "—" : `${Number.isInteger(v) ? v : v.toFixed(1)}${kpi.unit}`);
  return (
    <article className="rounded-2xl border border-line bg-white p-4 shadow-sm">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="font-bold">{kpi.name}</h3>
        <span className="text-sm text-muted">目標 {kpi.target_value == null ? "未設定" : fmt(kpi.target_value)}</span>
      </div>
      {kpi.data_status === "not_collected" ? (
        <p className="my-6 rounded-lg border border-dashed border-line p-3 text-center text-sm text-muted">
          データ未取得（0 ではありません）
        </p>
      ) : (
        <Chart kpi={kpi} annotations={annotations} />
      )}
      <div className="flex items-center justify-between text-sm">
        <span>
          現在 <strong className="text-lg">{fmt(kpi.current_value)}</strong>
          {kpi.current_period && <span className="ml-1 text-muted">（{kpi.current_period}）</span>}
        </span>
        {kpi.trend && <span className="text-muted">{TREND[kpi.trend]}</span>}
      </div>
      {kpi.source && (
        <p className="mt-2 text-xs text-muted">
          出典: {kpi.source.title}（{kpi.source.publisher}・{kpi.source.license}）{kpi.source.is_sample && <SampleBadge />}
        </p>
      )}
      {annotations.length > 0 && (
        <ul className="mt-1 text-xs text-[#8a5a1c]">
          {annotations.map((a) => (
            <li key={a.period + a.label}>▍{a.period} {a.label}</li>
          ))}
        </ul>
      )}
    </article>
  );
}
