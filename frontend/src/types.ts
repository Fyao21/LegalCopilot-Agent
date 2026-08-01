export type RunState =
  | "queued"
  | "parsing"
  | "analyzing"
  | "waiting_for_user"
  | "resuming"
  | "retrieving"
  | "reviewing"
  | "writing"
  | "waiting_for_approval"
  | "revising"
  | "completed"
  | "rejected"
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

export interface QuestionExample {
  example_id: string;
  category: string;
  detail_level: "brief" | "detailed";
  question: string;
}

export interface QuestionExamplesResponse {
  count: number;
  requested_category: string | null;
  requested_detail_level: "brief" | "detailed";
  available_categories: string[];
  examples: QuestionExample[];
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
  as_of_date: string | null;
  trace_id: string;
  status_url: string;
  report_url: string;
  monitoring_url: string;
}

export interface RunStatus {
  run_id: number;
  status: RunState;
  current_node: string | null;
  progress: number;
  retry_count: number;
  clarification_round: number;
  state_version: number;
  current_report_version: number;
  approved_report_version: number | null;
  pending_action_url: string | null;
  mode: "offline" | "agent";
  as_of_date: string | null;
  execution_engine: "pending" | "rules" | "llm" | "fallback";
  model: string | null;
  trace_id: string;
  monitoring_url: string;
  total_duration_ms: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
  fallback_count: number;
  facts: CaseFacts | null;
  traces: NodeTrace[];
  error_code: string | null;
  error_message: string | null;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface MonitoringSpan {
  span_id: string;
  parent_span_id: string | null;
  name: string;
  node: string | null;
  status: string;
  duration_ms: number;
  provider: string | null;
  model: string | null;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
  retry_count: number;
  fallback_reason: string | null;
  error_code: string | null;
  attributes: Record<string, string | number | boolean | null>;
  started_at: string;
  completed_at: string;
}

export interface RunMonitoringDetail {
  run_id: number;
  trace_id: string;
  status: string;
  mode: string;
  model: string | null;
  total_duration_ms: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
  fallback_count: number;
  retry_count: number;
  slowest_node: string | null;
  slowest_node_duration_ms: number;
  started_at: string | null;
  completed_at: string | null;
  spans: MonitoringSpan[];
}

export interface MonitoringNodeMetric {
  node: string;
  sample_count: number;
  average_duration_ms: number;
  p95_duration_ms: number;
}

export interface MonitoringRunSummary {
  run_id: number;
  trace_id: string;
  status: string;
  mode: string;
  model: string | null;
  total_duration_ms: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
  fallback_count: number;
  retry_count: number;
  created_at: string | null;
}

export interface MonitoringOverview {
  days: number;
  run_count: number;
  success_rate: number;
  fallback_rate: number;
  average_duration_ms: number;
  p95_duration_ms: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_estimated_cost_usd: number;
  node_metrics: MonitoringNodeMetric[];
  recent_runs: MonitoringRunSummary[];
}

export interface ClarificationQuestion {
  question_id: string;
  prompt: string;
  missing_field: string | null;
  required: boolean;
}

export interface ClarificationPendingAction {
  action_id: number;
  type: "clarification";
  round: number;
  max_rounds: number;
  questions: ClarificationQuestion[];
}

export type ApprovalAction = "approve" | "request_changes" | "reject";

export interface ApprovalPendingAction {
  action_id: number;
  type: "approval";
  report_version: number;
  report_version_id: number;
  title: string;
  change_summary: string | null;
  allowed_actions: ApprovalAction[];
}

export interface PendingActionResponse {
  run_id: number;
  status: RunState;
  state_version: number;
  action: ClarificationPendingAction | ApprovalPendingAction | null;
}

export interface ClarificationSubmissionResponse {
  run_id: number;
  status: RunState;
  state_version: number;
  replayed: boolean;
  status_url: string;
  message: string;
}

export interface ApprovalSubmissionResponse {
  run_id: number;
  action: ApprovalAction;
  status: RunState;
  state_version: number;
  report_version: number;
  replayed: boolean;
  status_url: string;
  message: string;
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
  law_id: number | null;
  law_version_id: number | null;
  version_label: string;
  effect_status: "effective" | "amended" | "repealed" | "legacy";
  effective_from: string | null;
  effective_to: string | null;
  review_status: string;
  review_reason: string | null;
  verified: boolean;
}

export interface Report {
  run_id: number;
  as_of_date: string | null;
  version_number: number;
  approval_status: "draft" | "approved" | "superseded" | "rejected";
  is_final: boolean;
  title: string;
  markdown: string;
  facts: CaseFacts;
  evidence_gaps: string[];
  citations: Citation[];
  notice: string;
  model: string | null;
}

export interface ReportVersionSummary {
  version_number: number;
  status: "draft" | "approved" | "superseded" | "rejected";
  title: string;
  change_summary: string | null;
  created_at: string | null;
  approved_at: string | null;
}

export interface ReportVersionDetail extends ReportVersionSummary {
  markdown: string;
  facts: CaseFacts;
  citations: Citation[];
  diff_from_previous: string;
}

export interface LegalArticleCreate {
  law_name: string;
  article_number: string;
  content: string;
  source: string;
}

export interface LegalArticle {
  article_id: number;
  law_name: string;
  article_number: string;
  content: string;
  source: string;
  law_id: number | null;
  law_version_id: number | null;
  version_label: string;
  effect_status: "effective" | "amended" | "repealed" | "legacy";
  effective_from: string | null;
  effective_to: string | null;
}

export type KnowledgeBatchStatus = "created" | "duplicate" | "invalid";

export interface KnowledgeBatchItem {
  filename: string;
  status: KnowledgeBatchStatus;
  article_id: number | null;
  law_name: string | null;
  article_number: string | null;
  message: string;
}

export interface KnowledgeBatchResponse {
  total: number;
  created_count: number;
  duplicate_count: number;
  invalid_count: number;
  items: KnowledgeBatchItem[];
}

export interface KnowledgeNormalizationResponse {
  original_filename: string;
  standardized_filename: string;
  law_name: string | null;
  article_number: string | null;
  source: string | null;
  content: string;
  confidence: number;
  missing_fields: string[];
  warnings: string[];
  multiple_articles_detected: boolean;
  ready_for_import: boolean;
  requires_human_review: boolean;
  standardized_text: string;
  model: string;
}
