import { useMemo, useState } from "react";
import { Link } from "react-router";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Activity, ChevronRight, GitBranch, Inbox, Search } from "lucide-react";
import { useApi } from "../api";
import type { Stats, TriageSummary } from "../types";
import { pct, timeAgo } from "../format";
import {
  cx,
  Card,
  CardHeader,
  ConfidenceBar,
  EmptyState,
  ErrorState,
  PageHeader,
  ShaChip,
  Skeleton,
  SourceBadge,
  Tag,
  useMeta,
} from "../components/ui";

export default function Overview() {
  const meta = useMeta();
  const stats = useApi<Stats>("/api/stats");
  const triages = useApi<TriageSummary[]>("/api/triages");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "blamed" | "unsure">("all");

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (triages.data ?? []).filter((t) => {
      if (filter === "blamed" && !t.responsible_commit) return false;
      if (filter === "unsure" && t.responsible_commit) return false;
      if (!q) return true;
      return [t.pr_title, t.what_failed, t.responsible_commit, `#${t.pr_number}`].some((v) => v?.toLowerCase().includes(q));
    });
  }, [triages.data, query, filter]);

  return (
    <>
      <PageHeader
        title="Overview"
        description={
          <>
            Every failed test run CI-Sense has looked at{meta ? <> in <span className="font-mono text-fg">{meta.repo}</span></> : null}, and the
            commit it thinks caused it.
          </>
        }
      />

      {stats.error ? (
        <ErrorState message={stats.error} onRetry={stats.reload} />
      ) : (
        <StatCards stats={stats.data} />
      )}

      <Card className="mt-4">
        <CardHeader title="Triages over time" icon={<Activity size={14} />} meta="Last 14 days" />
        <div className="h-[168px] px-2 pb-2 pt-4">
          {stats.error ? (
            <div className="flex h-full items-center justify-center text-xs text-fg-subtle">Chart unavailable</div>
          ) : stats.loading && !stats.data ? (
            <Skeleton className="mx-3 h-[130px]" />
          ) : stats.data ? (
            <TriagesChart data={stats.data.per_day} />
          ) : null}
        </div>
      </Card>

      <Card className="mt-4">
        <CardHeader
          title="Recent triages"
          meta={triages.data ? `${shown.length} of ${triages.data.length}` : undefined}
        />
        {triages.data && triages.data.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
            <label className="relative min-w-[200px] flex-1">
              <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-fg-subtle" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search by pull request, error or commit"
                className="w-full rounded-lg border border-line-strong bg-bg py-1.5 pl-8 pr-3 text-sm text-fg outline-none transition-colors placeholder:text-fg-subtle focus:border-accent"
              />
            </label>
            <div className="flex gap-1">
              {([
                ["all", "All"],
                ["blamed", "Commit found"],
                ["unsure", "Not sure"],
              ] as const).map(([k, label]) => (
                <button
                  key={k}
                  onClick={() => setFilter(k)}
                  className={cx(
                    "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                    filter === k ? "border-accent bg-accent-soft text-accent" : "border-line-strong text-fg-muted hover:bg-raised",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        )}
        {triages.error ? (
          <div className="p-4">
            <ErrorState message={triages.error} onRetry={triages.reload} />
          </div>
        ) : triages.loading && !triages.data ? (
          <FeedSkeleton />
        ) : triages.data && triages.data.length === 0 ? (
          <EmptyState
            icon={<Inbox size={18} />}
            title="No triages yet"
            description="When a test run fails, CI-Sense posts a verdict on the PR and it will appear here."
          />
        ) : (
          <div className="overflow-x-auto">
            <div className="min-w-[720px]">
              <div className="grid grid-cols-[minmax(0,1fr)_104px_132px_72px_72px_16px] gap-4 border-b border-line px-4 py-2 text-xs font-medium text-fg-subtle">
                <span>Pull request</span>
                <span>Suspect commit</span>
                <span>How sure</span>
                <span>Made by</span>
                <span className="text-right">When</span>
                <span />
              </div>
              {shown.length === 0 ? (
                <EmptyState icon={<Search size={18} />} title="Nothing matches" description="Try a different search or filter." />
              ) : (
                shown.map((t, i) => <FeedRow key={t.id} triage={t} index={i} />)
              )}
            </div>
          </div>
        )}
      </Card>
    </>
  );
}

function StatCards({ stats }: { stats: Stats | null }) {
  const cards = stats
    ? [
        { label: "Runs checked", value: String(stats.triaged), sub: "failed runs analysed" },
        { label: "Culprit found", value: String(stats.attributed), sub: `${pct(stats.triaged ? stats.attributed / stats.triaged : null)} of triages` },
        { label: "Not sure", value: String(stats.abstained), sub: "no confident culprit" },
        { label: "AI-assisted", value: pct(stats.triaged ? stats.llm / stats.triaged : null), sub: `${stats.fallback} fallback verdicts` },
        { label: "Average certainty", value: pct(stats.avg_confidence), sub: "across LLM verdicts" },
      ]
    : null;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {cards
        ? cards.map((c, i) => (
            <Card key={c.label} className="animate-rise px-4 py-4" style={{ animationDelay: `${i * 40}ms` }}>
              <div className="text-xs font-medium text-fg-muted">{c.label}</div>
              <div className="tabular mt-2 text-[28px] font-bold leading-none tracking-tight">{c.value}</div>
              <div className="mt-2 text-xs text-fg-subtle">{c.sub}</div>
            </Card>
          ))
        : Array.from({ length: 5 }, (_, i) => (
            <Card key={i} className="px-4 py-4">
              <Skeleton className="h-3 w-16" />
              <Skeleton className="mt-3 h-6 w-12" />
              <Skeleton className="mt-3 h-3 w-24" />
            </Card>
          ))}
    </div>
  );
}

function TriagesChart({ data }: { data: Stats["per_day"] }) {
  const rows = data.map((d) => ({
    ...d,
    label: new Date(`${d.date}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
  }));
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: 0 }} barCategoryGap="28%">
        <XAxis dataKey="label" tick={{ fill: "var(--color-fg-subtle)", fontSize: 11 }} axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={24} />
        <YAxis allowDecimals={false} tick={{ fill: "var(--color-fg-subtle)", fontSize: 11 }} axisLine={false} tickLine={false} width={28} />
        <Tooltip
          cursor={{ fill: "var(--color-raised)" }}
          contentStyle={{ background: "var(--color-raised)", border: "1px solid var(--color-line-strong)", borderRadius: 8, fontSize: 12 }}
          labelStyle={{ color: "var(--color-fg-muted)" }}
          itemStyle={{ color: "var(--color-fg)" }}
          formatter={(v) => [v, "Triages"]}
        />
        <Bar dataKey="count" fill="var(--color-accent)" radius={[3, 3, 0, 0]} maxBarSize={28} animationDuration={600} background={{ fill: "var(--color-raised)", radius: 3 }} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function FeedRow({ triage: t, index }: { triage: TriageSummary; index: number }) {
  return (
    <Link
      to={`/triages/${t.id}`}
      style={{ animationDelay: `${Math.min(index, 12) * 30}ms` }}
      className="animate-rise group grid grid-cols-[minmax(0,1fr)_104px_132px_72px_72px_16px] items-center gap-4 border-b border-line px-4 py-3 transition-colors last:border-b-0 hover:bg-raised/60"
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs text-fg-subtle">#{t.pr_number}</span>
          <span className="truncate text-sm font-medium text-fg">{t.pr_title ?? "Untitled pull request"}</span>
          {t.is_main_failure && (
            <Tag>
              <GitBranch size={11} />
              main
            </Tag>
          )}
        </div>
        <div className="mt-0.5 truncate text-xs text-fg-muted">{t.what_failed ?? "—"}</div>
      </div>
      <div>{t.responsible_commit ? <ShaChip sha={t.responsible_commit} tone="bad" link={false} /> : <Tag tone="warn">None</Tag>}</div>
      <ConfidenceBar value={t.confidence} width="w-16" />
      <div>
        <SourceBadge fallback={t.fallback} />
      </div>
      <div className="text-right text-xs text-fg-subtle" title={t.created_at}>
        {timeAgo(t.created_at)}
      </div>
      <ChevronRight size={14} className="text-fg-subtle transition-transform group-hover:translate-x-0.5 group-hover:text-fg-muted" />
    </Link>
  );
}

function FeedSkeleton() {
  return (
    <div>
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} className="flex items-center gap-4 border-b border-line px-4 py-3.5 last:border-b-0">
          <div className="flex-1 space-y-2">
            <Skeleton className="h-3.5 w-2/5" />
            <Skeleton className="h-3 w-3/5" />
          </div>
          <Skeleton className="h-5 w-20" />
          <Skeleton className="h-2 w-24" />
          <Skeleton className="h-5 w-12" />
        </div>
      ))}
    </div>
  );
}
