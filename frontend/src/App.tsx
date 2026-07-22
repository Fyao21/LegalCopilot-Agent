import { ChangeEvent, DragEvent, FormEvent, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { createRun, exportUrl, getCitations, getHealth, getReport, getRun } from "./api";
import type { Citation, Report, RunStatus } from "./types";

const MAX_FILE_BYTES = 10 * 1024 * 1024;
const acceptedExtensions = [".txt", ".docx", ".pdf"];
const examples = [
  "供应商收款后未按合同交货，我能否解除合同并要求赔偿？",
  "公司拖欠三个月工资，并且一直没有签订书面劳动合同。",
  "承租人逾期支付租金，我可以解除租赁合同吗？"
];

const stageLabels: Record<string, string> = {
  queued: "等待执行",
  parsing: "解析材料",
  analyzing: "提取案件要素",
  retrieving: "检索相关法规",
  reviewing: "审核法律引用",
  writing: "生成分析报告",
  completed: "分析完成",
  failed: "执行失败"
};

function validateFile(candidate: File): string | null {
  const extension = candidate.name.slice(candidate.name.lastIndexOf(".")).toLowerCase();
  if (!acceptedExtensions.includes(extension)) return "仅支持 TXT、DOCX 和 PDF 文件。";
  if (candidate.size > MAX_FILE_BYTES) return "文件不能超过 10 MB。";
  if (candidate.size === 0) return "不能上传空文件。";
  return null;
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function App() {
  const [health, setHealth] = useState<"checking" | "online" | "offline">("checking");
  const [articleCount, setArticleCount] = useState(0);
  const [question, setQuestion] = useState(examples[0]);
  const [mode, setMode] = useState<"offline" | "agent">("offline");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [runId, setRunId] = useState<number | null>(null);
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getHealth()
      .then((result) => {
        setHealth("online");
        setArticleCount(result.article_count);
      })
      .catch(() => setHealth("offline"));
  }, []);

  useEffect(() => {
    if (!runId || report || status?.status === "failed") return;
    let cancelled = false;
    const poll = async () => {
      try {
        const next = await getRun(runId);
        if (cancelled) return;
        setStatus(next);
        if (next.status === "completed") {
          const [nextReport, nextCitations] = await Promise.all([getReport(runId), getCitations(runId)]);
          if (!cancelled) {
            setReport(nextReport);
            setCitations(nextCitations);
          }
        } else if (next.status === "failed") {
          setError(next.error_message || "Agent 任务执行失败，请检查服务日志。");
        }
      } catch (pollError) {
        if (!cancelled) setError(pollError instanceof Error ? pollError.message : "查询任务失败");
      }
    };
    void poll();
    const timer = window.setInterval(poll, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [runId, report, status?.status]);

  const chooseFile = (candidate: File | null) => {
    if (!candidate) return;
    const validation = validateFile(candidate);
    if (validation) {
      setError(validation);
      return;
    }
    setFile(candidate);
    setError("");
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    chooseFile(event.dataTransfer.files[0] || null);
  };

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => chooseFile(event.target.files?.[0] || null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (question.trim().length < 2) {
      setError("请至少输入两个字符的问题。");
      return;
    }
    setSubmitting(true);
    setError("");
    setStatus(null);
    setReport(null);
    setCitations([]);
    setSelectedCitation(null);
    try {
      const created = await createRun(question.trim(), mode, file);
      setRunId(created.run_id);
      setStatus({
        run_id: created.run_id,
        status: created.status,
        current_node: null,
        progress: 0,
        retry_count: 0,
        mode,
        facts: null,
        traces: [],
        error_code: null,
        error_message: null,
        created_at: null,
        started_at: null,
        completed_at: null
      });
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "提交失败");
    } finally {
      setSubmitting(false);
    }
  };

  const reset = () => {
    setRunId(null);
    setStatus(null);
    setReport(null);
    setCitations([]);
    setSelectedCitation(null);
    setError("");
  };

  const isWorking = Boolean(runId && !report && status?.status !== "failed");

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="律镜首页">
          <span className="brand-mark">律</span>
          <span><strong>律镜</strong><small>LEGAL COPILOT</small></span>
        </a>
        <div className={`health health-${health}`}>
          <span className="health-dot" />
          {health === "online" ? `知识库在线 · ${articleCount} 条法规` : health === "offline" ? "后端未连接" : "正在连接"}
        </div>
      </header>

      <main id="top">
        <section className="hero">
          <div className="eyebrow">TRACEABLE LEGAL INTELLIGENCE</div>
          <h1>让每一条法律分析，<br /><em>都有据可查。</em></h1>
          <p>上传案件材料，律镜将提取争议要素、检索法规、审核引用，并生成一份可追溯的结构化报告。</p>
          <div className="assurance-row">
            <span>数据库原文校验</span><span>节点进度可见</span><span>模型失败可降级</span>
          </div>
        </section>

        <section className="workspace" aria-label="案件分析工作区">
          <form className="intake-card" onSubmit={submit}>
            <div className="section-number">01</div>
            <div className="section-heading">
              <div><span className="kicker">案件输入</span><h2>描述你遇到的问题</h2></div>
              <span className="privacy-note">材料仅用于本次分析</span>
            </div>

            <label className="field-label" htmlFor="question">案件问题</label>
            <textarea
              id="question"
              value={question}
              onChange={(event) => setQuestion(event.target.value.slice(0, 5000))}
              placeholder="例如：对方收款后一直没有交货，我可以解除合同并要求赔偿吗？"
              disabled={isWorking || submitting}
            />
            <div className="textarea-meta"><span>请尽量写明时间、主体、行为和诉求</span><span>{question.length} / 5000</span></div>

            <div className="example-row" aria-label="示例问题">
              {examples.map((example, index) => (
                <button type="button" key={example} onClick={() => setQuestion(example)} disabled={isWorking || submitting}>
                  示例 {index + 1}
                </button>
              ))}
            </div>

            <label className="field-label">案件材料 <span>可选</span></label>
            <div
              className={`dropzone ${dragging ? "is-dragging" : ""} ${file ? "has-file" : ""}`}
              onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
            >
              <input ref={inputRef} type="file" accept=".txt,.docx,.pdf" onChange={onFileChange} hidden />
              {file ? (
                <div className="file-row">
                  <span className="file-badge">{file.name.split(".").pop()?.toUpperCase()}</span>
                  <div><strong>{file.name}</strong><small>{formatBytes(file.size)}</small></div>
                  <button type="button" onClick={() => setFile(null)} aria-label="移除文件">移除</button>
                </div>
              ) : (
                <button type="button" className="dropzone-action" onClick={() => inputRef.current?.click()}>
                  <span className="upload-symbol">＋</span>
                  <strong>点击选择，或将文件拖到这里</strong>
                  <small>支持 TXT、DOCX、带文本层的 PDF · 最大 10 MB</small>
                </button>
              )}
            </div>

            <div className="mode-and-submit">
              <fieldset className="mode-switch" disabled={isWorking || submitting}>
                <legend>分析模式</legend>
                <label className={mode === "offline" ? "active" : ""}>
                  <input type="radio" name="mode" checked={mode === "offline"} onChange={() => setMode("offline")} />
                  离线可靠
                </label>
                <label className={mode === "agent" ? "active" : ""}>
                  <input type="radio" name="mode" checked={mode === "agent"} onChange={() => setMode("agent")} />
                  智能 Agent
                </label>
              </fieldset>
              <button className="primary-button" type="submit" disabled={submitting || isWorking || health === "offline"}>
                {submitting ? "正在提交…" : isWorking ? "分析进行中" : "开始案件分析"}<span>→</span>
              </button>
            </div>
            {error && <div className="error-banner" role="alert"><strong>未能完成操作</strong><span>{error}</span></div>}
          </form>

          <aside className="process-card">
            <div className="section-number">02</div>
            <div className="section-heading"><div><span className="kicker">执行过程</span><h2>Agent 运行轨迹</h2></div>{runId && <span className="run-id">RUN #{runId}</span>}</div>
            {!status ? (
              <div className="empty-process"><div className="orbit"><span /></div><strong>等待案件输入</strong><p>提交后，这里会展示每个分析节点的状态与耗时。</p></div>
            ) : (
              <>
                <div className="progress-summary">
                  <div><strong>{stageLabels[status.status] || status.status}</strong><span>{status.progress}%</span></div>
                  <div className="progress-track"><i style={{ width: `${status.progress}%` }} /></div>
                </div>
                <ol className="timeline">
                  {["analyze_case", "retrieve_laws", "review_citations", "write_report"].map((node, index) => {
                    const trace = status.traces.find((item) => item.node === node);
                    const nodeLabels = ["案件要素提取", "混合检索法规", "引用真实性审核", "生成分析报告"];
                    const active = status.current_node === node && !trace;
                    return (
                      <li key={node} className={trace ? "done" : active ? "active" : "pending"}>
                        <span className="timeline-index">{trace ? "✓" : index + 1}</span>
                        <div><strong>{nodeLabels[index]}</strong><small>{trace?.action_summary || (active ? "正在执行…" : "等待执行")}</small></div>
                        {trace && <time>{trace.duration_ms} ms</time>}
                      </li>
                    );
                  })}
                </ol>
                {status.facts && (
                  <div className="facts-preview"><span>识别结果</span><strong>{status.facts.case_type}</strong><small>置信度 {status.facts.confidence ? `${Math.round(status.facts.confidence * 100)}%` : "待评估"}</small></div>
                )}
              </>
            )}
          </aside>
        </section>

        {report && (
          <section className="result-section">
            <div className="result-header">
              <div><span className="kicker">分析完成</span><h2>{report.title}</h2><p>报告仅使用审核通过的知识库引用，请在正式使用前核对权威来源。</p></div>
              <div className="result-actions">
                <a href={exportUrl(report.run_id, "markdown")}>下载 Markdown</a>
                <a className="filled" href={exportUrl(report.run_id, "pdf")}>下载 PDF</a>
                <button type="button" onClick={reset}>分析新案件</button>
              </div>
            </div>
            <div className="result-grid">
              <article className="report-paper"><ReactMarkdown>{report.markdown}</ReactMarkdown></article>
              <aside className="evidence-panel">
                <div className="evidence-title"><span>已审核依据</span><strong>{citations.filter((item) => item.verified).length} / {citations.length}</strong></div>
                {citations.map((citation) => (
                  <button type="button" key={citation.article_id} className={`citation-card ${citation.verified ? "verified" : "unverified"}`} onClick={() => setSelectedCitation(citation)}>
                    <span className="citation-status">{citation.verified ? "已核验" : "低置信度"}</span>
                    <strong>{citation.law_name}</strong>
                    <b>{citation.article_number}</b>
                    <small>综合相关度 {(citation.score * 100).toFixed(1)}%</small>
                  </button>
                ))}
                <div className="notice-box">{report.notice}</div>
              </aside>
            </div>
          </section>
        )}
      </main>

      <footer><span>律镜 Legal Copilot · 工程演示项目</span><span>所有结论均需人工与权威来源复核</span></footer>

      {selectedCitation && (
        <div className="drawer-backdrop" role="presentation" onClick={() => setSelectedCitation(null)}>
          <aside className="citation-drawer" role="dialog" aria-modal="true" aria-label="法规引用详情" onClick={(event) => event.stopPropagation()}>
            <button className="drawer-close" type="button" onClick={() => setSelectedCitation(null)} aria-label="关闭">×</button>
            <span className="kicker">引用 #{selectedCitation.article_id}</span>
            <h2>{selectedCitation.law_name}</h2>
            <h3>{selectedCitation.article_number}</h3>
            <p className="article-text">{selectedCitation.excerpt}</p>
            <dl>
              <div><dt>来源</dt><dd>{selectedCitation.source}</dd></div>
              <div><dt>关键词分数</dt><dd>{((selectedCitation.keyword_score || 0) * 100).toFixed(1)}%</dd></div>
              <div><dt>语义分数</dt><dd>{((selectedCitation.semantic_score || 0) * 100).toFixed(1)}%</dd></div>
              <div><dt>审核结论</dt><dd>{selectedCitation.review_reason || "暂无说明"}</dd></div>
            </dl>
          </aside>
        </div>
      )}
    </div>
  );
}

export default App;
