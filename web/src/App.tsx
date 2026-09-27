import { BrowserRouter, NavLink, Outlet, Route, Routes } from "react-router";
import { FlaskConical, LayoutDashboard, Radio, Workflow } from "lucide-react";
import { useApi } from "./api";
import type { Meta } from "./types";
import { MetaContext, cx } from "./components/ui";
import Overview from "./pages/Overview";
import TriageDetailPage from "./pages/TriageDetail";
import LiveTriage from "./pages/LiveTriage";
import EvaluationPage from "./pages/Evaluation";
import HowItWorks from "./pages/HowItWorks";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/live", label: "Live triage", icon: Radio, end: false },
  { to: "/evaluation", label: "Evaluation", icon: FlaskConical, end: false },
  { to: "/how-it-works", label: "How it works", icon: Workflow, end: false },
];

export function Logo({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="7" fill="#7c83ff" />
      <path d="M9 17h4l2.5-6 3 11 2.5-5H23" fill="none" stroke="#09090b" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Layout() {
  const meta = useApi<Meta>("/api/meta");
  return (
    <MetaContext.Provider value={meta.data}>
      <div className="flex min-h-screen">
        <aside className="sticky top-0 flex h-screen w-60 shrink-0 flex-col border-r border-line bg-bg px-3 py-5">
          <div className="mb-7 flex items-center gap-2.5 px-2">
            <Logo />
            <span className="text-[15px] font-semibold tracking-tight">CI-Sense</span>
          </div>
          <nav className="space-y-0.5">
            {NAV.map(({ to, label, icon: Icon, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  cx(
                    "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] font-medium transition-colors",
                    isActive ? "bg-raised text-fg" : "text-fg-muted hover:bg-panel hover:text-fg",
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <Icon size={16} className={isActive ? "text-accent" : "text-fg-subtle"} />
                    {label}
                  </>
                )}
              </NavLink>
            ))}
          </nav>

          <div className="mt-auto space-y-2.5 rounded-lg border border-line bg-panel px-3 py-3 text-xs">
            <div className="flex items-center gap-2">
              <span
                className={cx(
                  "h-1.5 w-1.5 rounded-full",
                  meta.error ? "bg-bad" : meta.data ? "bg-ok shadow-[0_0_8px] shadow-ok/60" : "bg-fg-subtle",
                )}
              />
              <span className="text-fg-muted">{meta.error ? "API unreachable" : meta.data ? "API connected" : "Connecting…"}</span>
            </div>
            {meta.data && (
              <>
                <div className="truncate font-mono text-[11px] text-fg-subtle" title={meta.data.repo}>
                  {meta.data.repo}
                </div>
                <div className="flex items-center justify-between gap-2 font-mono text-[11px] text-fg-subtle">
                  <span className="truncate" title={meta.data.model}>
                    {meta.data.model}
                  </span>
                  {!meta.data.llm_configured && <span className="text-warn">no key</span>}
                </div>
              </>
            )}
          </div>
        </aside>

        <main className="min-w-0 flex-1">
          <div className="mx-auto max-w-[1180px] px-10 py-9">
            <Outlet />
          </div>
        </main>
      </div>
    </MetaContext.Provider>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Overview />} />
          <Route path="triages/:id" element={<TriageDetailPage />} />
          <Route path="live" element={<LiveTriage />} />
          <Route path="evaluation" element={<EvaluationPage />} />
          <Route path="how-it-works" element={<HowItWorks />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

function NotFound() {
  return (
    <div className="py-24 text-center">
      <div className="font-mono text-sm text-fg-subtle">404</div>
      <div className="mt-2 text-lg font-medium">Page not found</div>
    </div>
  );
}
