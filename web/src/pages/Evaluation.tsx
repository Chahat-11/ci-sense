import { useNavigate } from "react-router";
import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { Check, FlaskConical, Minus, X } from "lucide-react";
import { useApi } from "../api";
import type { CaseResult, EvalCase, Evaluation } from "../types";
import { CATEGORY_LABELS, firstLine, pct } from "../format";
import { Card, CardHeader, ConfidenceBar, EmptyState, ErrorState, PageHeader, ResultBadge, ShaChip, Skeleton, SourceBadge, cx } from "../components/ui";

export default function EvaluationPage() {
  const { data, error, loading, reload } = useApi<Evaluation>("/api/evaluation");

  return (
    <>
      <PageHeader
        title="Evaluation"
        description="Seeded pull requests with known breakages. Each verdict CI-Sense posted is scored against the commit that actually introduced the failure."
      />
      {error ? (
        error.includes("No evaluation results") ? (
          <Card>
            <EmptyState
              icon={<FlaskConical size={18} />}
              title="No evaluation yet"
              description={
                <>
                  Seed cases with <code className="font-mono text-fg">scripts/seed_failures.py</code>, then score them with{" "}
                  <code className="font-mono text-fg">scripts/evaluate.py</code>.
                </>
              }
            />
          </Card>
        ) : (
          <ErrorState message={error} onRetry={reload} />
        )
      ) : loading || !data ? (
        <EvaluationSkeleton />
      ) : (
        <>
          <EvaluationBody data={data} />
          <AblationCard />
        </>
      )}
    </>
  );
}

function EvaluationBody({ data }: { data: Evaluation }) {
  const navigate = useNavigate();
  const completed = data.cases.filter((c) => c.result !== "pending");
  const llmCorrect = completed.filter((c) => c.result === "correct").length;
  const detDone = data.cases.filter((c) => c.deterministic_result);
  const detCorrect = detDone.filter((c) => c.deterministic_result === "correct").length;
  const rescued = data.cases.filter((c) => c.result === "correct" && c.deterministic_result === "wrong");
  const multi = data.cases.filter((c) => c.commits.length > 1);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.35fr)] gap-4">
        <Headline
          label="With LLM"
          value={pct(data.accuracy.llm)}
          detail={`${llmCorrect} of ${completed.length} cases correct`}
          accent
        />
        <Headline
          label="Deterministic scoring only"
          value={pct(data.accuracy.deterministic)}
          detail={`${detCorrect} of ${detDone.length} cases correct`}
        />
        <Card className="flex flex-col">
          <CardHeader title="Accuracy by method" meta={`${completed.length} seeded cases`} />
          <div className="h-[132px] px-3 pt-3">
            <AccuracyChart deterministic={data.accuracy.deterministic ?? 0} llm={data.accuracy.llm ?? 0} />
          </div>
        </Card>
      </div>

      {rescued.length > 0 && (
        <Card className="px-5 py-4">
          <div className="text-[13px] font-medium">
            Where the LLM changed the outcome: case{rescued.length > 1 ? "s" : ""} {rescued.map((c) => c.case).join(" and ")}
          </div>
          <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-fg-muted">
            In each, an innocent commit that edits the failing test file outscores the real culprit: it touches the file named in the
            error and shares its identifiers. Scoring alone blames it; the LLM reads the diffs and identifies the source change that
            broke the test.
          </p>
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            {rescued.map((c) => (
              <RescueRow key={c.case} c={c} />
            ))}
          </div>
        </Card>
      )}

      <Card className="overflow-hidden">
        <CardHeader
          title="Cases"
          meta={`${multi.length} multi-commit · ${data.cases.length - multi.length} single-commit`}
        />
        <div className="grid grid-cols-[minmax(0,1fr)_150px_104px_116px_116px_124px_64px_96px] gap-3 border-b border-line px-4 py-2 text-[11px] font-medium uppercase tracking-wider text-fg-subtle">
          <span>Case</span>
          <span>Category</span>
          <span>Culprit</span>
          <span>Scoring only</span>
          <span>Verdict</span>
          <span>Confidence</span>
          <span>Source</span>
          <span>Result</span>
        </div>
        {data.cases.map((c, i) => (
          <div
            key={c.case}
            role={c.triage_id ? "link" : undefined}
            tabIndex={c.triage_id ? 0 : undefined}
            onClick={() => c.triage_id && navigate(`/triages/${c.triage_id}`)}
            onKeyDown={(e) => e.key === "Enter" && c.triage_id && navigate(`/triages/${c.triage_id}`)}
            style={{ animationDelay: `${i * 30}ms` }}
            className={cx(
              "animate-rise grid grid-cols-[minmax(0,1fr)_150px_104px_116px_116px_124px_64px_96px] items-center gap-3 border-b border-line px-4 py-3 last:border-b-0",
              c.triage_id != null && "cursor-pointer transition-colors hover:bg-raised/60",
            )}
          >
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-fg-subtle">{c.case}</span>
                <span className="truncate text-sm font-medium">{c.name?.replace(/-/g, " ")}</span>
              </div>
              <div className="mt-0.5 truncate text-xs text-fg-muted" title={c.description ?? undefined}>
                {c.description}
              </div>
            </div>
            <span className="truncate text-xs text-fg-muted">{CATEGORY_LABELS[c.category] ?? c.category}</span>
            <div title={firstLine(c.expected_message)}>
              <ShaChip sha={c.expected_sha} />
            </div>
            <PickCell sha={c.deterministic_sha} result={c.deterministic_result} />
            <PickCell sha={c.verdict_sha} result={c.result} />
            <ConfidenceBar value={c.confidence} width="w-14" />
            <div>{c.source ? <SourceBadge fallback={c.source === "fallback"} /> : <span className="text-xs text-fg-subtle">—</span>}</div>
            <ResultBadge result={c.result} />
          </div>
        ))}
        <div className="flex flex-wrap gap-x-6 gap-y-1 border-t border-line bg-bg/40 px-4 py-2.5 text-xs text-fg-subtle">
          {(Object.entries(data.summary.counts) as [CaseResult, number][]).map(([k, v]) => (
            <span key={k}>
              <span className="tabular font-mono text-fg-muted">{v}</span> {k}
            </span>
          ))}
          <span className="ml-auto">
            <span className="tabular font-mono text-fg-muted">{data.summary.llm}</span> LLM ·{" "}
            <span className="tabular font-mono text-fg-muted">{data.summary.fallback}</span> fallback
          </span>
        </div>
      </Card>
    </div>
  );
}

function Headline({ label, value, detail, accent }: { label: string; value: string; detail: string; accent?: boolean }) {
  return (
    <Card className="animate-rise relative overflow-hidden px-5 py-5">
      {accent && <div className="absolute inset-x-0 top-0 h-px bg-accent/70" />}
      <div className="text-xs font-medium text-fg-muted">{label}</div>
      <div className={cx("tabular mt-3 text-[44px] font-semibold leading-none tracking-tight", accent ? "text-fg" : "text-fg-muted")}>
        {value}
      </div>
      <div className="mt-3 text-xs text-fg-subtle">{detail}</div>
    </Card>
  );
}

function AccuracyChart({ deterministic, llm }: { deterministic: number; llm: number }) {
  const rows = [
    { name: "Scoring only", value: Math.round(deterministic * 100), fill: "#3a3a45" },
    { name: "With LLM", value: Math.round(llm * 100), fill: "#7c83ff" },
  ];
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 44, bottom: 0, left: 8 }} barCategoryGap={14}>
        <XAxis type="number" domain={[0, 100]} hide />
        <YAxis type="category" dataKey="name" tick={{ fill: "#a1a1ad", fontSize: 12 }} axisLine={false} tickLine={false} width={92} />
        <Bar dataKey="value" radius={[0, 4, 4, 0]} background={{ fill: "#15151a", radius: 4 }} animationDuration={700}>
          {rows.map((r) => (
            <Cell key={r.name} fill={r.fill} />
          ))}
          <LabelList dataKey="value" position="right" formatter={(v) => `${v}%`} fill="#ececf1" fontSize={12} fontFamily="Geist Mono" />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function PickCell({ sha, result }: { sha: string | null; result: CaseResult | null }) {
  const icon =
    result === "correct" ? (
      <Check size={13} strokeWidth={2.5} className="text-ok" />
    ) : result === "wrong" ? (
      <X size={13} strokeWidth={2.5} className="text-bad" />
    ) : result === "abstained" ? (
      <Minus size={13} className="text-warn" />
    ) : null;
  return (
    <div className="flex items-center gap-1.5">
      <ShaChip sha={sha} tone={result === "wrong" ? "bad" : "default"} />
      {icon}
    </div>
  );
}

function RescueRow({ c }: { c: EvalCase }) {
  const msg = (sha: string | null) => firstLine(c.commits.find((x) => x.sha === sha)?.message);
  const score = (sha: string | null) => c.scores.find((s) => s.sha === sha)?.score;
  return (
    <div className="rounded-lg border border-line bg-bg/50 px-3.5 py-3 text-xs">
      <div className="mb-2 font-mono text-fg-subtle">case {c.case}</div>
      <div className="flex items-center gap-2">
        <span className="w-24 shrink-0 text-fg-subtle">Scoring picked</span>
        <ShaChip sha={c.deterministic_sha} tone="bad" />
        <span className="truncate text-fg-muted">{msg(c.deterministic_sha)}</span>
        <span className="ml-auto shrink-0 font-mono text-fg-subtle">{score(c.deterministic_sha)}</span>
      </div>
      <div className="mt-1.5 flex items-center gap-2">
        <span className="w-24 shrink-0 text-fg-subtle">LLM picked</span>
        <ShaChip sha={c.verdict_sha} tone="ok" />
        <span className="truncate text-fg-muted">{msg(c.verdict_sha)}</span>
        <span className="ml-auto shrink-0 font-mono text-fg-subtle">{score(c.verdict_sha)}</span>
      </div>
    </div>
  );
}

function EvaluationSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        {[0, 1, 2].map((i) => (
          <Card key={i} className="px-5 py-5">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="mt-4 h-10 w-24" />
            <Skeleton className="mt-4 h-3 w-32" />
          </Card>
        ))}
      </div>
      <Card>
        {Array.from({ length: 8 }, (_, i) => (
          <div key={i} className="flex items-center gap-4 border-b border-line px-4 py-3.5 last:border-b-0">
            <Skeleton className="h-3.5 w-1/4" />
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-5 w-24" />
            <Skeleton className="ml-auto h-5 w-16" />
          </div>
        ))}
      </Card>
    </div>
  );
}

interface AblationStats {
  n: number;
  correct: number;
  accuracy: number | null;
  ci95: [number, number] | null;
}
interface Ablation {
  summary: Record<string, AblationStats>;
  multi_commit_only?: Record<string, AblationStats>;
  sourcegraph_usage?: { runs: number; runs_with_context: number; cases_with_context: string[] };
}

const VARIANT_LABELS: Record<string, string> = {
  last_commit: "Newest commit (baseline)",
  deterministic: "Deterministic scoring",
  llm: "LLM",
  llm_sourcegraph: "LLM + Sourcegraph",
};

function AblationCard() {
  const { data } = useApi<Ablation>("/api/ablation");
  if (!data) return null;
  const range = (s: AblationStats) => (s.ci95 ? `${pct(s.ci95[0])} – ${pct(s.ci95[1])}` : "—");
  const usage = data.sourcegraph_usage;
  const multi = (v: string) => data.multi_commit_only?.[v];
  return (
    <Card className="mt-4">
      <CardHeader
        title="Ablation and baselines"
        meta={usage ? `Sourcegraph context retrieved in ${usage.runs_with_context} of ${usage.runs} runs` : "Sourcegraph usage not logged in this run"}
      />
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-line text-left text-fg-subtle">
            <th className="px-4 py-2 font-medium">Variant</th>
            <th className="px-4 py-2 font-medium">All cases</th>
            <th className="px-4 py-2 font-medium">95% CI</th>
            <th className="px-4 py-2 font-medium">Multi-commit only</th>
          </tr>
        </thead>
        <tbody>
          {Object.keys(VARIANT_LABELS).map((v) =>
            data.summary[v] ? (
              <tr key={v} className="border-b border-line last:border-b-0">
                <td className="px-4 py-2.5 text-fg">{VARIANT_LABELS[v]}</td>
                <td className="px-4 py-2.5 font-mono">
                  {pct(data.summary[v].accuracy)} ({data.summary[v].correct}/{data.summary[v].n})
                </td>
                <td className="px-4 py-2.5 font-mono text-fg-muted">{range(data.summary[v])}</td>
                <td className="px-4 py-2.5 font-mono">
                  {multi(v) ? `${pct(multi(v)!.accuracy)} (${multi(v)!.correct}/${multi(v)!.n})` : "—"}
                </td>
              </tr>
            ) : null,
          )}
        </tbody>
      </table>
    </Card>
  );
}
