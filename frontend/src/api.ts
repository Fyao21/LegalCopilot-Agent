import type {
  ApprovalAction,
  ApprovalSubmissionResponse,
  Citation,
  ClarificationSubmissionResponse,
  KnowledgeBatchResponse,
  KnowledgeNormalizationResponse,
  LegalArticle,
  LegalArticleCreate,
  MonitoringOverview,
  QuestionExamplesResponse,
  PendingActionResponse,
  Report,
  ReportVersionDetail,
  ReportVersionSummary,
  RunMonitoringDetail,
  RunCreated,
  RunStatus
} from "./types";

export const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

const errorMessages: Record<number, string> = {
  408: "文件解析超时，请尝试更小或更简单的文件。",
  409: "任务当前状态不允许执行此操作。",
  413: "文件过大，请上传不超过 10 MB 的文件。",
  415: "文件格式不受支持，请使用 TXT、DOCX 或带文本层的 PDF。",
  422: "提交内容未通过校验，请检查问题、模式和文件。",
  429: "请求过于频繁，请稍后重试。",
  500: "服务暂时出现异常，请稍后重试。"
};

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new Error("无法连接后端服务，请确认 FastAPI 已在 8000 端口启动。");
  }
  if (!response.ok) {
    let detail = "";
    try {
      const body = (await response.json()) as { detail?: string | Array<{ msg?: string }> };
      detail = typeof body.detail === "string" ? body.detail : body.detail?.[0]?.msg || "";
    } catch {
      detail = "";
    }
    throw new Error(detail || errorMessages[response.status] || `请求失败（HTTP ${response.status}）`);
  }
  return response.json() as Promise<T>;
}

export async function getHealth(): Promise<{ status: string; article_count: number }> {
  return apiRequest("/health");
}

export async function getRandomQuestionExamples(
  count = 3,
  category?: string,
  detailLevel: "brief" | "detailed" = "brief"
): Promise<QuestionExamplesResponse> {
  const params = new URLSearchParams({
    count: String(count),
    detail_level: detailLevel
  });
  if (category) params.set("category", category);
  return apiRequest(`/api/v1/examples/questions/random?${params.toString()}`);
}

export async function createKnowledgeArticle(payload: LegalArticleCreate): Promise<LegalArticle> {
  return apiRequest("/api/v1/knowledge/articles", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export async function createKnowledgeArticleBatch(files: File[]): Promise<KnowledgeBatchResponse> {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  return apiRequest("/api/v1/knowledge/articles/batch", {
    method: "POST",
    body: form
  });
}

export async function normalizeKnowledgeArticle(
  file: File
): Promise<KnowledgeNormalizationResponse> {
  const form = new FormData();
  form.append("file", file);
  return apiRequest("/api/v1/knowledge/articles/normalize", {
    method: "POST",
    body: form
  });
}

export async function createRun(
  question: string,
  mode: "offline" | "agent",
  file: File | null,
  asOfDate: string
): Promise<RunCreated> {
  const form = new FormData();
  form.append("question", question);
  form.append("mode", mode);
  if (asOfDate) form.append("as_of_date", asOfDate);
  if (file) form.append("file", file);
  return apiRequest("/api/v1/runs", { method: "POST", body: form });
}

export async function getRun(runId: number): Promise<RunStatus> {
  return apiRequest(`/api/v1/runs/${runId}`);
}

export async function getMonitoringOverview(days = 7): Promise<MonitoringOverview> {
  return apiRequest(`/api/v1/monitoring/overview?days=${days}`);
}

export async function getRunMonitoring(runId: number): Promise<RunMonitoringDetail> {
  return apiRequest(`/api/v1/runs/${runId}/monitoring`);
}

export async function getPendingAction(runId: number): Promise<PendingActionResponse> {
  return apiRequest(`/api/v1/runs/${runId}/pending-action`);
}

export async function submitClarifications(
  runId: number,
  expectedStateVersion: number,
  answers: Array<{ question_id: string; answer: string }>,
  idempotencyKey: string
): Promise<ClarificationSubmissionResponse> {
  return apiRequest(`/api/v1/runs/${runId}/clarifications`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey
    },
    body: JSON.stringify({
      expected_state_version: expectedStateVersion,
      answers
    })
  });
}

export async function submitApproval(
  runId: number,
  expectedStateVersion: number,
  action: ApprovalAction,
  comment: string,
  reviewer: string,
  idempotencyKey: string
): Promise<ApprovalSubmissionResponse> {
  return apiRequest(`/api/v1/runs/${runId}/approvals`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey
    },
    body: JSON.stringify({
      expected_state_version: expectedStateVersion,
      action,
      comment,
      reviewer
    })
  });
}

export async function getCitations(runId: number): Promise<Citation[]> {
  return apiRequest(`/api/v1/runs/${runId}/citations`);
}

export async function getReport(runId: number): Promise<Report> {
  return apiRequest(`/api/v1/runs/${runId}/report`);
}

export async function getReportVersions(runId: number): Promise<ReportVersionSummary[]> {
  return apiRequest(`/api/v1/runs/${runId}/report-versions`);
}

export async function getReportVersion(
  runId: number,
  versionNumber: number
): Promise<ReportVersionDetail> {
  return apiRequest(`/api/v1/runs/${runId}/report-versions/${versionNumber}`);
}

export function exportUrl(runId: number, format: "markdown" | "pdf"): string {
  return `${API_BASE}/api/v1/runs/${runId}/export?format=${format}`;
}
