import { createContext, useContext, type CSSProperties, type ReactNode } from "react";
import { Check, CircleDashed, Clock, GitCommitHorizontal, Minus, RotateCw, TriangleAlert, X } from "lucide-react";
import type { CaseResult, Meta } from "../types";
import { commitUrl, pct, shortSha } from "../format";

export const MetaContext = createContext<Meta | null>(null);
export const useMeta = () => useContext(MetaContext);

export function cx(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

export function Card({ children, className, style }: { children: ReactNode; className?: string; style?: CSSProperties }) {
  return (
    <div className={cx("rounded-xl border border-line bg-panel", className)} style={style}>
      {children}
    </div>
  );
}

export function CardHeader({ title, meta, icon }: { title: string; meta?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
      <div className="flex items-center gap-2 text-[13px] font-medium text-fg">
        {icon && <span className="text-fg-subtle">{icon}</span>}
        {title}
      </div>
      {meta && <div className="text-xs text-fg-subtle">{meta}</div>}
    </div>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight text-fg">{title}</h1>
        {description && <p className="mt-1.5 max-w-2xl text-sm text-fg-muted">{description}</p>}
      </div>
      {actions}
    </div>
  );
}

export function ShaChip({
  sha,
  tone = "default",
  link = true,
}: {
  sha: string | null | undefined;
  tone?: "default" | "bad" | "ok";
  /** Set false when the chip sits inside another link or clickable row. */
  link?: boolean;
}) {
  const meta = useMeta();
  if (!sha) {
    return <span className="font-mono text-xs text-fg-subtle">—</span>;
  }
  const toneClass =
    tone === "bad"
      ? "border-bad/30 bg-bad/10 text-bad"
      : tone === "ok"
        ? "border-ok/30 bg-ok/10 text-ok"
        : "border-line-strong bg-raised text-fg";
  const chip = (
    <span className={cx("inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 font-mono text-xs", toneClass)}>
      <GitCommitHorizontal size={12} className="opacity-60" />
      {shortSha(sha)}
    </span>
  );
  if (!meta || !link) return chip;
  return (
    <a
      href={commitUrl(meta.repo, sha)}
      target="_blank"
      rel="noreferrer"
      onClick={(e) => e.stopPropagation()}
      className="transition-opacity hover:opacity-80"
      title={sha}
    >
      {chip}
    </a>
  );
}

export function confidenceTone(value: number | null | undefined) {
  if (value === null || value === undefined) return "subtle";
  if (value >= 0.8) return "ok";
  if (value >= 0.5) return "warn";
  return "bad";
}

export function ConfidenceBar({ value, width = "w-20" }: { value: number | null | undefined; width?: string }) {
  const tone = confidenceTone(value);
  const fill = { ok: "bg-ok", warn: "bg-warn", bad: "bg-bad", subtle: "bg-fg-subtle" }[tone];
  return (
    <div className="flex items-center gap-2">
      <div className={cx("h-1.5 overflow-hidden rounded-full bg-line", width)}>
        <div className={cx("h-full rounded-full transition-[width] duration-700", fill)} style={{ width: `${(value ?? 0) * 100}%` }} />
      </div>
      <span className="tabular w-9 text-right font-mono text-xs text-fg-muted">{pct(value)}</span>
    </div>
  );
}

export function SourceBadge({ fallback }: { fallback: boolean }) {
  return fallback ? (
    <span className="inline-flex items-center rounded-md border border-warn/25 bg-warn/10 px-1.5 py-0.5 text-[11px] font-medium text-warn">
      Fallback
    </span>
  ) : (
    <span className="inline-flex items-center rounded-md border border-accent/25 bg-accent-soft px-1.5 py-0.5 text-[11px] font-medium text-accent">
      LLM
    </span>
  );
}

export function Tag({ children, tone = "default" }: { children: ReactNode; tone?: "default" | "accent" | "warn" | "bad" | "ok" }) {
  const tones = {
    default: "border-line-strong bg-raised text-fg-muted",
    accent: "border-accent/25 bg-accent-soft text-accent",
    warn: "border-warn/25 bg-warn/10 text-warn",
    bad: "border-bad/25 bg-bad/10 text-bad",
    ok: "border-ok/25 bg-ok/10 text-ok",
  };
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium", tones[tone])}>
      {children}
    </span>
  );
}

export function ResultBadge({ result }: { result: CaseResult | null }) {
  if (!result) return <span className="text-xs text-fg-subtle">—</span>;
  const map = {
    correct: { icon: <Check size={12} strokeWidth={2.5} />, label: "Correct", cls: "text-ok bg-ok/10 border-ok/25" },
    wrong: { icon: <X size={12} strokeWidth={2.5} />, label: "Wrong", cls: "text-bad bg-bad/10 border-bad/25" },
    abstained: { icon: <Minus size={12} strokeWidth={2.5} />, label: "Abstained", cls: "text-warn bg-warn/10 border-warn/25" },
    pending: { icon: <Clock size={12} />, label: "Pending", cls: "text-fg-muted bg-raised border-line-strong" },
  }[result];
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium", map.cls)}>
      {map.icon}
      {map.label}
    </span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("animate-pulse rounded-md bg-raised", className)} />;
}

export function EmptyState({ title, description, icon }: { title: string; description?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full border border-line bg-raised text-fg-subtle">
        {icon ?? <CircleDashed size={18} />}
      </div>
      <div className="text-sm font-medium text-fg">{title}</div>
      {description && <div className="mt-1 max-w-sm text-sm text-fg-muted">{description}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-bad/25 bg-bad/5 px-4 py-3.5">
      <TriangleAlert size={16} className="mt-0.5 shrink-0 text-bad" />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium text-fg">Something went wrong</div>
        <div className="mt-0.5 break-words text-sm text-fg-muted">{message}</div>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-line-strong bg-raised px-2.5 py-1.5 text-xs font-medium text-fg transition-colors hover:border-fg-subtle"
        >
          <RotateCw size={12} />
          Retry
        </button>
      )}
    </div>
  );
}

export function ExternalLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 text-fg-muted underline decoration-line-strong underline-offset-4 transition-colors hover:text-fg hover:decoration-fg-subtle"
    >
      {children}
    </a>
  );
}
