// Thin client for the 渋谷共創ダッシュボード API. The demo user is chosen in the
// header and sent as X-User-Id (real authentication is out of the MVP scope).

const USER_KEY = "shibuya.userId";

export function getUserId(): number {
  try {
    return Number(localStorage.getItem(USER_KEY) ?? "1") || 1;
  } catch {
    return 1;
  }
}

export function setUserId(id: number) {
  try {
    localStorage.setItem(USER_KEY, String(id));
  } catch {
    /* storage unavailable: keep the default user */
  }
}

export class ApiError extends Error {
  status: number;
  code: string;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    const d = detail as { message?: string; code?: string } | string;
    super(typeof d === "string" ? d : d?.message ?? `エラー (${status})`);
    this.status = status;
    this.code = typeof d === "object" && d ? d.code ?? "" : "";
    this.detail = detail;
  }
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { "X-User-Id": String(getUserId()) };
  let body = init.body;
  if (init.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.json);
  }
  const res = await fetch(`/api${path}`, { ...init, body, headers: { ...headers, ...(init.headers as object) } });
  const data = res.headers.get("content-type")?.includes("json") ? await res.json() : await res.text();
  if (!res.ok) {
    if (Array.isArray(data?.detail)) throw new ApiError(res.status, "入力内容を確認してください");
    throw new ApiError(res.status, data?.detail ?? data);
  }
  return data as T;
}

export type Proposal<P> = {
  id: number;
  kind: string;
  payload: P;
  evidence: { kind: string; ref: string; label: string }[];
  status: "proposed" | "adopted" | "adopted_edited" | "rejected";
  model: string;
  decided_at: number | null;
};

export type Kpi = {
  id: number;
  name: string;
  unit: string;
  measurement: string;
  data_availability: "open_data" | "survey_needed" | "unknown";
  target_value: number | null;
  points: { period: string; value: number }[];
  dataset: Dataset | null;
};

export type Dataset = {
  id: number;
  title: string;
  publisher: string;
  description: string;
  license: string;
  source_url: string;
  file_format: string;
  updated_on: string;
  granularity: string;
  is_sample: boolean;
};

export type IssueCard = {
  id: number;
  title: string;
  target: string;
  place_time: string;
  evidence: { kind: string; text: string; quote?: string }[];
  focus_area: string;
  focus_area_label: string;
  focus_reason: string;
  status: string;
  status_label: string;
  author_id: number;
  author_name: string;
  author_attribute: string;
  visibility: string;
  community_id: number | null;
  kpis: Kpi[];
  dashboard: { id: number; public_slug: string; status: string } | null;
  origin_proposal: { id: number; status: string; model: string } | null;
  latest_decision: { state: string; reason: string; department: string; decided_by_name: string } | null;
  policy_news: PolicyNewsLink[];
  community: { id: number; name: string } | null;
  origin: { kind: "thread" | "news" | "conversation"; label: string; path: string } | null;
  origin_kind: string;
  origin_ref: string;
};

export type PolicyNewsLink = { id: number; title: string; published_at: string; department?: string };

export type Annotation = {
  id: number;
  period: string;
  label: string;
  kind: "policy_start" | "event" | "definition_change";
  kind_label: string;
  news_id: number | null;
};

export type Comparison = {
  annotation_id: number;
  period: string;
  label: string;
  kind: Annotation["kind"];
  kpis: {
    kpi_id: number;
    name: string;
    unit: string;
    before_value: number | null;
    after_value: number | null;
    after_periods: number;
    before_per_period: number | null;
    after_per_period: number | null;
    state: "ok" | "no_after" | "no_before" | "no_data";
  }[];
};

export type KpiSummary = {
  id: number;
  name: string;
  unit: string;
  target_value: number | null;
  current_value: number | null;
  current_period: string | null;
  data_status: "available" | "not_collected";
  trend: "up" | "down" | "flat" | null;
  points: { period: string; value: number }[];
  source: { title: string; publisher: string; license: string; source_url: string; updated_on: string; is_sample: boolean } | null;
};

export type DashboardView = {
  issue_card_id: number;
  title: string;
  target: string;
  place_time: string;
  focus_area_label: string;
  status: string;
  status_label: string;
  evidence_sources: { kind: string; text: string }[];
  kpis: KpiSummary[];
  dashboard: { id: number; public_slug: string; status: string } | null;
  latest_decision: { state: string; reason: string; department: string } | null;
  annotations: Annotation[];
  comparisons: Comparison[];
  causality_note: string;
  policy_news: PolicyNewsLink[];
  community_id?: number | null;
  community_members?: number;
};

export type User = { id: number; display_name: string; role: string; attribute: string; department: string };

export const ATTRIBUTE_LABEL: Record<string, string> = {
  resident: "住民",
  visitor: "来訪者",
  business: "事業者",
};

export function roleLabel(u: { role: string; attribute: string; department?: string }) {
  if (u.role === "staff") return `区職員${u.department ? `（${u.department}）` : ""}`;
  if (u.role === "community_manager") return "コミュニティ運営";
  return ATTRIBUTE_LABEL[u.attribute] ?? "参加者";
}
