export type RunState =
  | "queued"
  | "parsing"
  | "analyzing"
  | "retrieving"
  | "reviewing"
  | "writing"
  | "completed"
  | "failed";

export interface CaseFacts {
  case_type: string;
  parties: string[];
  key_facts: string[];
  claims: string[];
  dispute_focuses: string[];
  confidence: number | null;
  missing_information: string[];
  questions_for_user: string[];
}

export interface NodeTrace {
  node: string;
  status: string;
  duration_ms: number;
  action_summary: string;
  error_code: string | null;
}

export interface RunCreated {
  run_id: number;
  status: RunState;
  status_url: string;
  report_url: string;
}

export interface RunStatus {
  run_id: number;
  status: RunState;
  current_node: string | null;
  progress: number;
  retry_count: number;
  mode: "offline" | "agent";
  execution_engine: "pending" | "rules" | "llm" | "fallback";
  model: string | null;
  facts: CaseFacts | null;
  traces: NodeTrace[];
  error_code: string | null;
  error_message: string | null;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface Citation {
  article_id: number;
  law_name: string;
  article_number: string;
  excerpt: string;
  source: string;
  score: number;
  keyword_score: number | null;
  semantic_score: number | null;
  review_status: string;
  review_reason: string | null;
  verified: boolean;
}

export interface Report {
  run_id: number;
  title: string;
  markdown: string;
  facts: CaseFacts;
  evidence_gaps: string[];
  citations: Citation[];
  notice: string;
  model: string | null;
}
