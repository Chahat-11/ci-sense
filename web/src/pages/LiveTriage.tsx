import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  Brain,
  Check,
  ChevronRight,
  Download,
  FileSearch,
  GitCompare,
  LoaderCircle,
  Play,
  Scale,
  ShieldCheck,
  X,
} from "lucide-react";
import { streamTriage, useApi } from "../api";
import type { FailedRun, StageName, StreamEvent, TriageResult } from "../types";
import { ERROR_LINE, firstLine, formatBytes, formatDuration, shortSha, timeAgo } from "../format";
import { CandidateList, ScoreMeter, VerdictCard } from "../components/Verdict";
import { Card, CardHeader, ConfidenceBar, EmptyState, ErrorState, PageHeader, ShaChip, Skeleton, SourceBadge, Tag, cx } from "../components/ui";
import { SectionTitle } from "./TriageDetail";

type StepStatus = "pending" | "running" | "done" | "error";
interface StepState {
  status: StepStatus;
  startedAt?: number;
  duration?: number;
  preview?: Record<string, unknown> | null;
}

const STEPS: { stage: StageName; title: string; description: string; icon: typeof Download }[] = [
  { stage: "fetching logs", title: "Fetch logs", description: "Download the run's log archive from GitHub Actions", icon: Download },
  { stage: "distilling", title: "Distil error", description: "Strip timestamps and cleanup noise, keep windows around errors", icon: FileSearch },
  { stage: "finding candidates", title: "Find candidates", description: "Commits between the base and the failing sha", icon: GitCompare },
  { stage: "scoring", title: "Score", description: "Deterministic signals: files, identifiers, config changes", icon: Scale },
  { stage: "LLM verdict", title: "LLM verdict", description: "Pick the responsible commit, validated against candidates", icon: Brain },
];

const initialSteps = () => Object.fromEntries(STEPS.map((s) => [s.stage, { status: "pending" } as StepState])) as Record<string, StepState>;

type Phase = "idle" | "running" | "done" | "error";

export default function LiveTriage() {
  const runs = useApi<FailedRun[]>("/api/runs/failed");
  const [runId, setRunId] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [steps, setSteps] = useState<Record<string, StepState>>(initialSteps);
  const [result, setResult] = useState<{ result: TriageResult; comment: string; duration: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const controller = useRef<AbortController | null>(null);

  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (phase !== "running") return;
    const timer = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(timer);
  }, [phase]);

  const validId = /^\d+$/.test(runId.trim());

  async function run() {
    if (!validId || phase === "running") return;
    controller.current?.abort();
    const ctrl = new AbortController();
    controller.current = ctrl;
    setSteps(initialSteps());
    setResult(null);
    setError(null);
    setPhase("running");
    const t0 = Date.now();
    setStartedAt(t0);
    setNow(t0);

    const onEvent = (e: StreamEvent) => {
      if (e.type === "started") {
        setSteps((s) => ({ ...s, "fetching logs": { status: "running", startedAt: Date.now() } }));
      } else if (e.type === "stage") {
        if (!STEPS.some((st) => st.stage === e.stage)) return;
        setSteps((s) =>
          e.status === "running"
            ? { ...s, [e.stage]: { ...s[e.stage], status: "running", startedAt: s[e.stage].startedAt ?? Date.now() } }
            : { ...s, [e.stage]: { ...s[e.stage], status: "done", duration: e.duration_ms, preview: e.preview } },
        );
      } else if (e.type === "result") {
        setResult({ result: e.result, comment: e.comment, duration: e.duration_ms });
        setPhase("done");
      } else if (e.type === "error") {
        setError(e.message);
        setPhase("error");
        setSteps((s) => {
          const failing = e.stage && STEPS.some((st) => st.stage === e.stage) ? e.stage : "fetching logs";
          return { ...s, [failing]: { ...s[failing], status: "error" } };
        });
      }
    };

    try {
      await streamTriage(runId.trim(), onEvent, ctrl.signal);
    } catch (err) {
      setError((err as Error).message);
      setPhase("error");
    }
    setNow(Date.now());
  }

  const elapsed = startedAt ? (result ? result.duration : now - startedAt) : 0;

  return (
    <>
      <PageHeader
        title="Live triage"
        description="Run the full CI-Sense pipeline against any failed run and watch each stage as it happens."
        actions={
          <span className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-panel px-2.5 py-1.5 text-xs text-fg-muted">
            <ShieldCheck size={13} className="text-ok" />
            Dry run — never posts to GitHub
          </span>
        }
      />

      <div className="grid grid-cols-[340px_minmax(0,1fr)] items-start gap-5">
        <div className="space-y-3">
          <Card className="p-3">
            <label htmlFor="run-id" className="mb-1.5 block px-0.5 text-xs font-medium text-fg-muted">
              Workflow run ID
            </label>
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                run();
              }}
            >
              <input
                id="run-id"
                value={runId}
                onChange={(e) => setRunId(e.target.value)}
                placeholder="e.g. 36314578255"
                inputMode="numeric"
                autoComplete="off"
                className="min-w-0 flex-1 rounded-lg border border-line-strong bg-bg px-3 py-2 font-mono text-sm text-fg outline-none transition-colors placeholder:text-fg-subtle focus:border-accent"
              />
              <button
                type="submit"
                disabled={!validId || phase === "running"}
                className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3.5 py-2 text-sm font-medium text-bg transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {phase === "running" ? <LoaderCircle size={14} className="animate-spin" /> : <Play size={14} fill="currentColor" />}
                Run
              </button>
            </form>
            {runId && !validId && <div className="mt-1.5 px-0.5 text-xs text-bad">Run IDs are numeric.</div>}
          </Card>

          <Card className="overflow-hidden">
            <CardHeader title="Recent failed runs" meta={runs.data ? `${runs.data.length}` : undefined} />
            <div className="max-h-[560px] overflow-y-auto">
              {runs.error ? (
                <div className="p-3">
                  <ErrorState message={runs.error} onRetry={runs.reload} />
                </div>
              ) : runs.loading && !runs.data ? (
                Array.from({ length: 6 }, (_, i) => (
                  <div key={i} className="space-y-2 border-b border-line px-4 py-3">
                    <Skeleton className="h-3 w-1/2" />
                    <Skeleton className="h-3 w-4/5" />
                  </div>
                ))
              ) : runs.data?.length === 0 ? (
                <EmptyState title="No failed runs" description="Failed tests runs will be listed here." />
              ) : (
                runs.data?.map((r) => (
                  <RunRow key={r.id} run={r} selected={runId.trim() === String(r.id)} onSelect={() => setRunId(String(r.id))} />
                ))
              )}
            </div>
          </Card>
        </div>

        <div className="min-w-0 space-y-6">
          <Card className="overflow-hidden">
            <div className="flex items-center justify-between border-b border-line px-5 py-3">
              <div className="flex items-center gap-2 text-[13px] font-medium">
                Pipeline
                {phase !== "idle" && <span className="font-mono text-xs font-normal text-fg-subtle">run {runId.trim()}</span>}
              </div>
              <PhaseIndicator phase={phase} elapsed={elapsed} />
            </div>
            <ol className="px-5 py-5">
              {STEPS.map((step, i) => (
                <Step
                  key={step.stage}
                  index={i}
                  step={step}
                  state={steps[step.stage]}
                  now={now}
                  last={i === STEPS.length - 1}
                />
              ))}
            </ol>
            {phase === "idle" && (
              <div className="border-t border-line px-5 py-3 text-xs text-fg-subtle">
                Pick a failed run on the left or paste a run ID, then press Run.
              </div>
            )}
          </Card>

          {error && <ErrorState message={error} onRetry={validId ? run : undefined} />}

          {result && (
            <div className="animate-rise space-y-6">
              <section>
                <SectionTitle meta={`${result.result.model}`}>Verdict</SectionTitle>
                <VerdictCard result={result.result} />
              </section>
              <section>
                <SectionTitle meta="Ranked by deterministic score">Candidate commits</SectionTitle>
                <CandidateList candidates={result.result.candidates} responsible={result.result.responsible_commit} />
              </section>
              <CommentPreview comment={result.comment} />
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function PhaseIndicator({ phase, elapsed }: { phase: Phase; elapsed: number }) {
  if (phase === "idle") return <span className="text-xs text-fg-subtle">Ready</span>;
  const label = { running: "Running", done: "Completed", error: "Failed" }[phase];
  const tone = { running: "text-accent", done: "text-ok", error: "text-bad" }[phase];
  return (
    <span className={cx("inline-flex items-center gap-2 text-xs", tone)}>
      {phase === "running" && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />}
      {label}
      <span className="tabular font-mono text-fg-muted">{(elapsed / 1000).toFixed(1)} s</span>
    </span>
  );
}

function Step({ index, step, state, now, last }: { index: number; step: (typeof STEPS)[number]; state: StepState; now: number; last: boolean }) {
  const Icon = step.icon;
  const running = state.status === "running";
  const live = running && state.startedAt ? now - state.startedAt : undefined;
  return (
    <li className="relative flex gap-4 pb-6 last:pb-0">
      {!last && (
        <div className="absolute left-[15px] top-9 bottom-1 w-px bg-line">
          <div
            className={cx("w-full bg-ok/60 transition-[height] duration-500 ease-out", state.status === "done" ? "h-full" : "h-0")}
          />
        </div>
      )}
      <div className="relative z-10 shrink-0">
        {running && <span className="absolute inset-0 animate-ping rounded-full bg-accent/25" />}
        <div
          className={cx(
            "relative flex h-8 w-8 items-center justify-center rounded-full border transition-all duration-300",
            state.status === "pending" && "border-line-strong bg-panel text-fg-subtle",
            running && "border-accent bg-accent-soft text-accent shadow-[0_0_18px] shadow-accent/30",
            state.status === "done" && "border-ok/50 bg-ok/10 text-ok",
            state.status === "error" && "border-bad/50 bg-bad/10 text-bad",
          )}
        >
          {state.status === "done" ? (
            <Check size={15} strokeWidth={2.5} className="animate-fade-in" />
          ) : state.status === "error" ? (
            <X size={15} strokeWidth={2.5} />
          ) : running ? (
            <LoaderCircle size={15} className="animate-spin" />
          ) : (
            <Icon size={14} />
          )}
        </div>
      </div>
      <div className="min-w-0 flex-1 pt-1">
        <div className="flex items-baseline justify-between gap-3">
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-[11px] text-fg-subtle">0{index + 1}</span>
            <span className={cx("text-sm font-medium transition-colors", state.status === "pending" ? "text-fg-muted" : "text-fg")}>
              {step.title}
            </span>
          </div>
          <span className="tabular font-mono text-xs text-fg-subtle">
            {state.status === "done" ? formatDuration(state.duration) : live !== undefined ? formatDuration(live) : ""}
          </span>
        </div>
        <div className="mt-0.5 text-xs text-fg-subtle">{step.description}</div>
        {state.status === "done" && state.preview && (
          <div className="animate-rise mt-3">
            <StagePreview stage={step.stage} preview={state.preview} />
          </div>
        )}
      </div>
    </li>
  );
}

function StagePreview({ stage, preview }: { stage: StageName; preview: Record<string, unknown> }) {
  if (stage === "fetching logs") {
    return (
      <PreviewLine>
        <span className="font-mono text-fg">{Number(preview.log_lines).toLocaleString()}</span> log lines ·{" "}
        <span className="font-mono text-fg">{formatBytes(Number(preview.log_bytes))}</span> downloaded
      </PreviewLine>
    );
  }
  if (stage === "distilling") {
    const lines = String(preview.preview ?? "")
      .replace(/^\s*\n/, "")
      .split("\n")
      .filter((l) => l.trim())
      .slice(0, 7);
    return (
      <div>
        <PreviewLine>
          Kept <span className="font-mono text-fg">{String(preview.lines)}</span> lines around errors
        </PreviewLine>
        <div className="mt-2 overflow-hidden rounded-lg border border-line bg-bg px-3 py-2 font-mono text-[11px] leading-[1.7]">
          {lines.map((l, i) => (
            <div key={i} className={cx("truncate whitespace-pre", ERROR_LINE.test(l) ? "text-[#ffb4b6]" : "text-fg-subtle")}>
              {l}
            </div>
          ))}
        </div>
      </div>
    );
  }
  if (stage === "finding candidates") {
    const cands = (preview.candidates as { sha: string; message: string }[]) ?? [];
    const base = preview.pr_number ? `PR #${preview.pr_number} base` : preview.last_good_sha ? shortSha(String(preview.last_good_sha)) : "recent history";
    return (
      <div>
        <PreviewLine>
          <span className="font-mono text-fg">{cands.length}</span> candidate{cands.length === 1 ? "" : "s"} · {base} →{" "}
          <span className="font-mono">{shortSha(String(preview.head_sha))}</span>
        </PreviewLine>
        <div className="mt-2 space-y-1.5">
          {cands.slice(0, 5).map((c) => (
            <div key={c.sha} className="flex items-center gap-2 text-xs">
              <ShaChip sha={c.sha} />
              <span className="truncate text-fg-muted">{c.message}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }
  if (stage === "scoring") {
    const scores = [...((preview.scores as { sha: string; score: number; reasons: string[] }[]) ?? [])].sort((a, b) => b.score - a.score);
    return (
      <div className="space-y-2">
        {scores.map((s, i) => (
          <div key={s.sha} className="flex items-center gap-3">
            <ShaChip sha={s.sha} />
            <div className="min-w-0 flex-1 truncate text-xs text-fg-subtle">{s.reasons.join(" · ") || "no signals"}</div>
            <ScoreMeter score={s.score} guilty={i === 0 && s.score > 0} />
          </div>
        ))}
      </div>
    );
  }
  if (stage === "LLM verdict") {
    const sha = preview.responsible_commit as string | null;
    return (
      <div className="flex flex-wrap items-center gap-3">
        {sha ? <ShaChip sha={sha} tone="bad" /> : <Tag tone="warn">No confident culprit</Tag>}
        {sha && <ConfidenceBar value={preview.confidence as number | null} />}
        <SourceBadge fallback={Boolean(preview.fallback)} />
      </div>
    );
  }
  return null;
}

function PreviewLine({ children }: { children: ReactNode }) {
  return <div className="text-xs text-fg-muted">{children}</div>;
}

function RunRow({ run, selected, onSelect }: { run: FailedRun; selected: boolean; onSelect: () => void }) {
  return (
    <button
      onClick={onSelect}
      className={cx(
        "group flex w-full items-start gap-3 border-b border-line px-4 py-3 text-left transition-colors last:border-b-0",
        selected ? "bg-accent-soft" : "hover:bg-raised/60",
      )}
    >
      <span className={cx("mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full", selected ? "bg-accent" : "bg-bad/80")} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate font-mono text-xs text-fg">{run.branch}</span>
          {run.pr_number && <span className="shrink-0 font-mono text-[11px] text-fg-subtle">#{run.pr_number}</span>}
        </div>
        <div className="mt-0.5 truncate text-xs text-fg-muted">{firstLine(run.commit_message)}</div>
        <div className="mt-1.5 flex items-center gap-2 text-[11px] text-fg-subtle">
          <span className="font-mono">{run.id}</span>
          <span>·</span>
          <span>{timeAgo(run.created_at)}</span>
          {run.triaged && (
            <>
              <span>·</span>
              <span className="text-ok/80">triaged</span>
            </>
          )}
        </div>
      </div>
      <ChevronRight size={14} className={cx("mt-1 shrink-0 transition-colors", selected ? "text-accent" : "text-fg-subtle/0 group-hover:text-fg-subtle")} />
    </button>
  );
}

function CommentPreview({ comment }: { comment: string }) {
  const [open, setOpen] = useState(false);
  const visible = comment.replace(/\n*<!-- ci-sense-data[\s\S]*?-->\s*$/, "");
  return (
    <Card className="overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-4 py-3 text-left text-[13px] font-medium text-fg-muted transition-colors hover:text-fg"
      >
        <ChevronRight size={14} className={cx("transition-transform", open && "rotate-90")} />
        PR comment that would be posted
        <span className="ml-auto text-xs font-normal text-fg-subtle">Markdown · not posted</span>
      </button>
      {open && (
        <pre className="animate-fade-in max-h-[420px] overflow-auto border-t border-line bg-bg px-5 py-4 font-mono text-[12px] leading-relaxed whitespace-pre-wrap text-fg-muted">
          {visible}
        </pre>
      )}
    </Card>
  );
}
