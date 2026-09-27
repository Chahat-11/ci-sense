import { Link } from "react-router";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Activity, ChevronRight, GitBranch, Inbox } from "lucide-react";
import { useApi } from "../api";
import type { Stats, TriageSummary } from "../types";
import { pct, timeAgo } from "../format";
import {
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

  return (
    <>
      <PageHeader
        title="Overview"
        description={
          <>
            Every CI failure CI-Sense has triaged{meta ? <> in <span className="font-mono text-fg">{meta.repo}</span></> : null}, read
            from the structured data attached to its PR comments.
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
          meta={triages.data ? `${triages.data.length} verdicts` : undefined}
        />
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
            description="When a tests run fails, CI-Sense posts a verdict on the PR and it will appear here."
          />
        ) : (
          <div>
            <div className="grid grid-cols-[minmax(0,1fr)_104px_132px_72px_72px_16px] gap-4 border-b border-line px-4 py-2 text-[11px] font-medium uppercase tracking-wider text-fg-subtle">
              <span>Pull request</span>
              <span>Commit</span>
              <span>Confidence</span>
              <span>Source</span>
              <span className="text-right">When</span>
              <span />
            </div>
            {triages.data?.map((t, i) => <FeedRow key={t.id} triage={t} index={i} />)}
          </div>
        )}
      </Card>
    </>
  );
}

function StatCards({ stats }: { stats: Stats | null }) {
  const cards = stats
    ? [
        { label: "Triaged", value: String(stats.triaged), sub: "failed runs analysed" },
        { label: "Attributed", value: String(stats.attributed), sub: `${pct(stats.triaged ? stats.attributed / stats.triaged : null)} of triages` },
        { label: "Abstained", value: String(stats.abstained), sub: "no confident culprit" },
        { label: "LLM share", value: pct(stats.triaged ? stats.llm / stats.triaged : null), sub: `${stats.fallback} fallback verdicts` },
        { label: "Avg confidence", value: pct(stats.avg_confidence), sub: "across LLM verdicts" },
      ]
    : null;
  return (
    <div className="grid grid-cols-5 gap-3">
      {cards
        ? cards.map((c, i) => (
            <Card key={c.label} className="animate-rise px-4 py-4" style={{ animationDelay: `${i * 40}ms` }}>
              <div className="text-xs font-medium text-fg-muted">{c.label}</div>
              <div className="tabular mt-2 text-[26px] font-semibold leading-none tracking-tight">{c.value}</div>
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
        <XAxis dataKey="label" tick={{ fill: "#6c6c78", fontSize: 11 }} axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={24} />
        <YAxis allowDecimals={false} tick={{ fill: "#6c6c78", fontSize: 11 }} axisLine={false} tickLine={false} width={28} />
        <Tooltip
          cursor={{ fill: "#15151a" }}
          contentStyle={{ background: "#15151a", border: "1px solid #2c2c35", borderRadius: 8, fontSize: 12 }}
          labelStyle={{ color: "#a1a1ad" }}
          itemStyle={{ color: "#ececf1" }}
          formatter={(v) => [v, "Triages"]}
        />
        <Bar dataKey="count" fill="#7c83ff" radius={[3, 3, 0, 0]} maxBarSize={28} animationDuration={600} background={{ fill: "#111115", radius: 3 }} />
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
