import { BrowserRouter, NavLink, Outlet, Route, Routes } from "react-router";
import { useEffect, useState } from "react";
import { CircleHelp, FlaskConical, LayoutDashboard, Moon, Radio, Sun, Workflow } from "lucide-react";
import { useApi } from "./api";
import type { Meta } from "./types";
import { MetaContext, cx } from "./components/ui";
import Tour, { useTour } from "./components/Tour";
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
      <rect width="32" height="32" rx="7" fill="var(--color-accent)" />
      <path d="M9 17h4l2.5-6 3 11 2.5-5H23" fill="none" stroke="var(--color-bg)" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function useTheme() {
  const [theme, setTheme] = useState<"light" | "dark">(() => (document.documentElement.dataset.theme === "dark" ? "dark" : "light"));
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("cisense.theme", theme);
    } catch {
      /* ignore */
    }
  }, [theme]);
  return { theme, toggle: () => setTheme((t) => (t === "dark" ? "light" : "dark")) };
}

function MobileBar() {
  return (
    <header className="sticky top-0 z-30 flex items-center gap-1 overflow-x-auto border-b border-line bg-panel px-3 py-2 md:hidden">
      <Logo size={20} />
      {NAV.map(({ to, label, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            cx("shrink-0 rounded-md px-2.5 py-1.5 text-[13px] font-medium", isActive ? "bg-raised text-fg" : "text-fg-muted")
          }
        >
          {label}
        </NavLink>
      ))}
    </header>
  );
}

function Layout() {
  const meta = useApi<Meta>("/api/meta");
  const tour = useTour();
  const { theme, toggle } = useTheme();
  return (
    <MetaContext.Provider value={meta.data}>
      {tour.open && <Tour onClose={tour.close} />}
      <div className="flex min-h-screen flex-col md:flex-row">
        <MobileBar />
        <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-line bg-panel px-3 py-5 md:flex">
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

          <div className="mt-auto mb-3 space-y-0.5">
            <button
              onClick={tour.start}
              className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] font-medium text-fg-muted transition-colors hover:bg-raised hover:text-fg"
            >
              <CircleHelp size={16} className="text-fg-subtle" />
              Take the tour
            </button>
            <button
              onClick={toggle}
              className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] font-medium text-fg-muted transition-colors hover:bg-raised hover:text-fg"
            >
              {theme === "dark" ? <Sun size={16} className="text-fg-subtle" /> : <Moon size={16} className="text-fg-subtle" />}
              {theme === "dark" ? "Light mode" : "Dark mode"}
            </button>
          </div>

          <div className="space-y-2.5 rounded-lg border border-line bg-bg px-3 py-3 text-xs">
            <div className="flex items-center gap-2">
              <span
                className={cx(
                  "h-1.5 w-1.5 rounded-full",
                  meta.error ? "bg-bad" : meta.data ? "bg-ok" : "bg-fg-subtle",
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
          <div className="mx-auto max-w-[1180px] px-4 py-6 md:px-10 md:py-9">
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
