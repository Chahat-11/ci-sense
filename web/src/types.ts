export interface Candidate {
  sha: string;
  message: string;
  files: string[];
  score: number;
  reasons: string[];
}

export interface TriageResult {
  run_id: number;
  pr_number: number | null;
  guilty_pr: number | null;
  head_sha: string;
  last_good_sha: string | null;
  candidates: Candidate[];
  what_failed?: string | null;
  why?: string | null;
  responsible_commit: string | null;
  confidence: number | null;
  suggested_fix?: string | null;
  reasoning?: string | null;
  fallback: boolean;
  fallback_reason: string | null;
  model: string;
  timestamp: string;
  distilled_error: string;
}

export interface TriageSummary {
  id: number;
  pr_number: number;
  pr_title: string | null;
  pr_state: string | null;
  pr_url: string | null;
  comment_url: string;
  created_at: string;
  run_id: number;
  run_url: string;
  head_sha: string;
  is_main_failure: boolean;
  responsible_commit: string | null;
  responsible_message: string | null;
  confidence: number | null;
  fallback: boolean;
  what_failed: string | null;
  candidate_count: number;
}

export interface TriageNote {
  pr_number: number;
  pr_title: string | null;
  comment_url: string;
}

export interface TriageDetail extends TriageSummary {
  result: TriageResult;
  notes: TriageNote[];
  repo: string;
}

export interface Stats {
  triaged: number;
  attributed: number;
  abstained: number;
  llm: number;
  fallback: number;
  avg_confidence: number | null;
  per_day: { date: string; count: number }[];
}

export interface FailedRun {
  id: number;
  branch: string;
  event: string;
  head_sha: string;
  commit_message: string;
  created_at: string;
  url: string;
  pr_number: number | null;
  pr_title: string | null;
  triaged: boolean;
}

export type CaseResult = "correct" | "wrong" | "abstained" | "pending";

export interface EvalCase {
  case: string;
  name: string | null;
  category: string;
  description: string | null;
  pr_number: number;
  expected_sha: string;
  expected_message: string | null;
  verdict_sha: string | null;
  confidence: number | null;
  source: "llm" | "fallback" | null;
  result: CaseResult;
  deterministic_sha: string | null;
  deterministic_result: CaseResult | null;
  scores: { sha: string; score: number; reasons: string[] }[];
  commits: { sha: string; message: string; guilty: boolean }[];
  triage_id: number | null;
}

export interface Evaluation {
  summary: {
    cases: number;
    completed: number;
    accuracy: number | null;
    counts: Record<CaseResult, number>;
    llm: number;
    fallback: number;
  };
  cases: EvalCase[];
  accuracy: { llm: number | null; deterministic: number | null };
}

export interface Meta {
  repo: string;
  model: string;
  llm_configured: boolean;
}

export type StageName = "fetching logs" | "distilling" | "finding candidates" | "scoring" | "LLM verdict" | "posting";

export type StreamEvent =
  | { type: "started"; run_id: number; stages: StageName[] }
  | { type: "stage"; stage: StageName; status: "running" }
  | { type: "stage"; stage: StageName; status: "done"; duration_ms: number; preview: Record<string, unknown> | null }
  | { type: "result"; result: TriageResult; comment: string; run_url: string; duration_ms: number }
  | { type: "error"; stage: StageName | null; message: string };
