import { ChangeEvent, DragEvent, FormEvent, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  createRun,
  exportUrl,
  getCitations,
  getHealth,
  getPendingAction,
  getRandomQuestionExamples,
  getReport,
  getReportVersion,
  getReportVersions,
  getRun,
  submitApproval,
  submitClarifications
} from "./api";
import KnowledgePage from "./KnowledgePage";
import MonitoringPage from "./MonitoringPage";
import type {
  ApprovalAction,
  Citation,
  PendingActionResponse,
  QuestionExample,
  Report,
  ReportVersionDetail,
  ReportVersionSummary,
  RunStatus
} from "./types";

const MAX_FILE_BYTES = 10 * 1024 * 1024;
const acceptedExtensions = [".txt", ".docx", ".pdf"];
const fallbackExamples: QuestionExample[] = [
  {
    example_id: "fallback-contract",
    category: "合同纠纷",
    detail_level: "brief",
    question: "供应商收款后未按合同交货，我能否解除合同并要求赔偿？"
  },
  {
    example_id: "fallback-labor",
    category: "劳动争议",
    detail_level: "brief",
    question: "公司拖欠三个月工资，并且一直没有签订书面劳动合同。"
  },
  {
    example_id: "fallback-food",
    category: "食品安全",
    detail_level: "brief",
    question: "食物中毒商家需要承担什么责任？"
  }
];

const stageLabels: Record<string, string> = {
  queued: "等待执行",
  parsing: "解析材料",
  analyzing: "提取案件要素",
  waiting_for_user: "等待补充信息",
  resuming: "正在恢复分析",
  retrieving: "检索相关法规",
  reviewing: "审核法律引用",
  writing: "生成分析报告",
  waiting_for_approval: "等待人工审批",
  revising: "根据意见修改",
  completed: "审批通过",
  rejected: "报告已驳回",
  failed: "执行失败"
};

type Page = "analysis" | "knowledge" | "monitoring";

function pageFromHash(): Page {
  if (window.location.hash === "#knowledge") return "knowledge";
  if (window.location.hash === "#monitoring") return "monitoring";
  return "analysis";
}

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

function lawEffectLabel(citation: Citation): string {
  if (citation.effect_status === "effective") return "现行有效";
  if (citation.effect_status === "amended") return "已修订";
  if (citation.effect_status === "repealed") return "已废止 · 历史时点适用";
  return "效力未标注";
}

function lawValidity(citation: Citation): string {
  const from = citation.effective_from || "未标注";
  const to = citation.effective_to || "长期有效";
  return `${from} 至 ${to}`;
}

function App() {
  const [page, setPage] = useState<Page>(pageFromHash);
  const [health, setHealth] = useState<"checking" | "online" | "offline">("checking");
  const [articleCount, setArticleCount] = useState(0);
  const [question, setQuestion] = useState(fallbackExamples[0].question);
  const [examples, setExamples] = useState<QuestionExample[]>(fallbackExamples);
  const [examplesLoading, setExamplesLoading] = useState(false);
  const [exampleDetailLevel, setExampleDetailLevel] = useState<"brief" | "detailed">("brief");
  const [mode, setMode] = useState<"offline" | "agent">("offline");
  const [asOfDate, setAsOfDate] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [runId, setRunId] = useState<number | null>(() => {
    const saved = window.sessionStorage.getItem("legal-copilot-active-run");
    const parsed = saved ? Number(saved) : NaN;
    return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
  });
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [pendingAction, setPendingAction] = useState<PendingActionResponse | null>(null);
  const [clarificationAnswers, setClarificationAnswers] = useState<Record<string, string>>({});
  const [clarificationSubmitting, setClarificationSubmitting] = useState(false);
  const [approvalComment, setApprovalComment] = useState("");
  const [approvalReviewer, setApprovalReviewer] = useState("本地审核人");
  const [approvalSubmitting, setApprovalSubmitting] = useState(false);
  const [report, setReport] = useState<Report | null>(null);
  const [reportVersions, setReportVersions] = useState<ReportVersionSummary[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<ReportVersionDetail | null>(null);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const approvalActionIdRef = useRef<number | null>(null);

  useEffect(() => {
    getHealth()
      .then((result) => {
        setHealth("online");
        setArticleCount(result.article_count);
      })
      .catch(() => setHealth("offline"));
  }, []);

  useEffect(() => {
    getRandomQuestionExamples(3)
      .then((result) => setExamples(result.examples))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    const syncPage = () => {
      setPage(pageFromHash());
      window.scrollTo({ top: 0, behavior: "smooth" });
    };
    window.addEventListener("hashchange", syncPage);
    return () => window.removeEventListener("hashchange", syncPage);
  }, []);

  useEffect(() => {
    if (runId) {
      window.sessionStorage.setItem("legal-copilot-active-run", String(runId));
    } else {
      window.sessionStorage.removeItem("legal-copilot-active-run");
    }
  }, [runId]);

  useEffect(() => {
    const terminalWithReport = status
      && ["completed", "rejected"].includes(status.status)
      && report;
    if (!runId || terminalWithReport || status?.status === "failed") return;
    let cancelled = false;
    const poll = async () => {
      try {
        const next = await getRun(runId);
        if (cancelled) return;
        setStatus(next);
        if (["completed", "rejected"].includes(next.status)) {
          const [nextReport, nextCitations, nextVersions] = await Promise.all([
            getReport(runId),
            getCitations(runId),
            getReportVersions(runId)
          ]);
          if (!cancelled) {
            setReport(nextReport);
            setCitations(nextCitations);
            setReportVersions(nextVersions);
            setPendingAction(null);
          }
        } else if (["waiting_for_user", "waiting_for_approval"].includes(next.status)) {
          const pending = await getPendingAction(runId);
          if (!cancelled) {
            if (
              pending.action?.type === "approval"
              && approvalActionIdRef.current !== pending.action.action_id
            ) {
              approvalActionIdRef.current = pending.action.action_id;
              setApprovalComment("");
            }
            setPendingAction(pending);
            if (pending.action?.type === "clarification") {
              setClarificationAnswers((current) => {
                const initialized = { ...current };
                pending.action?.type === "clarification"
                  && pending.action.questions.forEach((item) => {
                    if (!(item.question_id in initialized)) initialized[item.question_id] = "";
                  });
                return initialized;
              });
            } else if (pending.action?.type === "approval") {
              const [draft, nextCitations, nextVersions] = await Promise.all([
                getReport(runId),
                getCitations(runId),
                getReportVersions(runId)
              ]);
              if (!cancelled) {
                setReport(draft);
                setCitations(nextCitations);
                setReportVersions(nextVersions);
              }
            }
          }
        } else if (["resuming", "revising"].includes(next.status)) {
          setPendingAction(null);
          setReport(null);
          setSelectedVersion(null);
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
  }, [runId, Boolean(report), status?.status]);

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

  const loadExamples = async (detailLevel: "brief" | "detailed") => {
    setExamplesLoading(true);
    try {
      const result = await getRandomQuestionExamples(3, undefined, detailLevel);
      setExamples(result.examples);
      setError("");
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : "刷新示例失败");
    } finally {
      setExamplesLoading(false);
    }
  };

  const changeExampleDetailLevel = (detailLevel: "brief" | "detailed") => {
    setExampleDetailLevel(detailLevel);
    void loadExamples(detailLevel);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (question.trim().length < 2) {
      setError("请至少输入两个字符的问题。");
      return;
    }
    setSubmitting(true);
    setError("");
    setStatus(null);
    setPendingAction(null);
    setClarificationAnswers({});
    approvalActionIdRef.current = null;
    setApprovalComment("");
    setReport(null);
    setReportVersions([]);
    setSelectedVersion(null);
    setCitations([]);
    setSelectedCitation(null);
    try {
      const created = await createRun(question.trim(), mode, file, asOfDate);
      setRunId(created.run_id);
      setStatus({
        run_id: created.run_id,
        status: created.status,
        current_node: null,
        progress: 0,
        retry_count: 0,
        clarification_round: 0,
        state_version: 0,
        current_report_version: 0,
        approved_report_version: null,
        pending_action_url: null,
        mode,
        as_of_date: created.as_of_date,
        execution_engine: "pending",
        model: null,
        trace_id: created.trace_id,
        monitoring_url: created.monitoring_url,
        total_duration_ms: 0,
        input_tokens: 0,
        output_tokens: 0,
        estimated_cost_cny: 0,
        fallback_count: 0,
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
    setPendingAction(null);
    setClarificationAnswers({});
    approvalActionIdRef.current = null;
    setApprovalComment("");
    setReport(null);
    setReportVersions([]);
    setSelectedVersion(null);
    setCitations([]);
    setSelectedCitation(null);
    setAsOfDate("");
    setError("");
  };

  const submitAnswers = async (event: FormEvent) => {
    event.preventDefault();
    if (!runId || !status || pendingAction?.action?.type !== "clarification") return;
    const answers = pendingAction.action.questions.map((item) => ({
      question_id: item.question_id,
      answer: (clarificationAnswers[item.question_id] || "").trim()
    }));
    if (answers.some((item) => !item.answer)) {
      setError("请回答所有追问；确实不了解时可以选择“暂不清楚”。");
      return;
    }
    setClarificationSubmitting(true);
    setError("");
    try {
      const result = await submitClarifications(
        runId,
        pendingAction.state_version,
        answers,
        `clarification-${runId}-${pendingAction.action.action_id}`
      );
      setStatus((current) => current ? {
        ...current,
        status: result.status,
        state_version: result.state_version,
        current_node: "clarify_user"
      } : current);
      setPendingAction(null);
    } catch (answerError) {
      setError(answerError instanceof Error ? answerError.message : "提交补充信息失败");
    } finally {
      setClarificationSubmitting(false);
    }
  };

  const handleApproval = async (action: ApprovalAction) => {
    if (!runId || !status || pendingAction?.action?.type !== "approval") return;
    if (["request_changes", "reject"].includes(action) && !approvalComment.trim()) {
      setError("要求修改或驳回时，请先填写具体审批意见。");
      return;
    }
    setApprovalSubmitting(true);
    setError("");
    try {
      const result = await submitApproval(
        runId,
        pendingAction.state_version,
        action,
        approvalComment.trim(),
        approvalReviewer.trim() || "本地审核人",
        `approval-${runId}-${pendingAction.action.action_id}-${action}`
      );
      setStatus((current) => current ? {
        ...current,
        status: result.status,
        state_version: result.state_version,
        current_node: "approve_report"
      } : current);
      setApprovalComment("");
      setPendingAction(null);
      setReport(null);
      setSelectedVersion(null);
    } catch (approvalError) {
      setError(approvalError instanceof Error ? approvalError.message : "提交审批失败");
    } finally {
      setApprovalSubmitting(false);
    }
  };

  const loadVersionDetail = async (versionNumber: number) => {
    if (!runId) return;
    try {
      setSelectedVersion(await getReportVersion(runId, versionNumber));
      setError("");
    } catch (versionError) {
      setError(versionError instanceof Error ? versionError.message : "读取报告版本失败");
    }
  };

  const isWorking = Boolean(
    runId
    && status
    && !["completed", "rejected", "failed"].includes(status.status)
  );
  const showClarificationNode = Boolean(
    status?.current_node === "clarify_user"
    || status?.clarification_round
    || status?.traces.some((item) => item.node === "clarify_user")
  );
  const showApprovalNode = Boolean(
    status?.current_report_version
    || ["waiting_for_approval", "revising", "completed", "rejected"].includes(status?.status || "")
    || status?.traces.some((item) => ["approve_report", "revise_report"].includes(item.node))
  );
  const timelineNodes = [
    { node: "analyze_case", label: "案件要素提取" },
    ...(showClarificationNode ? [{ node: "clarify_user", label: "补充关键信息" }] : []),
    { node: "retrieve_laws", label: "混合检索法规" },
    { node: "review_citations", label: "引用真实性审核" },
    { node: "write_report", label: "生成报告草稿" },
    ...(showApprovalNode ? [
      { node: "revise_report", label: "根据意见修改" },
      { node: "approve_report", label: "人工审批发布" }
    ] : [])
  ];
  const onArticlesCreated = (count: number) => {
    setArticleCount((current) => current + count);
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#analysis" aria-label="律镜首页">
          <span className="brand-mark">律</span>
          <span><strong>律镜</strong><small>LEGAL COPILOT</small></span>
        </a>
        <nav className="topnav" aria-label="主要导航">
          <a className={page === "analysis" ? "active" : ""} href="#analysis">案件分析</a>
          <a className={page === "knowledge" ? "active" : ""} href="#knowledge">知识库管理</a>
          <a className={page === "monitoring" ? "active" : ""} href="#monitoring">运行监控</a>
        </nav>
        <div className={`health health-${health}`}>
          <span className="health-dot" />
          {health === "online" ? `知识库在线 · ${articleCount} 条法规` : health === "offline" ? "后端未连接" : "正在连接"}
        </div>
      </header>

      <main id="top">
        {page === "analysis" ? (
          <>
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

            <div className="example-options" aria-label="示例问题详细程度">
              <span>示例生成</span>
              <button
                className={exampleDetailLevel === "brief" ? "active" : ""}
                type="button"
                onClick={() => changeExampleDetailLevel("brief")}
                disabled={isWorking || submitting || examplesLoading}
              >
                简短问题
              </button>
              <button
                className={exampleDetailLevel === "detailed" ? "active" : ""}
                type="button"
                onClick={() => changeExampleDetailLevel("detailed")}
                disabled={isWorking || submitting || examplesLoading}
              >
                详细案情
              </button>
            </div>

            <div className="example-row" aria-label="示例问题">
              {examples.map((example, index) => (
                <button
                  type="button"
                  key={example.example_id}
                  title={example.question}
                  onClick={() => setQuestion(example.question)}
                  disabled={isWorking || submitting}
                >
                  示例 {index + 1} · {example.category}
                </button>
              ))}
              <button
                className="refresh-examples"
                type="button"
                onClick={() => void loadExamples(exampleDetailLevel)}
                disabled={isWorking || submitting || examplesLoading}
              >
                {examplesLoading ? "生成中…" : "换一批"}
              </button>
            </div>

            <label className="field-label" htmlFor="as-of-date">
              案件发生日期 <span>可选</span>
            </label>
            <div className="date-field">
              <input
                id="as-of-date"
                type="date"
                value={asOfDate}
                onChange={(event) => setAsOfDate(event.target.value)}
                disabled={isWorking || submitting}
              />
              <div>
                <strong>{asOfDate || "按当前日期检索"}</strong>
                <small>系统会先筛选该日有效的法规版本，再进行关键词与向量召回。</small>
              </div>
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
                  <div className={`engine-badge engine-${status.execution_engine}`}>
                    {status.execution_engine === "llm"
                      ? `智能 Agent · ${status.model || "LLM"}`
                      : status.execution_engine === "fallback"
                        ? "Agent 已降级 · 离线规则"
                        : status.execution_engine === "rules"
                          ? "离线规则引擎 · 未调用模型"
                          : status.mode === "agent" ? "正在连接智能 Agent" : "正在执行离线规则"}
                  </div>
                  <div className="law-date-badge">
                    法规适用时点 · {status.as_of_date || "当前日期"}
                  </div>
                  <a className="monitoring-link" href="#monitoring">
                    Trace {status.trace_id.slice(0, 12)}… · 查看耗时与费用
                  </a>
                  <div className="progress-track"><i style={{ width: `${status.progress}%` }} /></div>
                </div>
                {pendingAction?.action?.type === "clarification" && (
                  <form className="clarification-card" onSubmit={submitAnswers}>
                    <div className="clarification-heading">
                      <div>
                        <span>需要你的补充</span>
                        <strong>第 {pendingAction.action.round} / {pendingAction.action.max_rounds} 轮追问</strong>
                      </div>
                      <small>回答会保存到当前任务，并从原进度继续。</small>
                    </div>
                    <div className="clarification-fields">
                      {pendingAction.action.questions.map((item, index) => (
                        <label key={item.question_id}>
                          <span>{index + 1}. {item.prompt}</span>
                          {item.missing_field && <small>待补充：{item.missing_field}</small>}
                          <textarea
                            value={clarificationAnswers[item.question_id] || ""}
                            onChange={(event) => setClarificationAnswers((current) => ({
                              ...current,
                              [item.question_id]: event.target.value.slice(0, 5000)
                            }))}
                            placeholder="请输入你知道的事实，不需要猜测"
                            disabled={clarificationSubmitting}
                          />
                          <button
                            type="button"
                            onClick={() => setClarificationAnswers((current) => ({
                              ...current,
                              [item.question_id]: "暂不清楚"
                            }))}
                            disabled={clarificationSubmitting}
                          >
                            暂不清楚
                          </button>
                        </label>
                      ))}
                    </div>
                    <button
                      className="clarification-submit"
                      type="submit"
                      disabled={clarificationSubmitting}
                    >
                      {clarificationSubmitting ? "正在恢复…" : "提交并继续分析"}<span>→</span>
                    </button>
                  </form>
                )}
                {pendingAction?.action?.type === "approval" && (
                  <section className="approval-card" aria-label="报告人工审批">
                    <div className="approval-heading">
                      <div>
                        <span>等待人工审批</span>
                        <strong>报告版本 V{pendingAction.action.report_version}</strong>
                      </div>
                      <small>批准前只能查看草稿，最终报告下载会被后端拒绝。</small>
                    </div>
                    <div className="approval-draft-summary">
                      <strong>{pendingAction.action.title}</strong>
                      <span>{pendingAction.action.change_summary || "Agent 生成的初始草稿"}</span>
                    </div>
                    <label>
                      <span>审核人</span>
                      <input
                        value={approvalReviewer}
                        onChange={(event) => setApprovalReviewer(event.target.value.slice(0, 100))}
                        disabled={approvalSubmitting}
                      />
                    </label>
                    <label>
                      <span>审批意见</span>
                      <textarea
                        value={approvalComment}
                        onChange={(event) => setApprovalComment(event.target.value.slice(0, 5000))}
                        placeholder="批准时可选；要求修改或驳回时必填"
                        disabled={approvalSubmitting}
                      />
                    </label>
                    <div className="approval-actions">
                      <button
                        className="approve"
                        type="button"
                        onClick={() => void handleApproval("approve")}
                        disabled={approvalSubmitting}
                      >
                        批准并发布
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleApproval("request_changes")}
                        disabled={approvalSubmitting}
                      >
                        要求修改
                      </button>
                      <button
                        className="reject"
                        type="button"
                        onClick={() => void handleApproval("reject")}
                        disabled={approvalSubmitting}
                      >
                        驳回报告
                      </button>
                    </div>
                  </section>
                )}
                <ol className="timeline">
                  {timelineNodes.map(({ node, label }, index) => {
                    const matchingTraces = status.traces.filter((item) => item.node === node);
                    const trace = matchingTraces.at(-1);
                    const active = status.current_node === node
                      && status.status !== "waiting_for_user"
                      && (!trace || node === "analyze_case");
                    const waiting = (
                      (node === "clarify_user" && status.status === "waiting_for_user")
                      || (node === "approve_report" && status.status === "waiting_for_approval")
                    );
                    return (
                      <li key={node} className={trace ? "done" : active || waiting ? "active" : "pending"}>
                        <span className="timeline-index">{trace ? "✓" : index + 1}</span>
                        <div>
                          <strong>{label}</strong>
                          <small>{trace?.action_summary || (waiting ? "等待你的回答…" : active ? "正在执行…" : "等待执行")}</small>
                        </div>
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
              <div>
                <span className="kicker">
                  {report.is_final
                    ? `已批准最终报告 · V${report.version_number}`
                    : report.approval_status === "rejected"
                      ? `已驳回报告 · V${report.version_number}`
                      : `待审批草稿 · V${report.version_number}`}
                </span>
                <h2>{report.title}</h2>
                <p>
                  {report.is_final
                    ? "当前版本已通过人工审批，可下载最终报告；正式使用前仍需核对权威来源。"
                    : "当前内容仅为报告草稿，可以查看和审核，但不能下载为最终报告。"}
                </p>
                <span className="report-law-date">
                  法规检索时点：{report.as_of_date || "当前日期"}
                </span>
              </div>
              <div className="result-actions">
                {report.is_final ? (
                  <>
                    <a href={exportUrl(report.run_id, "markdown")}>下载 Markdown</a>
                    <a className="filled" href={exportUrl(report.run_id, "pdf")}>下载 PDF</a>
                  </>
                ) : (
                  <span className="draft-download-lock">审批通过后开放下载</span>
                )}
                <button type="button" onClick={reset}>分析新案件</button>
              </div>
            </div>
            <div className="result-grid">
              <article className="report-paper">
                <ReactMarkdown>{selectedVersion?.markdown || report.markdown}</ReactMarkdown>
                {selectedVersion?.diff_from_previous && (
                  <section className="version-diff">
                    <h3>与上一版本的差异</h3>
                    <pre>{selectedVersion.diff_from_previous}</pre>
                  </section>
                )}
              </article>
              <aside className="evidence-panel">
                <div className="version-history">
                  <div className="evidence-title">
                    <span>报告版本</span><strong>{reportVersions.length}</strong>
                  </div>
                  {reportVersions.map((version) => (
                    <button
                      type="button"
                      key={version.version_number}
                      className={selectedVersion?.version_number === version.version_number ? "active" : ""}
                      onClick={() => void loadVersionDetail(version.version_number)}
                    >
                      <strong>V{version.version_number}</strong>
                      <span>{version.status === "approved"
                        ? "已批准"
                        : version.status === "superseded"
                          ? "已被新版本替代"
                          : version.status === "rejected"
                            ? "已驳回"
                            : "待审批"}</span>
                      <small>{version.change_summary || "初始报告草稿"}</small>
                    </button>
                  ))}
                  {selectedVersion && (
                    <button
                      type="button"
                      className="clear-version"
                      onClick={() => setSelectedVersion(null)}
                    >
                      返回当前版本
                    </button>
                  )}
                </div>
                <div className="evidence-title"><span>已审核依据</span><strong>{citations.filter((item) => item.verified).length} / {citations.length}</strong></div>
                {citations.map((citation) => (
                  <button type="button" key={citation.article_id} className={`citation-card ${citation.verified ? "verified" : "unverified"}`} onClick={() => setSelectedCitation(citation)}>
                    <span className="citation-status">{citation.verified ? "已核验" : "低置信度"}</span>
                    <span className={`law-effect-badge effect-${citation.effect_status}`}>
                      {lawEffectLabel(citation)}
                    </span>
                    <strong>{citation.law_name}</strong>
                    <b>{citation.article_number}</b>
                    <small className="citation-version">{citation.version_label}</small>
                    <small>综合相关度 {(citation.score * 100).toFixed(1)}%</small>
                  </button>
                ))}
                <div className="notice-box">{report.notice}</div>
              </aside>
            </div>
          </section>
        )}
          </>
        ) : page === "knowledge" ? (
          <KnowledgePage backendOnline={health === "online"} onArticlesCreated={onArticlesCreated} />
        ) : (
          <MonitoringPage backendOnline={health === "online"} activeRunId={runId} />
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
            <div className={`drawer-law-version effect-${selectedCitation.effect_status}`}>
              <strong>{lawEffectLabel(selectedCitation)}</strong>
              <span>{selectedCitation.version_label}</span>
            </div>
            <p className="article-text">{selectedCitation.excerpt}</p>
            <dl>
              <div><dt>法规版本 ID</dt><dd>{selectedCitation.law_version_id || "未标注"}</dd></div>
              <div><dt>版本适用区间</dt><dd>{lawValidity(selectedCitation)}</dd></div>
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
