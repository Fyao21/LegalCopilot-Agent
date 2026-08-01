import { ChangeEvent, FormEvent, useRef, useState } from "react";
import {
  createKnowledgeArticle,
  createKnowledgeArticleBatch,
  normalizeKnowledgeArticle
} from "./api";
import type {
  KnowledgeBatchResponse,
  KnowledgeNormalizationResponse,
  LegalArticle,
  LegalArticleCreate
} from "./types";

const MAX_TEXT_FILE_BYTES = 1024 * 1024;
const MAX_BATCH_FILES = 200;
const MAX_BATCH_FILE_BYTES = 128 * 1024;
const emptyForm: LegalArticleCreate = {
  law_name: "",
  article_number: "",
  content: "",
  source: ""
};

interface KnowledgePageProps {
  backendOnline: boolean;
  onArticlesCreated: (count: number) => void;
}

interface BatchPreview {
  file: File;
  lawName: string;
  articleNumber: string;
  source: string;
  contentLength: number;
  error: string | null;
}

async function parseBatchPreview(file: File): Promise<BatchPreview> {
  const base = {
    file,
    lawName: "",
    articleNumber: "",
    source: "",
    contentLength: 0
  };
  if (!file.name.toLowerCase().endsWith(".txt")) {
    return { ...base, error: "仅支持 TXT" };
  }
  if (file.size === 0) {
    return { ...base, error: "文件为空" };
  }
  if (file.size > MAX_BATCH_FILE_BYTES) {
    return { ...base, error: "超过 128 KB" };
  }
  try {
    const text = (await file.text()).replace(/\r\n?/g, "\n").replace(/\n+$/, "");
    const lines = text.split("\n");
    if (lines.length < 4) {
      return { ...base, error: "不足四行" };
    }
    const lawName = lines[0].trim();
    const articleNumber = lines[1].trim();
    const source = lines[2].trim();
    const content = lines.slice(3).join("\n").trim();
    let error: string | null = null;
    if (lawName.length < 2 || lawName.length > 200) error = "法律名称长度错误";
    else if (!articleNumber || articleNumber.length > 64) error = "条号长度错误";
    else if (source.length < 2 || source.length > 500) error = "来源长度错误";
    else if (content.length < 2 || content.length > 20000) error = "正文长度错误";
    return { file, lawName, articleNumber, source, contentLength: content.length, error };
  } catch {
    return { ...base, error: "读取失败，请使用 UTF-8" };
  }
}

interface BatchUploaderProps {
  backendOnline: boolean;
  onCreated: (count: number) => void;
}

function BatchUploader({ backendOnline, onCreated }: BatchUploaderProps) {
  const [previews, setPreviews] = useState<BatchPreview[]>([]);
  const [result, setResult] = useState<KnowledgeBatchResponse | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const selectFiles = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    setResult(null);
    if (files.length > MAX_BATCH_FILES) {
      setPreviews([]);
      setError(`每批最多选择 ${MAX_BATCH_FILES} 个文件。`);
      return;
    }
    setError("");
    setPreviews(await Promise.all(files.map(parseBatchPreview)));
  };

  const uploadBatch = async () => {
    if (!previews.length) {
      setError("请先选择 TXT 文件。");
      return;
    }
    setSubmitting(true);
    setError("");
    setResult(null);
    try {
      const response = await createKnowledgeArticleBatch(previews.map((item) => item.file));
      setResult(response);
      onCreated(response.created_count);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "批量上传失败");
    } finally {
      setSubmitting(false);
    }
  };

  const invalidCount = previews.filter((item) => item.error).length;

  return (
    <div className="batch-uploader">
      <details className="batch-rules" open>
        <summary>
          <span>
            <strong>批量 TXT 格式与导入规则</strong>
            <small>上传前请先检查，每个文件只对应一条法律条文</small>
          </span>
          <b>展开 / 收起</b>
        </summary>
        <div className="batch-rules-content">
          <div className="batch-format">
            <div><span>第 1 行</span><strong>法律名称</strong><small>2～200 字符</small></div>
            <div><span>第 2 行</span><strong>条号</strong><small>1～64 字符</small></div>
            <div><span>第 3 行</span><strong>来源</strong><small>2～500 字符</small></div>
            <div><span>第 4 行起</span><strong>条文正文</strong><small>2～20000 字符，可多行</small></div>
          </div>

          <div className="batch-rule-grid">
            <section>
              <strong>文件要求</strong>
              <ul>
                <li>只接收 UTF-8 编码的 <code>.txt</code>，允许 UTF-8 BOM。</li>
                <li>一份文件只能放一个明确条号，字段之间不能增加空行。</li>
                <li>一次最多 200 个；单个不超过 128 KB；整批不超过 8 MB。</li>
                <li>文件名不限，但建议使用“法律简称_条号.txt”方便排错。</li>
              </ul>
            </section>
            <section>
              <strong>校验与判重</strong>
              <ul>
                <li>浏览器先预检查，后端会重新读取并校验全部字段。</li>
                <li>按照“法律名称 + 条号”判重，数据库已有或本批重复都会跳过。</li>
                <li>单个错误文件不会阻断其他合法文件，结果会逐文件返回。</li>
                <li>非固定格式的 TXT 请先使用旁边的“Agent 整理”。</li>
              </ul>
            </section>
          </div>

          <div className="batch-example">
            <div>
              <strong>标准文件示例</strong>
              <span>复制时不要包含左侧行号</span>
            </div>
            <pre><code>{`中华人民共和国食品安全法
第四条
国家法律法规数据库
食品生产经营者对其生产经营食品的安全负责。
正文需要分段时，可以从第五行继续。`}</code></pre>
          </div>

          <div className="batch-status-guide">
            <span><b>新增成功</b> 已入库并建立索引</span>
            <span><b>重复跳过</b> 原记录保持不变</span>
            <span><b>格式错误</b> 未写入数据库</span>
          </div>
        </div>
      </details>

      <input ref={inputRef} type="file" accept=".txt,text/plain" multiple onChange={selectFiles} hidden />
      <button
        type="button"
        className="batch-dropzone"
        onClick={() => inputRef.current?.click()}
        disabled={submitting}
      >
        <span className="upload-symbol">＋</span>
        <strong>选择多个 TXT 文件</strong>
        <small>一次最多 200 个 · 单个 128 KB · 总计 8 MB · UTF-8 编码</small>
      </button>

      {previews.length > 0 && (
        <>
          <div className="batch-summary">
            <strong>已选择 {previews.length} 个文件</strong>
            <span className={invalidCount ? "has-invalid" : ""}>
              {invalidCount ? `${invalidCount} 个预检查异常，后端仍会逐个复核` : "全部通过浏览器预检查"}
            </span>
            <button type="button" onClick={() => { setPreviews([]); setResult(null); }}>清空</button>
          </div>
          <div className="batch-preview-list">
            {previews.map((item, index) => (
              <div className={`batch-preview-item ${item.error ? "invalid" : ""}`} key={`${item.file.name}-${index}`}>
                <span>{item.error ? "!" : "✓"}</span>
                <div>
                  <strong>{item.file.name}</strong>
                  <small>
                    {item.error
                      ? item.error
                      : `${item.lawName} · ${item.articleNumber} · 正文 ${item.contentLength} 字`}
                  </small>
                </div>
              </div>
            ))}
          </div>
          <div className="knowledge-submit-row">
            <p>前端预检查只用于提示；后端会重新解析、校验并按“法律名称 + 条号”判重。</p>
            <button
              className="primary-button"
              type="button"
              onClick={uploadBatch}
              disabled={submitting || !backendOnline}
            >
              {submitting ? "正在批量处理…" : backendOnline ? `上传 ${previews.length} 个文件` : "后端未连接"}
              <span>→</span>
            </button>
          </div>
        </>
      )}

      {error && <div className="error-banner" role="alert"><strong>批量上传失败</strong><span>{error}</span></div>}
      {result && (
        <div className="batch-result" role="status">
          <div className="batch-result-counts">
            <div><strong>{result.created_count}</strong><span>新增成功</span></div>
            <div><strong>{result.duplicate_count}</strong><span>重复跳过</span></div>
            <div><strong>{result.invalid_count}</strong><span>格式错误</span></div>
          </div>
          <div className="batch-result-list">
            {result.items.map((item, index) => (
              <div className={`result-${item.status}`} key={`${item.filename}-${index}`}>
                <strong>{item.filename}</strong>
                <span>{item.law_name && item.article_number ? `${item.law_name} · ${item.article_number}` : item.message}</span>
                <b>{item.status === "created" ? `ARTICLE #${item.article_id}` : item.status === "duplicate" ? "已跳过" : "未导入"}</b>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

interface AgentNormalizerProps {
  backendOnline: boolean;
  onUseDraft: (draft: KnowledgeNormalizationResponse) => void;
}

function AgentNormalizer({ backendOnline, onUseDraft }: AgentNormalizerProps) {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<KnowledgeNormalizationResponse | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const selectFile = (event: ChangeEvent<HTMLInputElement>) => {
    const selected = event.target.files?.[0] || null;
    event.target.value = "";
    setResult(null);
    setError("");
    if (!selected) return;
    if (!selected.name.toLowerCase().endsWith(".txt")) {
      setFile(null);
      setError("智能整理仅支持 TXT 文件。");
      return;
    }
    if (selected.size === 0) {
      setFile(null);
      setError("不能上传空文件。");
      return;
    }
    if (selected.size > MAX_BATCH_FILE_BYTES) {
      setFile(null);
      setError("智能整理的 TXT 不能超过 128 KB。");
      return;
    }
    setFile(selected);
  };

  const normalize = async () => {
    if (!file) {
      setError("请先选择一份排版不固定的 TXT。");
      return;
    }
    setSubmitting(true);
    setError("");
    setResult(null);
    try {
      setResult(await normalizeKnowledgeArticle(file));
    } catch (normalizeError) {
      setError(normalizeError instanceof Error ? normalizeError.message : "Agent 整理失败");
    } finally {
      setSubmitting(false);
    }
  };

  const download = () => {
    if (!result) return;
    const blob = new Blob([`\ufeff${result.standardized_text}`], {
      type: "text/plain;charset=utf-8"
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = result.standardized_filename;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="agent-normalizer">
      <div className="normalizer-intro">
        <strong>让模型识别任意排版</strong>
        <p>上传一份只包含一条法规的 UTF-8 TXT。模型只做字段提取和排版，不允许补写正文；整理结果必须人工核对后再入库。</p>
      </div>
      <input ref={inputRef} type="file" accept=".txt,text/plain" onChange={selectFile} hidden />
      <button
        type="button"
        className="batch-dropzone"
        onClick={() => inputRef.current?.click()}
        disabled={submitting}
      >
        <span className="upload-symbol">✦</span>
        <strong>{file ? file.name : "选择任意排版的 TXT"}</strong>
        <small>{file ? `${(file.size / 1024).toFixed(1)} KB · 可以开始整理` : "单文件 128 KB · UTF-8 · 一份文件对应一条法规"}</small>
      </button>
      <div className="knowledge-submit-row">
        <p>需要在线 LLM。缺少字段时会保留“待补充”标记，不会自动写入数据库。</p>
        <button
          className="primary-button"
          type="button"
          onClick={normalize}
          disabled={submitting || !backendOnline || !file}
        >
          {submitting ? "Agent 正在整理…" : backendOnline ? "开始智能整理" : "后端未连接"}
          <span>→</span>
        </button>
      </div>
      {error && <div className="error-banner" role="alert"><strong>整理失败</strong><span>{error}</span></div>}
      {result && (
        <div className="normalizer-result" role="status">
          <div className="normalizer-status-row">
            <div>
              <small>模型</small>
              <strong>{result.model}</strong>
            </div>
            <div>
              <small>置信度</small>
              <strong>{Math.round(result.confidence * 100)}%</strong>
            </div>
            <span className={result.ready_for_import ? "ready" : "needs-review"}>
              {result.ready_for_import ? "字段齐全，仍需人工核对" : "存在缺失或多条内容"}
            </span>
          </div>
          <div className="normalizer-fields">
            <div><span>法律名称</span><strong>{result.law_name || "待补充"}</strong></div>
            <div><span>条号</span><strong>{result.article_number || "待补充"}</strong></div>
            <div><span>来源</span><strong>{result.source || "待补充"}</strong></div>
            <div><span>正文</span><strong>{result.content.length} 字</strong></div>
          </div>
          {result.warnings.length > 0 && (
            <div className="normalizer-warnings">
              <strong>人工核对提示</strong>
              <ul>{result.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
            </div>
          )}
          <label className="knowledge-field">
            <span>标准四行 TXT 预览</span>
            <textarea value={result.standardized_text} readOnly />
          </label>
          <div className="normalizer-actions">
            <button type="button" onClick={download}>下载标准 TXT</button>
            <button type="button" className="primary-button" onClick={() => onUseDraft(result)}>
              填入单条录入并核对 <span>→</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function KnowledgePage({ backendOnline, onArticlesCreated }: KnowledgePageProps) {
  const [entryMode, setEntryMode] = useState<"single" | "batch" | "agent">("single");
  const [form, setForm] = useState<LegalArticleCreate>(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [draftNotice, setDraftNotice] = useState("");
  const [created, setCreated] = useState<LegalArticle | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const updateField = (field: keyof LegalArticleCreate, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
    setError("");
    setDraftNotice("");
    setCreated(null);
  };

  const importTextFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const selected = event.target.files?.[0];
    event.target.value = "";
    if (!selected) return;
    if (!selected.name.toLowerCase().endsWith(".txt")) {
      setError("正文导入仅支持 TXT 文件。");
      return;
    }
    if (selected.size === 0) {
      setError("不能导入空文件。");
      return;
    }
    if (selected.size > MAX_TEXT_FILE_BYTES) {
      setError("TXT 文件不能超过 1 MB。请按单条法律条文拆分后再导入。");
      return;
    }
    try {
      const text = (await selected.text()).trim();
      if (text.length < 2) {
        setError("文件中没有可用的条文正文。");
        return;
      }
      if (text.length > 20000) {
        setError("单条正文不能超过 20000 个字符，请拆分后录入。");
        return;
      }
      updateField("content", text);
    } catch {
      setError("读取 TXT 文件失败，请确认文件编码为 UTF-8，或手工粘贴正文。");
    }
  };

  const validate = (): string | null => {
    if (form.law_name.trim().length < 2) return "法律名称至少需要 2 个字符。";
    if (!form.article_number.trim()) return "请填写条号，例如“第五百七十七条”。";
    if (form.content.trim().length < 2) return "请填写完整的法律条文正文。";
    if (form.source.trim().length < 2) return "请填写法规来源或权威来源地址。";
    return null;
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const validation = validate();
    if (validation) {
      setError(validation);
      return;
    }
    setSubmitting(true);
    setError("");
    setDraftNotice("");
    setCreated(null);
    try {
      const article = await createKnowledgeArticle({
        law_name: form.law_name.trim(),
        article_number: form.article_number.trim(),
        content: form.content.trim(),
        source: form.source.trim()
      });
      setCreated(article);
      onArticlesCreated(1);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "法规保存失败");
    } finally {
      setSubmitting(false);
    }
  };

  const continueSameLaw = () => {
    setForm((current) => ({ ...current, article_number: "", content: "" }));
    setCreated(null);
    setError("");
    setDraftNotice("");
  };

  const resetAll = () => {
    setForm(emptyForm);
    setCreated(null);
    setError("");
    setDraftNotice("");
  };

  const useNormalizedDraft = (draft: KnowledgeNormalizationResponse) => {
    setForm({
      law_name: draft.law_name || "",
      article_number: draft.article_number || "",
      source: draft.source || "",
      content: draft.content
    });
    setCreated(null);
    setEntryMode("single");
    setError("");
    setDraftNotice(
      draft.ready_for_import
        ? "Agent 已填入整理结果。保存前请逐项核对名称、条号、来源和正文。"
        : `Agent 已填入草稿，但仍缺少：${draft.missing_fields.join("、") || "多条内容需要拆分"}。`
    );
  };

  return (
    <>
      <section className="knowledge-hero">
        <div>
          <span className="eyebrow">KNOWLEDGE BASE MANAGEMENT</span>
          <h1>录入可信法规，<br /><em>扩展检索依据。</em></h1>
          <p>按单条法律条文录入名称、条号、正文和来源。保存后系统会立即建立检索向量，无需重启后端。</p>
        </div>
        <div className="knowledge-hero-note">
          <strong>录入原则</strong>
          <span>一条记录对应一个明确条号</span>
          <span>正文必须来自可核验的权威来源</span>
          <span>正式使用前确认法规现行有效</span>
        </div>
      </section>

      <section className="knowledge-workspace" aria-label="知识库法规录入">
        <form className="knowledge-form-card" onSubmit={submit}>
          <div className="section-number">03</div>
          <div className="section-heading">
            <div>
              <span className="kicker">知识库管理</span>
              <h2>
                {entryMode === "single"
                  ? "新增法律条文"
                  : entryMode === "batch"
                    ? "批量导入法律条文"
                    : "Agent 智能整理 TXT"}
              </h2>
            </div>
            <span className="privacy-note">保存后立即进入检索库</span>
          </div>

          <div className="knowledge-mode-switch" role="tablist" aria-label="法规录入方式">
            <button
              type="button"
              role="tab"
              aria-selected={entryMode === "single"}
              className={entryMode === "single" ? "active" : ""}
              onClick={() => setEntryMode("single")}
            >
              单条录入
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={entryMode === "batch"}
              className={entryMode === "batch" ? "active" : ""}
              onClick={() => setEntryMode("batch")}
            >
              批量 TXT
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={entryMode === "agent"}
              className={entryMode === "agent" ? "active" : ""}
              onClick={() => setEntryMode("agent")}
            >
              Agent 整理
            </button>
          </div>

          {entryMode === "single" ? (
            <>
          <div className="knowledge-field-grid">
            <label className="knowledge-field">
              <span>法律名称 <b>必填</b></span>
              <input
                value={form.law_name}
                onChange={(event) => updateField("law_name", event.target.value.slice(0, 200))}
                placeholder="例如：中华人民共和国民法典"
                disabled={submitting}
              />
              <small>{form.law_name.length} / 200</small>
            </label>
            <label className="knowledge-field">
              <span>条号 <b>必填</b></span>
              <input
                value={form.article_number}
                onChange={(event) => updateField("article_number", event.target.value.slice(0, 64))}
                placeholder="例如：第五百七十七条"
                disabled={submitting}
              />
              <small>{form.article_number.length} / 64</small>
            </label>
          </div>

          <label className="knowledge-field">
            <span>法规来源 <b>必填</b></span>
            <input
              value={form.source}
              onChange={(event) => updateField("source", event.target.value.slice(0, 500))}
              placeholder="例如：国家法律法规数据库 https://flk.npc.gov.cn/"
              disabled={submitting}
            />
            <small>{form.source.length} / 500</small>
          </label>

          <div className="content-label-row">
            <label className="field-label" htmlFor="article-content">条文正文 <span>必填</span></label>
            <button type="button" className="text-import-button" onClick={() => fileInputRef.current?.click()} disabled={submitting}>
              从 TXT 导入
            </button>
            <input ref={fileInputRef} type="file" accept=".txt,text/plain" onChange={importTextFile} hidden />
          </div>
          <textarea
            id="article-content"
            className="article-content-input"
            value={form.content}
            onChange={(event) => updateField("content", event.target.value.slice(0, 20000))}
            placeholder="粘贴该条法律条文的完整原文。不要把多条法规合并在一条记录中。"
            disabled={submitting}
          />
          <div className="textarea-meta">
            <span>支持手工粘贴或 UTF-8 TXT 文件；单条记录最多 20000 字</span>
            <span>{form.content.length} / 20000</span>
          </div>

          <div className="knowledge-submit-row">
            <p>系统按“法律名称 + 条号”判重；重复记录不会覆盖数据库原文。</p>
            <button className="primary-button" type="submit" disabled={submitting || !backendOnline}>
              {submitting ? "正在保存…" : backendOnline ? "保存并建立索引" : "后端未连接"}<span>→</span>
            </button>
          </div>

          {draftNotice && (
            <div className="knowledge-notice" role="status">
              <strong>Agent 整理结果已填入</strong>
              <span>{draftNotice}</span>
            </div>
          )}
          {error && <div className="error-banner" role="alert"><strong>未能保存法规</strong><span>{error}</span></div>}
          {created && (
            <div className="knowledge-success" role="status">
              <span className="success-mark">✓</span>
              <div>
                <small>法规已保存并可立即检索</small>
                <strong>{created.law_name} · {created.article_number}</strong>
                <p>ARTICLE #{created.article_id}</p>
              </div>
              <div className="success-actions">
                <button type="button" onClick={continueSameLaw}>继续添加本法条文</button>
                <button type="button" onClick={resetAll}>录入其他法律</button>
              </div>
            </div>
          )}
            </>
          ) : entryMode === "batch" ? (
            <BatchUploader backendOnline={backendOnline} onCreated={onArticlesCreated} />
          ) : (
            <AgentNormalizer backendOnline={backendOnline} onUseDraft={useNormalizedDraft} />
          )}
        </form>

        <aside className="knowledge-guide-card">
          <span className="kicker">录入检查</span>
          <h2>四步保证数据可追溯</h2>
          <ol>
            <li><span>01</span><div><strong>核对名称</strong><p>使用法规正式全称，不使用含糊简称。</p></div></li>
            <li><span>02</span><div><strong>拆分条文</strong><p>每次只录入一个条号，便于精准引用。</p></div></li>
            <li><span>03</span><div><strong>保留来源</strong><p>优先填写国家法律法规数据库或中国人大网地址。</p></div></li>
            <li><span>04</span><div><strong>检查效力</strong><p>确认公布、施行和修订状态，教学数据也要明确标注。</p></div></li>
          </ol>
          <div className="admin-warning">
            <strong>当前是本地演示管理页</strong>
            <p>批量导入会真实写入数据库。知识库写接口尚未加入管理员认证，请勿直接暴露到公网。</p>
          </div>
        </aside>
      </section>
    </>
  );
}

export default KnowledgePage;
