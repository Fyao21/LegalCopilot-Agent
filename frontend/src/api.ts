import type { Citation, Report, RunCreated, RunStatus } from "./types";

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

export async function createRun(question: string, mode: "offline" | "agent", file: File | null): Promise<RunCreated> {
  const form = new FormData();
  form.append("question", question);
  form.append("mode", mode);
  if (file) form.append("file", file);
  return apiRequest("/api/v1/runs", { method: "POST", body: form });
}

export async function getRun(runId: number): Promise<RunStatus> {
  return apiRequest(`/api/v1/runs/${runId}`);
}

export async function getCitations(runId: number): Promise<Citation[]> {
  return apiRequest(`/api/v1/runs/${runId}/citations`);
}

export async function getReport(runId: number): Promise<Report> {
  return apiRequest(`/api/v1/runs/${runId}/report`);
}

export function exportUrl(runId: number, format: "markdown" | "pdf"): string {
  return `${API_BASE}/api/v1/runs/${runId}/export?format=${format}`;
}
