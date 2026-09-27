import { useState } from "react";
import { ChevronRight, FileCode2, Sparkles, TriangleAlert } from "lucide-react";
import type { Candidate, TriageResult } from "../types";
import { ERROR_LINE, firstLine } from "../format";
import { Card, CardHeader, ConfidenceBar, ShaChip, SourceBadge, Tag, cx } from "./ui";

const MAX_SCORE = 7;

export function VerdictCard({ result }: { result: TriageResult }) {
  const [showReasoning, setShowReasoning] = useState(false);
  const responsible = result.candidates.find((c) => c.sha === result.responsible_commit);

  return (
    <Card className="animate-rise overflow-hidden">
      <div className="flex items-center justify-between gap-4 border-b border-line px-5 py-4">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          {responsible ? (
            <>
              <span className="shrink-0 text-xs font-medium uppercase tracking-wider text-fg-subtle">Responsible</span>
              <span className="shrink-0">
                <ShaChip sha={responsible.sha} tone="bad" />
              </span>
              <span className="min-w-0 truncate text-sm text-fg" title={firstLine(responsible.message)}>
                {firstLine(responsible.message)}
              </span>
            </>
          ) : (
            <>
              <TriangleAlert size={15} className="text-warn" />
              <span className="text-sm font-medium text-warn">Could not attribute with confidence</span>
            </>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {responsible && <ConfidenceBar value={result.confidence} />}
          <SourceBadge fallback={result.fallback} />
        </div>
      </div>

      <div className="grid gap-px bg-line md:grid-cols-3">
        <Field label="What failed" value={result.what_failed} />
        <Field label="Why" value={result.why} />
        <Field label="Suggested fix" value={result.suggested_fix} />
      </div>

      {result.fallback && result.fallback_reason && (
        <div className="flex items-start gap-2 border-t border-line bg-warn/5 px-5 py-3 text-xs text-fg-muted">
          <TriangleAlert size={13} className="mt-0.5 shrink-0 text-warn" />
          <span>
            Deterministic scoring only. <span className="font-mono text-fg-subtle">{result.fallback_reason}</span>
          </span>
        </div>
      )}

      {result.reasoning && (
        <div className="border-t border-line">
          <button
            onClick={() => setShowReasoning((v) => !v)}
            className="flex w-full items-center gap-2 px-5 py-3 text-left text-xs font-medium text-fg-muted transition-colors hover:text-fg"
          >
            <ChevronRight size={14} className={cx("transition-transform", showReasoning && "rotate-90")} />
            <Sparkles size={13} className="text-accent" />
            Model reasoning
            <span className="ml-auto font-mono text-[11px] text-fg-subtle">{result.model}</span>
          </button>
          {showReasoning && (
            <div className="animate-fade-in px-5 pb-4 pl-12 text-sm leading-relaxed text-fg-muted">
              <RichText text={result.reasoning} />
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function Field({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="min-w-0 bg-panel px-5 py-4">
      <div className="mb-1.5 text-xs font-medium uppercase tracking-wider text-fg-subtle">{label}</div>
      <div className="text-sm leading-relaxed text-fg">{value ? <RichText text={value} /> : <span className="text-fg-subtle">—</span>}</div>
    </div>
  );
}

const FULL_SHA = /\b[0-9a-f]{40}\b/g;

/** Renders the small amount of Markdown LLM verdicts use: fenced code, inline code, and full shas. */
export function RichText({ text }: { text: string }) {
  const blocks = text.split(/```(?:[a-z]*)\n?([\s\S]*?)```/g);
  return (
    <>
      {blocks.map((block, i) =>
        i % 2 === 1 ? (
          <pre key={i} className="my-2 overflow-x-auto rounded-md border border-line bg-bg px-3 py-2 font-mono text-[12px] leading-relaxed text-fg-muted">
            {block.trim()}
          </pre>
        ) : (
          <span key={i}>{renderInline(block)}</span>
        ),
      )}
    </>
  );
}

function renderInline(text: string) {
  return text.split(/`([^`]+)`/g).map((part, i) =>
    i % 2 === 1 ? (
      <code key={i} className="rounded border border-line bg-raised px-1 py-px font-mono text-[12px] text-fg">
        {part}
      </code>
    ) : (
      part.split(FULL_SHA).flatMap((chunk, j, arr) => {
        const shas = part.match(FULL_SHA) ?? [];
        return j < arr.length - 1
          ? [chunk, <span key={`${i}-${j}`} className="font-mono text-[12px] text-fg" title={shas[j]}>{shas[j].slice(0, 7)}</span>]
          : [chunk];
      })
    ),
  );
}

export function CandidateList({ candidates, responsible }: { candidates: Candidate[]; responsible: string | null }) {
  const ranked = [...candidates].sort((a, b) => b.score - a.score);
  if (!ranked.length) {
    return <div className="rounded-xl border border-dashed border-line px-4 py-8 text-center text-sm text-fg-muted">No candidate commits.</div>;
  }
  return (
    <div className="space-y-2.5">
      {ranked.map((c, i) => (
        <CandidateCard key={c.sha} candidate={c} rank={i + 1} guilty={c.sha === responsible} delay={i * 60} />
      ))}
    </div>
  );
}

function CandidateCard({ candidate, rank, guilty, delay }: { candidate: Candidate; rank: number; guilty: boolean; delay: number }) {
  return (
    <div
      style={{ animationDelay: `${delay}ms` }}
      className={cx(
        "animate-rise relative overflow-hidden rounded-xl border bg-panel px-4 py-3.5",
        guilty ? "border-bad/40" : "border-line",
      )}
    >
      {guilty && <div className="absolute inset-y-0 left-0 w-0.5 bg-bad" />}
      <div className="flex items-start gap-4">
        <div className="tabular w-5 pt-0.5 font-mono text-xs text-fg-subtle">{rank}</div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <ShaChip sha={candidate.sha} tone={guilty ? "bad" : "default"} />
            <span className="min-w-0 truncate text-sm text-fg">{firstLine(candidate.message)}</span>
            {guilty && <Tag tone="bad">Responsible</Tag>}
          </div>
          {candidate.files.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {candidate.files.map((f) => (
                <span key={f} className="inline-flex items-center gap-1 rounded border border-line bg-bg px-1.5 py-0.5 font-mono text-[11px] text-fg-muted">
                  <FileCode2 size={11} className="text-fg-subtle" />
                  {f}
                </span>
              ))}
            </div>
          )}
          {candidate.reasons.length > 0 ? (
            <ul className="mt-2 space-y-0.5">
              {candidate.reasons.map((r) => (
                <li key={r} className="flex gap-2 text-xs text-fg-muted">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent" />
                  {r}
                </li>
              ))}
            </ul>
          ) : (
            <div className="mt-2 text-xs text-fg-subtle">No scoring signals matched</div>
          )}
        </div>
        <ScoreMeter score={candidate.score} guilty={guilty} />
      </div>
    </div>
  );
}

export function ScoreMeter({ score, guilty }: { score: number; guilty?: boolean }) {
  return (
    <div className="flex w-14 shrink-0 flex-col items-end gap-1.5">
      <div className="flex items-baseline gap-0.5">
        <span className={cx("tabular font-mono text-lg font-medium leading-none", guilty ? "text-fg" : "text-fg-muted")}>{score}</span>
        <span className="font-mono text-[11px] text-fg-subtle">/{MAX_SCORE}</span>
      </div>
      <div className="h-1 w-full overflow-hidden rounded-full bg-line">
        <div
          className={cx("h-full rounded-full transition-[width] duration-700", guilty ? "bg-bad" : "bg-fg-subtle")}
          style={{ width: `${(score / MAX_SCORE) * 100}%` }}
        />
      </div>
    </div>
  );
}

export function LogViewer({ text, title = "Distilled error", maxHeight = "max-h-[420px]" }: { text: string; title?: string; maxHeight?: string }) {
  const lines = text.replace(/^\s*\n/, "").replace(/\s+$/, "").split("\n");
  const errorCount = lines.filter((l) => ERROR_LINE.test(l)).length;
  return (
    <Card className="overflow-hidden">
      <CardHeader
        title={title}
        icon={<FileCode2 size={14} />}
        meta={
          <span className="font-mono">
            {lines.length} lines · <span className="text-bad">{errorCount} flagged</span>
          </span>
        }
      />
      <div className={cx("overflow-auto bg-bg py-2 font-mono text-[12px] leading-[1.7]", maxHeight)}>
        {lines.map((line, i) =>
          line.trim() === "---" ? (
            <div key={i} className="my-1 flex items-center gap-3 px-4 text-[11px] text-fg-subtle">
              <span className="h-px flex-1 bg-line" />
              lines omitted
              <span className="h-px flex-1 bg-line" />
            </div>
          ) : (
            <div key={i} className={cx("flex", ERROR_LINE.test(line) && "bg-bad/[0.07]")}>
              <span
                className={cx(
                  "tabular w-12 shrink-0 select-none border-r pr-3 text-right",
                  ERROR_LINE.test(line) ? "border-bad/50 text-bad/70" : "border-line text-fg-subtle/60",
                )}
              >
                {i + 1}
              </span>
              <span className={cx("whitespace-pre pl-4 pr-4", ERROR_LINE.test(line) ? "text-[#ffb4b6]" : "text-fg-muted")}>{line || " "}</span>
            </div>
          ),
        )}
      </div>
    </Card>
  );
}
