import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Survey } from "../api";
import { SurveyProgress } from "../components/SurveyComposer";
import { Button, Card, ErrorNote, Loading } from "../components/ui";

type SurveyView = Survey & { issue_card: { id: number; title: string }; kpi: { name: string; unit: string }; is_owner: boolean };

/** 回答ページ (F-11): anyone signed in can answer, once per month (answering again replaces it). */
export function SurveyAnswer() {
  const { id } = useParams();
  const qc = useQueryClient();
  const [value, setValue] = useState<string>("");
  const s = useQuery({ queryKey: ["survey", id], queryFn: () => api<SurveyView>(`/surveys/${id}`) });
  const send = useMutation({
    mutationFn: () => api<Survey>(`/surveys/${id}/responses`, { method: "POST", json: { value: Number(value) } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["survey", id] }),
  });
  if (s.isLoading) return <Loading />;
  if (!s.data) return <ErrorNote error={s.error} />;
  const v = s.data;
  return (
    <Card>
      <p className="text-xs text-muted">{v.kind === "observation" ? "📋 現場観測" : "📝 アンケート"}・課題カード「<Link className="underline" to={`/issues/${v.issue_card.id}`}>{v.issue_card.title}</Link>」の KPI「{v.kpi.name}」</p>
      <h2 className="mt-1 text-lg font-bold">{v.title}</h2>
      {v.audience && <p className="text-xs text-muted">回答してほしい人: {v.audience}</p>}
      <p className="mt-3 font-semibold">{v.question}</p>
      {v.status !== "open" ? (
        <p className="mt-3 rounded-lg bg-warn-soft p-3 text-sm text-warn">{v.status === "draft" ? "まだ回答を受け付けていません。" : "回答の受付は終了しました。"}</p>
      ) : (
        <form className="mt-3 space-y-3" onSubmit={(e) => { e.preventDefault(); send.mutate(); }}>
          {v.answer_type === "rating5" ? (
            <div className="flex gap-2" role="radiogroup" aria-label="5 段階で答える">
              {[1, 2, 3, 4, 5].map((n) => (
                <button key={n} type="button" role="radio" aria-checked={value === String(n)} onClick={() => setValue(String(n))}
                  className={`h-12 w-12 rounded-xl border text-lg font-bold ${value === String(n) ? "border-brand bg-brand text-white" : "border-line bg-white"}`}>
                  {n}
                </button>
              ))}
            </div>
          ) : (
            <label className="flex items-center gap-2">
              <input className="input w-32" inputMode="decimal" aria-label="数値で答える" value={value} onChange={(e) => setValue(e.target.value)} />
              <span>{v.unit}</span>
            </label>
          )}
          <Button disabled={value === "" || send.isPending}>{v.answered_this_period ? "回答を更新する" : "回答する"}</Button>
          {v.answered_this_period && <p className="text-xs text-muted">今月はすでに回答しています。もう一度送ると、前の回答と置き換わります。</p>}
          <ErrorNote error={send.error} />
        </form>
      )}
      <div className="mt-4 rounded-lg border border-line p-3 text-xs text-muted">
        <p>回答は月ごとに集計し、{v.min_responses} 件以上集まった月だけ平均値をダッシュボードに出します。個別の回答と回答者は誰にも表示されません。</p>
        <SurveyProgress survey={v} />
      </div>
    </Card>
  );
}
