import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { ArrowLeft, ArrowRight, FlaskConical, GitPullRequest, LayoutDashboard, Radio, Sparkles, X } from "lucide-react";
import { cx } from "./ui";

const KEY = "cisense.tour.done";

const STEPS = [
  {
    icon: Sparkles,
    title: "Welcome to CI-Sense",
    body: "When your tests fail, CI-Sense works out which commit most likely broke them and tells you on the pull request. This short tour shows you around. It takes under a minute.",
    to: "/",
  },
  {
    icon: LayoutDashboard,
    title: "Overview: everything it has found",
    body: "Each row is one failed test run. You can see the pull request, the commit it blames and how sure it is. Use the search box and the filters to find a specific one, then click a row for the full story.",
    to: "/",
  },
  {
    icon: Radio,
    title: "Live triage: watch it think",
    body: "Pick a failed run and watch CI-Sense read the logs, shortlist suspects and reach a verdict, step by step. It's a safe preview, so nothing is posted to GitHub.",
    to: "/live",
  },
  {
    icon: FlaskConical,
    title: "Evaluation: can you trust it?",
    body: "We planted known bugs and checked whether CI-Sense blamed the right commit. This page shows the scores, and how much the AI step adds over simple rules.",
    to: "/evaluation",
  },
  {
    icon: GitPullRequest,
    title: "You're all set",
    body: "You can reopen this tour any time from “Take the tour” in the sidebar. The “How it works” page explains the whole pipeline in plain steps.",
    to: "/how-it-works",
  },
];

function isDone() {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

/** Controls for the guided tour. It opens automatically on a first visit. */
export function useTour() {
  const [open, setOpen] = useState(() => !isDone());
  const start = useCallback(() => setOpen(true), []);
  const close = useCallback(() => {
    try {
      localStorage.setItem(KEY, "1");
    } catch {
      /* private mode: just close */
    }
    setOpen(false);
  }, []);
  return { open, start, close };
}

export default function Tour({ onClose }: { onClose: () => void }) {
  const [i, setI] = useState(0);
  const navigate = useNavigate();
  const step = STEPS[i];
  const last = i === STEPS.length - 1;
  const Icon = step.icon;

  const go = useCallback(
    (n: number) => {
      setI(n);
      navigate(STEPS[n].to);
    },
    [navigate],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") {
        if (i < STEPS.length - 1) go(i + 1);
        else onClose();
      }
      if (e.key === "ArrowLeft" && i > 0) go(i - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [i, go, onClose]);

  return (
    <div className="animate-fade-in fixed inset-0 z-50 flex items-end justify-center bg-black/45 p-4 sm:items-center" role="dialog" aria-modal="true" aria-label="Product tour">
      <div className="animate-rise w-full max-w-md overflow-hidden rounded-2xl border border-line-strong bg-panel shadow-2xl shadow-black/15">
        <div className="flex items-center justify-between px-5 pt-4">
          <span className="text-xs font-medium text-fg-subtle">
            Step {i + 1} of {STEPS.length}
          </span>
          <button
            onClick={onClose}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-fg-muted transition-colors hover:bg-raised hover:text-fg"
          >
            Skip tour
            <X size={13} />
          </button>
        </div>

        <div className="px-6 pb-2 pt-5" key={i}>
          <div className="animate-rise mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-soft text-accent">
            <Icon size={22} />
          </div>
          <h2 className="animate-rise text-xl font-semibold tracking-tight">{step.title}</h2>
          <p className="animate-rise mt-2 text-[15px] leading-relaxed text-fg-muted">{step.body}</p>
        </div>

        <div className="flex items-center justify-between px-5 pb-5 pt-4">
          <div className="flex gap-1.5" aria-hidden>
            {STEPS.map((_, n) => (
              <span key={n} className={cx("h-1.5 rounded-full transition-all", n === i ? "w-5 bg-accent" : "w-1.5 bg-line-strong")} />
            ))}
          </div>
          <div className="flex items-center gap-2">
            {i === 0 && (
              <button
                onClick={onClose}
                className="rounded-lg border border-line-strong px-3 py-2 text-sm font-medium text-fg transition-colors hover:bg-raised"
              >
                Skip for now
              </button>
            )}
            {i > 0 && (
              <button
                onClick={() => go(i - 1)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong px-3 py-2 text-sm font-medium text-fg transition-colors hover:bg-raised"
              >
                <ArrowLeft size={14} />
                Back
              </button>
            )}
            <button
              onClick={() => (last ? onClose() : go(i + 1))}
              className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg transition-opacity hover:opacity-90"
            >
              {i === 0 ? "Start tour" : last ? "Get started" : "Next"}
              {!last && <ArrowRight size={14} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
