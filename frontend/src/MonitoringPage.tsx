import { useCallback, useEffect, useState } from "react";
import { getMonitoringOverview, getRunMonitoring } from "./api";
import type {
  MonitoringOverview,
  MonitoringSpan,
  RunMonitoringDetail
} from "./types";

interface MonitoringPageProps {
  backendOnline: boolean;
  activeRunId: number | null;
}

const nodeLabels: Record<string, string> = {
  analyze_case: "案件要素提取",
  clarify_user: "补充信息恢复",
  retrieve_laws: "法规混合检索",
  review_citations: "引用真实性审核",
  retry_retrieval: "补充检索重试",
  write_report: "生成报告草稿",
  revise_report: "根据意见修订",
  approve_report: "人工审批恢复"
};

const spanLabels: Record<string, string> = {
  "agent.invoke": "Agent 工作流",
  "agent.analyze_case": "案件要素提取",
  "agent.interrupt.resume": "用户追问恢复",
  "agent.retrieval": "混合检索",
  "agent.review_citations": "引用审核",
  "agent.retry": "补充检索",
  "agent.write_report": "报告生成",
  "agent.revise_report": "报告修订",
  "agent.approval.resume": "人工审批恢复",
  "gen_ai.chat": "LLM 调用",
  "gen_ai.embeddings": "Embedding 调用"
};

function formatDuration(value: number): string {
  if (value < 1000) return `${value} ms`;
  return `${(value / 1000).toFixed(2)} s`;
}

function formatCost(value: number): string {
  if (value === 0) return "¥0.000000";
  return `¥${value.toFixed(6)}`;
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function spanKind(span: MonitoringSpan): string {
  if (span.name === "gen_ai.chat") return "CHAT";
  if (span.name === "gen_ai.embeddings") return "EMBED";
  if (span.name === "agent.invoke") return "ROOT";
  return "NODE";
}

export default function MonitoringPage({
  backendOnline,
  activeRunId
}: MonitoringPageProps) {
  const [days, setDays] = useState(7);
  const [overview, setOverview] = useState<MonitoringOverview | null>(null);
  const [detail, setDetail] = useState<RunMonitoringDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");

  const loadOverview = useCallback(async () => {
    if (!backendOnline) return;
    setLoading(true);
    setError("");
    try {
      setOverview(await getMonitoringOverview(days));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "无法加载监控概览");
    } finally {
      setLoading(false);
    }
  }, [backendOnline, days]);

  const loadDetail = useCallback(async (runId: number) => {
    setDetailLoading(true);
    setError("");
    try {
      setDetail(await getRunMonitoring(runId));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "无法加载运行 Trace");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  useEffect(() => {
    if (backendOnline && activeRunId) void loadDetail(activeRunId);
  }, [activeRunId, backendOnline, loadDetail]);

  return (
    <>
      <section className="monitoring-hero">
        <div>
          <span className="eyebrow">AGENT OBSERVABILITY</span>
          <h1>运行是否可靠，<br /><em>要用数据回答。</em></h1>
          <p>通过 Trace ID 串联工作流节点，查看耗时、模型、Token、估算费用、重试和降级原因。</p>
        </div>
        <div className="monitoring-privacy">
          <strong>隐私安全边界</strong>
          <span>只记录允许字段，不采集案件全文、Prompt、API Key、身份证、电话或地址。</span>
        </div>
      </section>

      <section className="monitoring-shell" aria-label="Agent 运行监控">
        <div className="monitoring-toolbar">
          <div>
            <span className="kicker">运行概览</span>
            <h2>最近 {days} 天</h2>
          </div>
          <div className="monitoring-filters">
            <label>
              统计范围
              <select value={days} onChange={(event) => setDays(Number(event.target.value))}>
                <option value={1}>最近 1 天</option>
                <option value={7}>最近 7 天</option>
                <option value={30}>最近 30 天</option>
                <option value={90}>最近 90 天</option>
              </select>
            </label>
            <button type="button" onClick={() => void loadOverview()} disabled={loading}>
              {loading ? "刷新中…" : "刷新数据"}
            </button>
          </div>
        </div>

        {!backendOnline && (
          <div className="monitoring-empty">后端未连接，请先启动 FastAPI 服务。</div>
        )}
        {error && <div className="error-banner" role="alert"><strong>监控数据加载失败</strong><span>{error}</span></div>}

        {overview && (
          <>
            <div className="metric-grid">
              <article><span>运行次数</span><strong>{overview.run_count}</strong><small>带 Trace ID 的 Agent 运行</small></article>
              <article><span>运行成功率</span><strong>{formatPercent(overview.success_rate)}</strong><small>未进入 failed 的运行</small></article>
              <article className={overview.fallback_rate > 0 ? "metric-warning" : ""}><span>降级率</span><strong>{formatPercent(overview.fallback_rate)}</strong><small>至少一个模型或向量回退</small></article>
              <article><span>平均 / P95</span><strong>{formatDuration(overview.average_duration_ms)}</strong><small>P95 {formatDuration(overview.p95_duration_ms)}</small></article>
              <article><span>累计 Token</span><strong>{overview.total_input_tokens + overview.total_output_tokens}</strong><small>输入 {overview.total_input_tokens} · 输出 {overview.total_output_tokens}</small></article>
              <article><span>估算费用</span><strong>{formatCost(overview.total_estimated_cost_cny)}</strong><small>人民币 · 按环境变量中的单价估算</small></article>
            </div>

            <div className="monitoring-grid">
              <section className="monitor-card">
                <div className="monitor-card-heading">
                  <div><span className="kicker">NODE LATENCY</span><h3>节点平均与 P95 耗时</h3></div>
                  <span>{overview.node_metrics.length} 个节点</span>
                </div>
                {overview.node_metrics.length === 0 ? (
                  <div className="monitoring-empty">运行一次案件分析后会生成节点指标。</div>
                ) : (
                  <div className="node-metrics">
                    {overview.node_metrics.map((metric) => {
                      const ceiling = Math.max(
                        ...overview.node_metrics.map((item) => item.p95_duration_ms),
                        1
                      );
                      return (
                        <div key={metric.node}>
                          <div>
                            <strong>{nodeLabels[metric.node] || metric.node}</strong>
                            <span>平均 {formatDuration(metric.average_duration_ms)} · P95 {formatDuration(metric.p95_duration_ms)}</span>
                          </div>
                          <i><b style={{ width: `${Math.max(3, metric.p95_duration_ms / ceiling * 100)}%` }} /></i>
                          <small>{metric.sample_count} 个样本</small>
                        </div>
                      );
                    })}
                  </div>
                )}
              </section>

              <section className="monitor-card recent-runs">
                <div className="monitor-card-heading">
                  <div><span className="kicker">RECENT RUNS</span><h3>最近运行</h3></div>
                  {activeRunId && (
                    <button type="button" onClick={() => void loadDetail(activeRunId)}>
                      查看当前 RUN #{activeRunId}
                    </button>
                  )}
                </div>
                {overview.recent_runs.length === 0 ? (
                  <div className="monitoring-empty">还没有第八周监控数据。</div>
                ) : (
                  <div className="run-list">
                    {overview.recent_runs.map((run) => (
                      <button type="button" key={run.run_id} onClick={() => void loadDetail(run.run_id)}>
                        <span className={`run-state run-state-${run.status}`}>{run.status}</span>
                        <strong>RUN #{run.run_id}</strong>
                        <code>{run.trace_id.slice(0, 12)}…</code>
                        <small>{formatDuration(run.total_duration_ms)} · {run.model || run.mode}</small>
                        {run.fallback_count > 0 && <b>{run.fallback_count} 次降级</b>}
                      </button>
                    ))}
                  </div>
                )}
              </section>
            </div>
          </>
        )}

        <section className="trace-detail monitor-card">
          <div className="monitor-card-heading">
            <div><span className="kicker">TRACE DETAIL</span><h3>单次运行链路</h3></div>
            {detailLoading && <span>加载中…</span>}
          </div>
          {!detail ? (
            <div className="monitoring-empty">从最近运行中选择一条记录，查看完整 Trace。</div>
          ) : (
            <>
              <div className="trace-summary">
                <div><span>RUN</span><strong>#{detail.run_id}</strong></div>
                <div className="trace-id"><span>Trace ID</span><code>{detail.trace_id}</code></div>
                <div><span>最慢节点</span><strong>{nodeLabels[detail.slowest_node || ""] || detail.slowest_node || "暂无"}</strong><small>{formatDuration(detail.slowest_node_duration_ms)}</small></div>
                <div><span>模型</span><strong>{detail.model || "未调用 LLM"}</strong><small>{detail.mode}</small></div>
                <div><span>Token</span><strong>{detail.input_tokens + detail.output_tokens}</strong><small>输入 {detail.input_tokens} · 输出 {detail.output_tokens}</small></div>
                <div><span>费用</span><strong>{formatCost(detail.estimated_cost_cny)}</strong><small>人民币 · {detail.fallback_count} 次降级 · {detail.retry_count} 次工作流重试</small></div>
              </div>
              <ol className="span-waterfall">
                {detail.spans.map((span) => (
                  <li key={span.span_id} className={span.fallback_reason ? "span-fallback" : ""}>
                    <span className={`span-kind span-kind-${spanKind(span).toLowerCase()}`}>{spanKind(span)}</span>
                    <div>
                      <strong>{spanLabels[span.name] || span.name}</strong>
                      <code>{span.span_id}</code>
                      <small>
                        {span.provider || "local"}{span.model ? ` / ${span.model}` : ""}
                        {span.input_tokens + span.output_tokens > 0
                          ? ` · ${span.input_tokens + span.output_tokens} tokens`
                          : ""}
                      </small>
                      {span.fallback_reason && <p>降级原因：{span.fallback_reason}</p>}
                    </div>
                    <div className="span-duration">
                      <strong>{formatDuration(span.duration_ms)}</strong>
                      {span.retry_count > 0 && <small>重试 {span.retry_count}</small>}
                    </div>
                  </li>
                ))}
              </ol>
            </>
          )}
        </section>
      </section>
    </>
  );
}
