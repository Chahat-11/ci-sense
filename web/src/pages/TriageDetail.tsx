import type { ReactNode } from "react";
import { Link, useParams } from "react-router";
import { ArrowRight, ChevronLeft, ExternalLink as ExternalIcon, GitBranch, GitPullRequest, MessageSquare, Play } from "lucide-react";
import { useApi } from "../api";
import type { TriageDetail } from "../types";
import { formatDateTime, prUrl, runUrl, shortSha } from "../format";
import { CandidateList, LogViewer, VerdictCard } from "../components/Verdict";
import { Card, ErrorState, ShaChip, Skeleton, SourceBadge, Tag } from "../components/ui";

export default function TriageDetailPage() {
  const { id } = useParams();
  const { data, error, loading, reload } = useApi<TriageDetail>(`/api/triages/${id}`);

  return (
    <>
      <Link to="/" className="mb-5 inline-flex items-center gap-1 text-xs text-fg-muted transition-colors hover:text-fg">
        <ChevronLeft size={14} />
        Overview
      </Link>

      {error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : loading || !data ? (
        <DetailSkeleton />
      ) : (
        <Detail triage={data} />
      )}
    </>
  );
}

function Detail({ triage: t }: { triage: TriageDetail }) {
  const r = t.result;
  return (
    <div className="space-y-6">
      <header>
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="font-mono text-sm text-fg-subtle">#{t.pr_number}</span>
          <h1 className="text-[22px] font-semibold tracking-tight">{t.pr_title ?? "Untitled pull request"}</h1>
          {t.pr_state && <Tag tone={t.pr_state === "merged" ? "accent" : t.pr_state === "open" ? "ok" : "default"}>{t.pr_state}</Tag>}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-fg-muted">
          <HeaderLink href={t.pr_url ?? prUrl(t.repo, t.pr_number)} icon={<GitPullRequest size={13} />}>
            Pull request
          </HeaderLink>
          <HeaderLink href={runUrl(t.repo, t.run_id)} icon={<Play size={13} />}>
            Run <span className="font-mono">{t.run_id}</span>
          </HeaderLink>
          <HeaderLink href={t.comment_url} icon={<MessageSquare size={13} />}>
            Triage comment
          </HeaderLink>
          <span className="text-fg-subtle">{formatDateTime(t.created_at)}</span>
          <span className="text-fg-subtle">
            {r.candidates.length} candidate{r.candidates.length === 1 ? "" : "s"}
          </span>
          <SourceBadge fallback={t.fallback} />
        </div>
      </header>

      {t.is_main_failure && <MainFailurePanel triage={t} />}

      <section>
        <SectionTitle>Verdict</SectionTitle>
        <VerdictCard result={r} />
      </section>

      <section>
        <SectionTitle meta="Ranked by deterministic score">Candidate commits</SectionTitle>
        <CandidateList candidates={r.candidates} responsible={r.responsible_commit} />
      </section>

      <section>
        <SectionTitle>Evidence</SectionTitle>
        <LogViewer text={r.distilled_error} />
      </section>
    </div>
  );
}

function MainFailurePanel({ triage: t }: { triage: TriageDetail }) {
  const r = t.result;
  return (
    <Card className="animate-rise grid gap-px overflow-hidden bg-line md:grid-cols-3">
      <div className="bg-panel px-5 py-4">
        <div className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-fg-subtle">
          <GitBranch size={12} />
          Failure on main
        </div>
        <div className="flex items-center gap-2">
          <ShaChip sha={r.last_good_sha} tone="ok" />
          <ArrowRight size={14} className="text-fg-subtle" />
          <ShaChip sha={r.head_sha} tone="bad" />
        </div>
        <div className="mt-2 text-xs text-fg-muted">
          Last green run{r.last_good_sha ? ` at ${shortSha(r.last_good_sha)}` : " not found"} → failing head
        </div>
      </div>
      <div className="bg-panel px-5 py-4">
        <div className="mb-2 text-xs font-medium uppercase tracking-wider text-fg-subtle">Attributed to</div>
        {r.guilty_pr ? (
          <a href={prUrl(t.repo, r.guilty_pr)} target="_blank" rel="noreferrer" className="group block">
            <div className="text-sm font-medium text-fg group-hover:underline">PR #{r.guilty_pr}</div>
            <div className="mt-0.5 truncate text-xs text-fg-muted">
              {r.guilty_pr === t.pr_number && t.pr_title ? t.pr_title : "Full verdict posted here"}
            </div>
          </a>
        ) : (
          <div className="text-sm text-fg-muted">No PR found for the responsible commit</div>
        )}
      </div>
      <div className="bg-panel px-5 py-4">
        <div className="mb-2 text-xs font-medium uppercase tracking-wider text-fg-subtle">“Not your fault” note</div>
        {t.notes.length ? (
          t.notes.map((n) => (
            <a key={n.comment_url} href={n.comment_url} target="_blank" rel="noreferrer" className="group block">
              <div className="text-sm font-medium text-fg group-hover:underline">PR #{n.pr_number}</div>
              <div className="mt-0.5 truncate text-xs text-fg-muted">{n.pr_title}</div>
            </a>
          ))
        ) : (
          <div className="text-sm text-fg-muted">Not needed: the failing merge came from the same PR</div>
        )}
      </div>
    </Card>
  );
}

function HeaderLink({ href, icon, children }: { href: string; icon: ReactNode; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 transition-colors hover:text-fg">
      <span className="text-fg-subtle">{icon}</span>
      {children}
      <ExternalIcon size={11} className="text-fg-subtle" />
    </a>
  );
}

export function SectionTitle({ children, meta }: { children: ReactNode; meta?: string }) {
  return (
    <div className="mb-3 flex items-baseline justify-between">
      <h2 className="text-[13px] font-medium text-fg">{children}</h2>
      {meta && <span className="text-xs text-fg-subtle">{meta}</span>}
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="space-y-6">
      <div>
        <Skeleton className="h-6 w-96" />
        <Skeleton className="mt-3 h-3.5 w-[28rem]" />
      </div>
      <Card className="p-5">
        <Skeleton className="h-5 w-1/2" />
        <div className="mt-5 grid grid-cols-3 gap-6">
          {[0, 1, 2].map((i) => (
            <div key={i} className="space-y-2">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-3.5 w-full" />
              <Skeleton className="h-3.5 w-4/5" />
            </div>
          ))}
        </div>
      </Card>
      {[0, 1].map((i) => (
        <Card key={i} className="p-4">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="mt-3 h-3 w-1/3" />
        </Card>
      ))}
    </div>
  );
}
