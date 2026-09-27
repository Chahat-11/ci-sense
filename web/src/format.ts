export const shortSha = (sha: string | null | undefined) => (sha ? sha.slice(0, 7) : "—");

export const firstLine = (text: string | null | undefined) => (text ?? "").split("\n")[0];

export function pct(value: number | null | undefined, digits = 0) {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function timeAgo(iso: string) {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 45) return "just now";
  if (seconds < 3600) return `${Math.max(1, Math.round(seconds / 60))}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  if (seconds < 604800) return `${Math.round(seconds / 86400)}d ago`;
  return `${Math.round(seconds / 604800)}w ago`;
}

export function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDuration(ms: number | null | undefined) {
  if (ms === null || ms === undefined) return "";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

export function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export const ERROR_LINE = /(Error|Traceback|FAILED|assert|Exception|##\[error\])/i;

export const commitUrl = (repo: string, sha: string) => `https://github.com/${repo}/commit/${sha}`;
export const prUrl = (repo: string, pr: number) => `https://github.com/${repo}/pull/${pr}`;
export const runUrl = (repo: string, run: number) => `https://github.com/${repo}/actions/runs/${run}`;

export const CATEGORY_LABELS: Record<string, string> = {
  import_error: "Import error",
  logic_bug: "Logic bug",
  test_bug: "Test bug",
  syntax_error: "Syntax error",
  dependency: "Dependency",
  multi_commit_logic: "Multi-commit · logic",
  multi_commit_rename: "Multi-commit · rename",
  multi_commit_behavior: "Multi-commit · behaviour",
};
