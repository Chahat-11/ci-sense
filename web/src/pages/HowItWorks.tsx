import { Brain, FileSearch, GitCompare, MessageSquare, Scale, ShieldCheck, Zap } from "lucide-react";
import { Card, PageHeader } from "../components/ui";

const STAGES = [
  { icon: Zap, name: "Trigger", line: "A failed tests run fires workflow_run; triage starts only when the run failed." },
  { icon: FileSearch, name: "Distil", line: "Download the logs, strip timestamps and cleanup noise, keep windows around errors." },
  { icon: GitCompare, name: "Candidates", line: "PR runs: base branch to failing sha. Main: every commit since the last green run." },
  { icon: Scale, name: "Score", line: "Deterministic signals: file named in the error, shared identifiers, config changes." },
  { icon: Brain, name: "LLM verdict", line: "The model picks the responsible commit or abstains; its answer must be a candidate." },
  { icon: MessageSquare, name: "Post", line: "Verdict goes to the PR that introduced the commit, with evidence and hidden data." },
];

const GUARANTEES = [
  { title: "Honest fallback", body: "If the LLM is unavailable the top-scored commit is used, and nobody is blamed when every score is zero." },
  { title: "Validated answers", body: "A verdict naming a sha outside the candidate set is rejected rather than trusted." },
  { title: "No leaked secrets", body: "Keys and tokens are scrubbed by pattern from logs and from every comment before it is posted." },
];

export default function HowItWorks() {
  return (
    <>
      <PageHeader
        title="How it works"
        description="From a red CI run to a verdict on the pull request that caused it, in six stages."
      />

      <Card className="px-6 py-8">
        <ol className="grid grid-cols-6 gap-0">
          {STAGES.map(({ icon: Icon, name, line }, i) => (
            <li key={name} className="animate-rise relative flex flex-col px-3" style={{ animationDelay: `${i * 70}ms` }}>
              <div className="relative flex items-center">
                <div className="relative z-10 flex h-11 w-11 items-center justify-center rounded-xl border border-line-strong bg-raised text-accent">
                  <Icon size={18} />
                </div>
                {i < STAGES.length - 1 && (
                  <div className="absolute left-11 right-[-12px] top-1/2 flex items-center">
                    <div className="h-px flex-1 bg-gradient-to-r from-line-strong to-line" />
                    <div className="h-0 w-0 border-y-[4px] border-l-[6px] border-y-transparent border-l-line-strong" />
                  </div>
                )}
              </div>
              <div className="mt-4 font-mono text-[11px] text-fg-subtle">0{i + 1}</div>
              <div className="mt-1 text-sm font-medium">{name}</div>
              <p className="mt-1.5 text-xs leading-relaxed text-fg-muted">{line}</p>
            </li>
          ))}
        </ol>
      </Card>

      <div className="mt-4 grid grid-cols-3 gap-4">
        {GUARANTEES.map((g) => (
          <Card key={g.title} className="px-5 py-4">
            <div className="flex items-center gap-2 text-[13px] font-medium">
              <ShieldCheck size={14} className="text-ok" />
              {g.title}
            </div>
            <p className="mt-1.5 text-xs leading-relaxed text-fg-muted">{g.body}</p>
          </Card>
        ))}
      </div>
    </>
  );
}
