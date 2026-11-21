import { Brain, FileSearch, GitCompare, MessageSquare, Scale, ShieldCheck, Zap } from "lucide-react";
import { Card, PageHeader } from "../components/ui";

const STAGES = [
  { icon: Zap, name: "Trigger", line: "A test run fails on GitHub, and CI-Sense wakes up. Passing runs are ignored." },
  { icon: FileSearch, name: "Read logs", line: "It downloads the logs and trims the noise, keeping just the lines around each error." },
  { icon: GitCompare, name: "Suspects", line: "It lists the commits that could be to blame: everything new since the last passing run." },
  { icon: Scale, name: "Score", line: "Each suspect gets a score from clear clues, like a file named in the error." },
  { icon: Brain, name: "AI verdict", line: "The AI picks the most likely commit, or says it is not sure. It can only choose from the suspects." },
  { icon: MessageSquare, name: "Post", line: "The verdict is posted on the pull request that introduced the commit, with the evidence." },
];

const GUARANTEES = [
  { title: "Honest fallback", body: "If the AI is unavailable, the highest-scoring commit is used. If nothing scores, nobody is blamed." },
  { title: "Validated answers", body: "An answer naming a commit that was never a suspect is thrown out, not trusted." },
  { title: "No leaked secrets", body: "Keys and tokens are scrubbed from the logs and from every comment before it is posted." },
];

export default function HowItWorks() {
  return (
    <>
      <PageHeader
        title="How it works"
        description="From a failed test run to a verdict on the pull request that caused it, in six simple steps."
      />

      <Card className="px-6 py-8">
        <ol className="grid gap-6 sm:grid-cols-2 lg:grid-cols-6 lg:gap-0">
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
              <div className="mt-4 text-xs font-semibold text-accent">Step {i + 1}</div>
              <div className="mt-1 text-sm font-medium">{name}</div>
              <p className="mt-1.5 text-xs leading-relaxed text-fg-muted">{line}</p>
            </li>
          ))}
        </ol>
      </Card>

      <div className="mt-4 grid gap-4 md:grid-cols-3">
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
