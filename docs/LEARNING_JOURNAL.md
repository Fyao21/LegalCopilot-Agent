# 律镜 Legal Copilot Agent 学习文档与开发日志

## 文档定位

这份文档面向项目作者本人，用于学习项目实现、准备简历和应对技术面试。它和 README 的区别是：README 解决“别人如何启动项目”，本文件解决“我为什么这样设计、代码如何工作、面试时怎么解释”。

文档采用追加式维护。从第三周开始，每完成一组功能就在文件末尾增加新的日期章节，不覆盖之前的学习记录。这样可以保留项目从简单基线演进为完整 Agent 系统的过程，这个演进过程本身也是面试时很有价值的内容。

## 学习方法

建议按以下顺序学习：

1. 先运行项目和接口，不急着阅读全部代码。
2. 从 `app/main.py` 找到一个接口入口。
3. 顺着函数调用查看 service、workflow、model 和 schema。
4. 查看对应测试，理解正常与异常输入的预期行为。
5. 用自己的话复述设计原因，不要只背代码。
6. 修改一个小参数并重新测试，例如 Top-K、检索权重或最大重试次数。
7. 最后阅读面试问答，尝试脱离文档回答。

---

# 2026-07-21：第一周——建立可独立运行的后端与检索基线

## 1. 第一周解决了什么问题

旧项目虽然有多个 Agent，但存在几个不利于求职展示的问题：模块目录包含空格，需要动态导入；法条搜索主要依赖模型记忆；GUI 与核心逻辑耦合；缺少可量化测试；运行需要多个模型服务。

第一周没有直接追求“大模型效果”，而是先建立一个稳定的软件工程底座：

- 项目可以离开旧仓库独立运行；
- 没有 API Key 也可以演示；
- 输入、数据库、检索、API 和测试形成完整闭环；
- 后续加入 Agent 时不会破坏离线基线。

这个顺序很重要。面试官通常更关心系统能否稳定运行、能否测试、失败如何处理，而不是代码里写了几个名为 Agent 的类。

## 2. 第一周项目结构

```text
LegalCopilot-Agent/
├─ app/
│  ├─ main.py                 FastAPI 入口和接口
│  ├─ config.py               环境与路径配置
│  ├─ database.py             SQLAlchemy 引擎和 Session
│  ├─ models.py               数据库表
│  ├─ schemas.py              请求与响应结构
│  └─ services/
│     ├─ document_parser.py   TXT/DOCX/PDF 解析
│     ├─ case_analyzer.py     规则案件分析
│     ├─ embeddings.py        离线哈希向量
│     ├─ retriever.py         第一版向量检索
│     └─ seed.py              样例法规初始化
├─ data/sample_laws.jsonl     项目自己的教学法规
├─ tests/                     自动测试
└─ scripts/run_self_test.py   统一自测入口
```

## 3. 为什么先使用 FastAPI

FastAPI 适合这个项目的原因：

1. Python 生态与 LLM、文档解析、RAG 工具兼容良好。
2. 类型标注和 Pydantic 可以自动进行请求校验。
3. 自动生成 OpenAPI 和 Swagger，方便演示和导入 Apifox。
4. API 层容易与未来 React 前端、任务队列分离。

`app/main.py` 中的 `app = FastAPI(...)` 创建应用。装饰器如 `@app.get`、`@app.post` 将 URL、HTTP 方法和 Python 函数绑定起来。

面试回答要点：FastAPI 不只是“速度快”，更重要的是类型驱动、自动文档和适合异步 I/O。当前工作流仍然同步，第三周才会真正发挥异步接口的价值。

## 4. 为什么使用 Pydantic Schema

`app/schemas.py` 描述了系统允许接收和返回的数据，例如 `CaseFacts`：

```text
case_type            案件类型
parties              当事人
key_facts            关键事实
claims               用户诉求
dispute_focuses      争议焦点
missing_information  缺失信息
questions_for_user   需要确认的问题
```

Schema 的价值：

- API 输出结构稳定，前端不需要猜字段；
- LLM 输出可以经过同一个 Schema 校验；
- 错误数据在进入数据库和业务逻辑前被拦截；
- OpenAPI 可以自动描述字段类型和约束。

一个常见错误是只在提示词中写“请返回 JSON”，然后直接 `json.loads`。JSON 语法正确不代表字段正确，仍需 Pydantic 验证字段、类型、范围和默认值。

## 5. 数据库是如何工作的

`app/database.py` 根据 `DATABASE_URL` 创建 SQLAlchemy Engine。默认地址指向项目内部：

```text
data/legal_copilot.db
```

`SessionLocal` 用于创建数据库会话。FastAPI 的 `get_db()` 使用生成器保证请求结束时关闭 Session。

第一周的主要表：

- `legal_articles`：法规条文和第一版向量；
- `case_runs`：兼容接口产生的案件记录；
- `retrieval_logs`：案件命中了哪些法规以及分数。

选择 SQLite 的原因：

- 求职项目可以直接运行，不要求面试官安装 MySQL；
- 单元测试可以使用内存数据库；
- SQLAlchemy 将数据库实现与业务层隔离；
- 后续仍可迁移 PostgreSQL 或 MySQL。

SQLite 不是最终生产方案。它的并发写能力有限，也没有原生向量索引。当前阶段选择它是为了降低启动成本，而不是认为它适合所有场景。

## 6. 启动时如何自动初始化数据

FastAPI 的 lifespan 会执行以下操作：

1. `Base.metadata.create_all(engine)` 创建不存在的表；
2. `seed_sample_laws(db)` 检查法规表是否为空；
3. 数据为空时读取 `data/sample_laws.jsonl`；
4. 生成本地向量并写入数据库；
5. 第二次启动发现已有数据后跳过导入。

这里体现了幂等性：同一个初始化操作执行多次，最终状态不会重复增长。

面试可能追问：“为什么不用数据库迁移工具？”回答：MVP 使用 `create_all` 降低复杂度；当表结构需要修改或进入团队开发时，应使用 Alembic 保存可追踪的升级和回滚脚本。

## 7. 文档解析流程

入口位于 `app/services/document_parser.py`。

流程：

```text
UploadFile
  ↓ 读取 bytes
根据扩展名分派
  ├─ TXT  → UTF-8 解码
  ├─ DOCX → python-docx 读取段落
  └─ PDF  → pypdf 逐页提取文本
  ↓
统一返回 str
```

为什么不支持旧版 `.doc`：它是二进制格式，跨平台解析经常依赖 Word、LibreOffice 或额外系统程序。MVP 明确拒绝比“偶尔成功、偶尔失败”更可靠。

为什么扫描 PDF 无法读取：`pypdf` 读取的是 PDF 中已有的文本层。如果 PDF 每页只是图片，需要 OCR，这是后续扩展点。

安全注意：扩展名检查只是第一层。第三周还应加入 MIME、文件头、文件大小、页数、解析时间和保存路径校验。

## 8. 规则案件分析基线

`app/services/case_analyzer.py` 不调用模型，而是通过关键词和正则表达式完成基础抽取。

例如：

- 出现“劳动、工资、加班”倾向劳动争议；
- 出现“合同、违约、货款”倾向合同纠纷；
- 使用“原告、被告、甲方、乙方”等标签提取当事人；
- 使用“请求、赔偿、支付、返还、解除”筛选诉求；
- 使用“争议、是否、违约、责任”筛选争议焦点。

规则方案明显不够智能，为什么还要保留：

1. 没有密钥时项目仍可运行；
2. 模型故障时可以降级；
3. 为评测提供基线；
4. 规则输出可重复，方便定位系统其他部分的问题。

这是工程中的 baseline 思维：先建立一个简单、可复现的最低效果，再证明复杂方案确实带来了提升。

## 9. 第一版离线向量

`app/services/embeddings.py` 实现中文二元字符哈希向量：

1. 删除空格并转为小写；
2. 将“合同违约赔偿”切成“合同、同违、违约、约赔、赔偿”；
3. 对每个片段计算 SHA-256；
4. 将结果映射到固定的 384 个维度；
5. 累加并进行 L2 归一化；
6. 使用余弦相似度计算接近程度。

余弦相似度的直观含义：比较两个向量方向是否接近。公式是：

```text
cos(A, B) = (A · B) / (||A|| × ||B||)
```

由于向量已经归一化，代码中可以直接计算点积。

这不是真正语义模型。它主要识别字符片段重合，无法很好理解同义词。但它无需网络、结果确定、速度快，适合作为第一版可运行基线。

## 10. 第一周 API 流程

以 `POST /api/v1/cases` 为例：

```text
接收 question 和 file
  ↓
解析文件文本
  ↓
规则提取 CaseFacts
  ↓
组合问题和争议焦点
  ↓
检索 Top-K 法规
  ↓
保存 CaseRun 和 RetrievalLog
  ↓
返回 run_id、facts、citations、notice
```

这条接口是同步接口，适合第一周快速验证。第三周会将长工作流改成“创建任务后立即返回 run_id，再轮询状态”。

## 11. 第一周如何测试

统一执行：

```powershell
python scripts\run_self_test.py
```

第一周测试覆盖：案件分类、TXT 解析、非法格式、向量相关性、健康检查、法规搜索和案件分析接口。

为什么脚本使用标准库 unittest：降低新环境测试门槛，不需要额外安装 pytest。项目后续仍可迁移 pytest，以使用 fixture、参数化和插件生态。

## 12. 第一周面试表达

可以这样介绍：

> 我先将原来的多模型 GUI 原型拆成独立 FastAPI 服务，以 SQLite 和离线检索建立可复现基线。系统支持案件文件解析、结构化要素提取、法规检索和引用返回，并通过自动测试保证无模型密钥时仍可运行。这为后续 Agent 编排和效果评测提供了稳定底座。

---

# 2026-07-21：第二周——从检索基线升级为可控 Agent 工作流

## 1. 第二周解决了什么问题

第一周只能返回案件要素和候选法条，缺少以下能力：

- 无法调用真实 LLM 进行更好的事实理解；
- 检索只有单一分数；
- 没有验证模型或检索结果中的法条是否真实；
- 没有清晰的多步骤状态和重试分支；
- 没有生成最终报告；
- 模型超时或返回错误 JSON 时没有统一回退机制。

第二周围绕“可控”展开。这里的 Agent 不是让模型自由决定一切，而是将模型放入受约束的工作流节点中。

## 2. 第二周新增结构

```text
app/
├─ llm/
│  └─ client.py                  OpenAI 兼容结构化 LLM 客户端
├─ services/
│  ├─ embedding_provider.py      Embedding 抽象与实现
│  ├─ embedding_index.py         多模型向量索引
│  ├─ legal_chunker.py           长法条切片
│  ├─ mixed_retriever.py         关键词 + 语义混合检索
│  ├─ case_agent.py              LLM 案件分析及规则回退
│  ├─ citation_reviewer.py       引用真实性和语义审核
│  └─ report_writer.py           报告草稿与 Markdown 渲染
├─ workflows/
│  └─ legal_report_graph.py      LangGraph 状态图
└─ models.py                     AgentRun 等新增表
```

## 3. 配置层与 Adapter 模式

真实项目不应让业务代码直接依赖某一家模型 SDK。当前项目定义了适配层：

- LLM 对外提供 `invoke_structured`；
- Embedding 对外提供 `embed_documents` 和 `embed_query`；
- 业务服务只依赖这些稳定方法。

好处：

1. 更换 DeepSeek、OpenAI 或其他兼容服务时不改业务节点；
2. 测试可以替换为 Fake 或 Mock；
3. 离线实现和真实实现可以共用一套调用方式；
4. 错误可以统一转换为项目自己的异常类型。

当前配置兼容两组变量：

```text
LLM_API_KEY      或 OPENAI_API_KEY
LLM_BASE_URL     或 OPENAI_BASE_URL
LLM_MODEL        或 MODEL_NAME
```

项目不会把真实密钥写进代码。`.env.example` 只包含占位符，真实值放在被 Git 忽略的 `.env`。

## 4. LLM 结构化输出与有限重试

`app/llm/client.py` 使用 OpenAI 兼容的 `/chat/completions` 接口。

一次调用包括：

1. system prompt 明确节点职责和 JSON 字段；
2. `response_format=json_object` 请求 JSON；
3. 提取代码块或正文中的 JSON 对象；
4. 使用 Pydantic Schema 校验；
5. 首次格式错误时请求模型修复一次；
6. 第二次仍失败则抛出 `LLM_INVALID_OUTPUT`；
7. 上层 Agent 捕获错误并回退规则方案。

为什么只能修复一次：无限重试会带来不可控的延迟、费用和死循环。明确的重试上限比“直到成功”为止更适合生产系统。

错误被分为：认证失败、限流、服务端错误、网络/超时、HTTP 错误和结构化输出错误。可重试错误只做有限重试，认证错误不重试。

## 5. 多 Embedding 索引设计

第一周把向量直接放在法规表中。第二周增加 `article_embeddings`：

```text
article_id
provider
model
dimensions
content_hash
vector
```

这允许同一条法规同时保存哈希向量和真实模型向量。

`content_hash` 用于判断正文是否变化：

- 正文和 provider/model 都不变：跳过计算；
- 正文变化：重新生成；
- 切换模型：生成一套新的索引；
- 重复执行脚本：不会重复写入。

这种能力叫幂等索引或增量索引。真实知识库可能有大量文档，不能每次启动都重新付费计算全部 Embedding。

索引命令：

```powershell
python scripts\reindex_embeddings.py
```

## 6. 为什么 Chat 模型与 Embedding 要分开配置

Chat 模型处理自然语言理解和生成；Embedding 模型把文本转换为向量。两者经常由不同服务提供。

不能因为某服务兼容 `/chat/completions`，就假设它一定支持 `/embeddings`。项目因此使用独立配置：

```text
LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
EMBEDDING_API_KEY / EMBEDDING_BASE_URL / EMBEDDING_MODEL
```

默认 `EMBEDDING_PROVIDER=hash`，即使启用 DeepSeek Chat，也不会错误地向 DeepSeek 地址发送 Embedding 请求。

## 7. 长法条切片

`app/services/legal_chunker.py` 对超长法条执行：

1. 清理空行；
2. 长度不超过阈值时保持整条；
3. 优先在换行、句号或分号边界切分；
4. 相邻切片保留少量重叠；
5. 每个切片保留原始条号和稳定 `chunk_index`。

重叠的意义：如果重要语义刚好位于切分边界，两边都保留一部分上下文，可以减少检索遗漏。

法律文本切片不能随意把不同条号混在一起，因为最终引用必须能准确回到具体法条。

## 8. 混合检索原理

`app/services/mixed_retriever.py` 同时计算：

- `keyword_score`：查询与法条二元片段的覆盖程度，并对法律名称、条号精确命中加分；
- `semantic_score`：查询向量与法规向量的余弦相似度；
- `score`：两种分数按权重融合。

公式：

```text
combined_score = keyword_weight × keyword_score
               + semantic_weight × semantic_score
```

默认权重：关键词 0.35，语义 0.65。配置层会自动归一化权重，避免用户填写的权重和不等于 1。

为什么不只用向量：法条号、法律名称和固定术语非常适合精确匹配。为什么不只用关键词：用户可能使用不同表述，真实 Embedding 更擅长理解语义接近。混合检索结合两者优势。

## 9. 案件分析 Agent

`app/services/case_agent.py` 的策略：

```text
有可用 LLM
  ↓
调用结构化案件抽取
  ├─ 成功 → source=llm
  └─ 失败 → 规则抽取，source=rules_fallback，并记录原因

无 LLM 或 offline
  ↓
规则抽取，source=rules
```

提示词明确要求“只能依据材料，不得补充事实”。Schema 增加置信度、缺失信息和待确认问题，以便模型承认材料不足，而不是强行生成完整故事。

## 10. LangGraph 状态设计

`WorkflowState` 是节点共享的数据结构，主要字段：

```text
run_id                 任务 ID
document_text           文件文本
question                用户问题
mode                    offline/agent
facts                   结构化案件事实
retrieval_query         实际检索查询
citations               候选引用
reviewed_citations      审核引用
retry_count             补充检索次数
traces                  节点轨迹
report_title            报告标题
report_markdown         Markdown 报告
evidence_gaps           证据缺口
model_name              实际模型
```

节点函数遵循 `State → Partial State`：读取当前状态，只返回需要更新的字段。这样每个节点职责清晰，方便单独测试和增加条件分支。

## 11. 工作流节点与条件边

当前状态图：

```text
START
  ↓
analyze_case
  ↓
retrieve_laws
  ↓
review_citations
  ├─ 有 verified 引用 ─────────→ write_report → END
  ├─ 无引用且 retry < 2 → retry_retrieval ─┐
  │                                         └→ retrieve_laws
  └─ 无引用且 retry = 2 ──────→ write_report → END
```

这段图体现了 Agent 工作流的核心：节点不仅顺序执行，还根据当前状态决定下一步，并能使用工具和重试。但决策范围是工程师明确设计的，不是任由模型调用任意工具。

## 12. Agent 与普通流水线的区别

普通流水线通常固定执行 A → B → C。当前工作流有状态、条件边、工具调用、失败回退和有限循环，因此具备 Agent 工作流特征。

但不要夸大：当前并不是完全自治 Agent。它更准确地说是“受控的 Agentic Workflow”。面试中这样描述会比“多个智能体自动辩论”更可信。

## 13. 两层引用审核

引用审核位于 `app/services/citation_reviewer.py`。

第一层是确定性校验：

1. `article_id` 在数据库中存在；
2. 法律名称一致；
3. 条号一致；
4. 引用正文与数据库原文完全一致；
5. 查询与条文具有最低检索关联。

任意关键字段不一致，引用标记为 `rejected`。这可以拦截模型虚构或篡改法条。

第二层是可选 LLM 语义审核：判断真实条文是否能支撑当前问题。LLM 只能审核给定 ID，不能新增法条。模型可以将引用降级为低置信度，但不能绕过第一层真实性校验。

关键设计原则：确定性规则管理“它是不是真实条文”，模型辅助判断“它是否支持当前论点”。

## 14. 报告生成为何分为 Draft 和 Render

`app/services/report_writer.py` 分两步：

1. `create_report_draft` 生成标题、分析、建议和证据缺口；
2. `render_markdown` 由服务器拼装固定章节、免责声明和数据库引用原文。

不让模型直接生成完整最终 Markdown 的原因：

- 模型可能修改法条原文；
- 模型可能漏掉免责声明；
- 输出章节和引用格式不稳定；
- 服务端渲染更容易测试。

模型失败时使用离线模板生成报告。没有通过审核的引用时，报告明确写“低置信度”，而不是隐藏事实。

## 15. 第二周新增数据库表

### `agent_runs`

保存任务问题、文件文本、模式、状态、进度、当前节点、重试次数、事实、报告、节点轨迹、错误、模型名称和时间。

### `agent_run_citations`

保存任务与法规的关系，以及综合分数、关键词分数、语义分数、审核状态、审核理由和最终是否通过。

### `article_embeddings`

保存每个 provider/model 对应的法规向量和内容哈希。

这些表让一次 Agent 运行变得可追踪：不仅知道最终报告是什么，也知道它检索了什么、为什么通过、是否回退、每个节点花了多久。

## 16. 第二周 API 调用流程

创建任务：

```text
POST /api/v1/runs
question=供应商收款后没有交货，能否解除合同并要求赔偿？
mode=offline
```

返回：

```json
{
  "run_id": 1,
  "status": "completed",
  "status_url": "/api/v1/runs/1",
  "report_url": "/api/v1/runs/1/report"
}
```

然后调用：

```text
GET /api/v1/runs/1             查看状态、事实和节点轨迹
GET /api/v1/runs/1/citations   查看引用与审核结果
GET /api/v1/runs/1/report      查看最终报告
GET /api/v1/articles/{id}      回查引用原文
```

当前 `POST /runs` 虽然返回 202，但第二周仍在请求内同步执行。第三周会改为真正后台任务，接口路径保持不变。

## 17. 节点轨迹是什么

每个节点记录：

- 节点名称；
- 完成或失败状态；
- 执行耗时；
- 可以公开的动作摘要；
- 错误码。

项目不会保存或展示模型隐藏思维链。可观测性应该记录输入输出摘要、工具动作、耗时和错误，而不是要求模型暴露完整内部推理。

## 18. 第二周故障处理

### 没有 API Key

Agent 模式会发现 LLM 不可用，使用规则和模板继续完成。

### 模型超时

客户端有限重试，仍失败则上层回退。

### 模型返回非法 JSON

请求修复一次；仍失败则抛出结构化错误并回退。

### Embedding 服务未配置

默认使用 hash provider。真实 Embedding 必须单独配置，不能默认复用 Chat 地址。

### 没有检索结果

工作流最多补充检索两次，然后生成低置信度报告并结束。

### 引用被篡改

数据库一致性校验失败，标记 `rejected`，不会进入报告的可信引用部分。

## 19. 第二周测试覆盖

当前共有 19 项自动测试，重点包括：

- 合同和劳动案件分类；
- 文档解析与非法格式；
- 哈希向量与混合检索；
- 向量索引幂等；
- 长法条切片；
- 篡改引用拦截；
- 无知识库时有限重试；
- LLM 超时回退；
- 非法 JSON 只修复一次；
- OpenAI 兼容环境变量映射；
- LangGraph 节点顺序；
- 状态、引用、报告和法条详情接口；
- 无密钥 Agent 模式回退。

执行：

```powershell
python scripts\run_self_test.py
```

预期：

```text
Ran 19 tests
OK
```

## 20. 第二周面试表达

可以这样介绍：

> 第二阶段我用 LangGraph 将案件分析、混合检索、引用审核和报告生成建模为显式状态图。系统同时支持离线和真实模型模式，通过 Adapter 隔离服务商，通过 Pydantic 校验结构化输出。所有法条引用先用数据库 ID 和原文做确定性校验，再进行可选语义审核；模型或检索失败时采用有限重试和规则回退，避免无限循环和单点故障。

---

# 求职面试复习区

## 1. 为什么这个项目需要 RAG

LLM 参数中的知识无法保证准确、最新和可追溯。RAG 先从项目知识库检索候选依据，再让模型基于依据分析，可以降低凭空生成法条的概率，并提供可回查引用。

注意：RAG 不能自动消除幻觉。检索可能返回错误内容，模型也可能错误理解，因此项目增加引用审核和评测。

## 2. 为什么需要 LangGraph

工作流包含状态共享、条件分支、工具调用、失败回退和有限循环。手写大量 if/else 也能实现，但随着节点增加会难以维护。LangGraph 将节点、边和状态显式化，便于解释、测试和未来加入持久化或人工审核。

## 3. 如何防止法条幻觉

回答顺序：

1. 法条来自数据库检索，不接受模型自由生成的法条作为事实。
2. 报告引用必须包含 `article_id`。
3. 服务端回查法律名称、条号和正文。
4. 不一致的引用直接拒绝。
5. 模型只能判断支撑关系，不能修改原文。
6. 最终报告附来源和免责声明。
7. 使用人工标注评测集计算引用正确率。

## 4. 为什么保留 Offline 模式

- 提高可运行性；
- 降低演示成本；
- 支持 CI；
- 建立效果基线；
- 外部模型故障时提供降级能力。

## 5. 为什么当前不用 MySQL

SQLite 能让项目独立运行，适合单机 MVP 和测试。进入多用户并发、后台任务和生产部署后，可以迁移 PostgreSQL/MySQL。数据库选择应由阶段和负载决定，不是越复杂越专业。

## 6. 为什么当前不用 Redis 和 RocketMQ

第二周任务同步执行，不需要消息代理。第三周做后台任务时 Redis 可用于队列、状态和限流。RocketMQ 更适合与已有 Java 微服务事件体系集成，当前引入会增加运维复杂度而没有直接收益。

## 7. 当前检索有什么不足

- 内置法规只有少量教学样例；
- 哈希向量主要依赖字符重合；
- 没有 BM25、向量数据库和 reranker；
- 没有法规时效性和版本过滤；
- 尚未通过完整标注集评测。

面试时不要回避限制。说明下一步如何验证和改进，比声称“检索很准确”更专业。

## 8. Agent 和普通 LLM 调用有什么区别

普通调用是输入 Prompt 后得到一次输出。本项目将模型放在有状态工作流中，能够调用检索和审核工具，根据结果选择重试或继续，并持久化执行轨迹。它仍然是受控工作流，不是无限自治。

## 9. 为什么不保存思维链

工程可观测性需要的是可验证的动作摘要、工具输入输出、耗时、错误和决策结果。隐藏思维链不稳定、不可作为可靠审计依据，也可能包含敏感信息。项目只记录公开节点轨迹。

## 10. 当前最大的技术债是什么

可以回答：

1. 后台任务仍然同步；
2. 数据库没有 Alembic 迁移；
3. 法规数据量和权威性不足；
4. 真实 Embedding 尚未形成固定评测结果；
5. 没有前端和 Docker；
6. 错误响应格式还未完全统一。

这些正是第三、第四周要解决的问题。

## 11. 简历描述草稿

在完成第四周评测前，不填写虚构指标。当前可以使用：

> 独立设计并实现可追溯法律分析 Agent，使用 FastAPI、SQLAlchemy 与 LangGraph 构建案件分析、混合检索、引用审核和报告生成工作流；通过 Adapter 支持离线与 OpenAI 兼容模型切换，并以 Pydantic 校验、有限重试和规则回退处理模型异常。所有法规引用均通过数据库 ID 与原文一致性审核，项目提供 OpenAPI/Apifox 文档及 19 项自动测试。

第四周获得真实评测结果后，再加入 Recall@5、引用正确率、工作流成功率和 P95 延迟。

---

# 后续追加格式

以后每次完成一组功能，在文件末尾复制以下模板并填写，不修改上面的历史章节。

```markdown
# YYYY-MM-DD：第 N 周——功能名称

## 1. 本次解决的问题

## 2. 用户可以看到的变化

## 3. 新增或修改的文件

## 4. 核心实现原理

## 5. 一次请求或数据的完整流转

## 6. 异常与安全处理

## 7. 自动测试和实际结果

## 8. 已知限制和下一步

## 9. 面试可能追问

## 10. 本次简历描述是否需要更新
```

---

# 2026-07-22：配置兼容与学习文档制度

## 1. 本次解决的问题

用户已有一套 OpenAI 兼容、MySQL、Redis、Spring Boot 和 RocketMQ 配置，需要判断哪些可以用于当前 Python Agent 项目。同时需要建立一份以求职学习为目标、以后持续追加的项目文档。

## 2. 用户可以看到的变化

- 项目支持直接读取 `OPENAI_API_KEY`、`OPENAI_BASE_URL` 和 `MODEL_NAME`；
- 原来的 `LLM_API_KEY`、`LLM_BASE_URL` 和 `LLM_MODEL` 仍然支持；
- Chat 和 Embedding 配置彻底分离；
- 新增 `docs/CONFIGURATION.md`；
- 新增本学习日志；
- 新增 `AGENTS.md`，要求以后完成功能后追加学习记录。

## 3. 新增或修改的文件

- `app/config.py`：增加兼容变量读取和优先级；
- `.env.example`：更新 DeepSeek 示例并增加安全提醒；
- `docs/CONFIGURATION.md`：解释各类旧配置是否适用；
- `tests/test_second_week.py`：验证环境变量别名；
- `docs/LEARNING_JOURNAL.md`：项目学习与面试准备主文档；
- `AGENTS.md`：追加式维护规则。

## 4. 核心实现原理

配置读取使用“新项目变量优先，兼容变量兜底”的方式：

```text
LLM_API_KEY  > OPENAI_API_KEY
LLM_BASE_URL > OPENAI_BASE_URL
LLM_MODEL    > MODEL_NAME
```

这样不会强迫已有环境立刻改名，同时避免业务代码到处判断不同变量。

Embedding 不复用 LLM Key 和地址。只有用户显式配置 `EMBEDDING_PROVIDER=openai-compatible` 以及独立 Embedding 参数时，系统才请求 `/embeddings`。

## 5. 一次配置读取的流转

```text
Python 导入 app.config
  ↓
读取项目根目录 .env
  ↓
读取系统环境变量
  ↓
按优先级选择 LLM 配置
  ↓
校验检索权重并归一化
  ↓
缓存 Settings
  ↓
LLM/Embedding Adapter 使用 Settings
```

由于 `get_settings()` 使用缓存，修改 `.env` 后必须重新启动服务。

## 6. 异常与安全处理

- 真实密钥和密码不写入仓库；
- `.env` 被 `.gitignore` 排除；
- 已公开的密钥应在服务提供方撤销并轮换；
- MySQL、Redis、RocketMQ 配置未直接搬入项目；
- 不把 Spring JDBC URL 当作 SQLAlchemy URL；
- 不把 Chat 模型地址自动当作 Embedding 地址。

## 7. 自动测试和实际结果

新增 `test_openai_compatible_environment_aliases`，在隔离的环境变量中验证兼容名称、优先级、模型名、离线模式和 Embedding 密钥隔离。

完整测试结果：

```text
Ran 19 tests
OK
```

## 8. 已知限制和下一步

当前没有迁移 MySQL，也没有接入 Redis/RocketMQ。第三周实现后台任务时再评估 Redis；只有需要对接已有 Java 事件系统时才考虑 RocketMQ。

## 9. 面试可能追问

问题：“为什么不直接兼容所有旧配置？”

回答要点：配置兼容不是越多越好。只兼容语义相同的 OpenAI Chat 参数；数据库、中间件和 Java 框架配置涉及不同运行模型，必须经过架构设计和迁移验证，不能简单改名后使用。

问题：“为什么修改 `.env` 后需要重启？”

回答要点：配置对象通过 `lru_cache` 缓存，减少重复读取和解析；重启进程会清空缓存并加载新配置。测试中通过 `cache_clear()` 隔离不同环境。

## 10. 本次简历描述是否需要更新

不需要单独增加简历条目。它属于“支持 OpenAI 兼容模型切换和安全配置管理”的实现细节，可以在面试展开说明。

---

# 2026-07-22：逐接口使用手册

## 1. 本次解决的问题

原有 `API_REFERENCE.md` 和 `openapi.json` 适合快速查阅和导入工具，但学习者仍需要理解每个接口为什么存在、参数如何填写、返回字段如何解释、出错后如何排查，以及多个接口之间怎样组成完整 Agent 调用链。

## 2. 用户可以看到的变化

- 新增 `docs/API_GUIDE_DETAILED.md`，覆盖全部 15 个接口定义；
- 9 个已实现接口包含真实调用方式、详细字段说明、成功和错误返回示例；
- 6 个规划接口包含预期契约，并明确提示当前调用会返回 404；
- 增加 Apifox 环境配置、完整自测顺序、统一错误理解和面试回答；
- README 与快速接口文档增加详细手册入口。

## 3. 新增或修改的文件

- `docs/API_GUIDE_DETAILED.md`：逐接口学习与调试主文档；
- `README.md`：增加详细接口手册链接；
- `docs/API_REFERENCE.md`：增加从快速参考到详细手册的跳转；
- `docs/LEARNING_JOURNAL.md`：追加本次学习记录。

## 4. 核心文档设计原则

接口文档不能只写 URL。一个可用于开发协作和求职学习的接口说明至少需要回答六个问题：它解决什么业务问题、怎样发请求、字段有什么约束、成功后返回什么、失败后怎样处理、下一步调用哪个接口。

文档严格区分 `implemented` 和 `planned`。规划接口的示例是契约设计，不是伪装成已经完成的运行结果，这能避免调试时把正常的 404 误判为环境故障。

## 5. 一次 Agent 请求的完整流转

```text
POST /api/v1/runs
  → 返回并保存 run_id
GET /api/v1/runs/{run_id}
  → 查看状态、进度和节点轨迹
GET /api/v1/runs/{run_id}/citations
  → 审核法规来源和分数
GET /api/v1/runs/{run_id}/report
  → 获取 Markdown 与结构化报告
```

`run_id` 把一次创建请求与后续状态、引用、报告资源关联起来。重试失败任务会产生新的 `run_id`，不会覆盖原失败记录。

## 6. 异常与安全处理

- 明确解释 404、409、415、422 等状态码和排查动作；
- 指出 FastAPI 当前默认错误格式与规划统一错误格式的差异；
- 规划接口当前返回 404 属于预期行为；
- 示例只使用假数据，不包含真实密钥、数据库密码或案件材料；
- 法规引用的相关度分数不能解释为结论正确率或胜诉率。

## 7. 验证结果

本次只新增和更新 Markdown 文档，没有修改运行代码或 OpenAPI 契约。接口数量已与 `docs/openapi.json` 对照：共 15 个，其中 9 个 `implemented`、6 个 `planned`。

## 8. 已知限制和下一步

规划接口需要在后续周次实现后，把文档里的“计划返回”替换为自动测试验证过的真实结果。第三周异步化后，还需要补充轮询间隔、任务超时和幂等性说明。

## 9. 面试可能追问

问题：“为什么创建任务、查询状态、查询引用和获取报告要拆成多个接口？”

回答要点：Agent 任务可能耗时且失败，拆分资源后可以支持进度轮询、失败重试、引用审计、报告权限与独立导出，也为同步实现迁移到后台任务保留稳定契约。

问题：“为什么要把规划接口也写进 OpenAPI？”

回答要点：先设计契约可以让前后端并行和提前 Mock，但必须通过扩展字段清楚标记实现状态，避免把设计稿误认为生产能力。

## 10. 本次简历描述是否需要更新

不需要新增独立简历条目。接口契约设计、错误处理、可观测任务资源和 Apifox/OpenAPI 协作方式可以作为现有 Agent 项目的面试展开内容。

---

# 2026-07-22：本地运行环境文件

## 1. 本次解决的问题

为项目创建实际使用的 `.env`，让 PyCharm 启动时能够从项目根目录读取一套明确、安全且可以直接运行的配置。

## 2. 用户可以看到的变化

- 默认 `OFFLINE_MODE=true`，没有模型密钥也能完成 Agent 工作流；
- 默认使用项目自己的 SQLite，不依赖 MySQL；
- 默认使用本地哈希 Embedding，不调用外部向量接口；
- 预填 DeepSeek 兼容地址和模型名，但密钥保持为空；
- 保留混合检索权重、超时和工作流重试次数。

## 3. 新增或修改的文件

- `.env`：本机运行配置，被 `.gitignore` 排除；
- `docs/LEARNING_JOURNAL.md`：追加本次配置学习记录。

## 4. 核心实现原理

`app/config.py` 在导入时读取项目根目录的 `.env`，再构造并缓存 `Settings`。`DATABASE_URL` 留空时自动使用 `data/legal_copilot.db`；`EMBEDDING_PROVIDER=hash` 时使用本地哈希向量；`OFFLINE_MODE=true` 时不调用外部 LLM。

## 5. 配置读取流转

```text
启动 app.main
  → app.config 加载项目根目录 .env
  → get_settings() 校验和归一化配置
  → 数据库选择 SQLite
  → Embedding 选择 hash
  → Agent 选择 offline
  → 服务无需外部中间件即可启动
```

## 6. 异常与安全处理

- `.env` 已由 `.gitignore` 排除，不应提交到 Git；
- 公开粘贴过的 API Key 不再写入文件，应先撤销并轮换；
- MySQL、Redis、RocketMQ 当前未接入，不保存相关密码；
- 切换真实模型时只填写轮换后的 `LLM_API_KEY`，并把 `OFFLINE_MODE` 改为 `false`；
- 修改 `.env` 后需要重启 PyCharm 中的服务，因为 Settings 有进程内缓存。

## 7. 验证结果

配置项与 `app/config.py` 当前读取字段逐项核对。离线组合不要求网络、API Key、MySQL、Redis 或 RocketMQ。

## 8. 已知限制和下一步

当前 DeepSeek 模型配置只用于 OpenAI 兼容 Chat。Embedding 继续使用本地 hash；如果以后切换真实 Embedding，需要单独确认服务是否提供 Embedding 模型，并填写独立的 Key、Base URL 和模型名。

## 9. 面试可能追问

问题：“为什么 Chat 模型和 Embedding 不共用一套配置？”

回答要点：二者可能来自不同供应商、使用不同模型和鉴权策略。拆分配置可以避免把只支持 Chat 的地址错误用于 Embedding，也方便独立降级和成本控制。

## 10. 本次简历描述是否需要更新

不需要。环境分层、安全密钥管理和离线降级属于项目工程化设计，可在面试中结合整体架构说明。

---

# 2026-07-22：第三周——可交互产品、后台任务与报告导出

## 1. 本次解决的问题

第二周已经具备完整 Agent 工作流，但用户只能通过 Swagger 或 Apifox 操作，而且创建任务会在一个请求内等待工作流完成。第三周把技术能力包装为可演示的浏览器产品，并补齐长任务进度、文件安全、报告下载、请求日志和容器化配置。

第三周的核心目标不是简单“增加一个页面”，而是建立以下完整闭环：

```text
浏览器输入问题/上传文件
  → 后端校验文件并创建 queued 任务
  → HTTP 202 立即返回 run_id
  → FastAPI 后台任务执行 LangGraph
  → 每个节点把状态和进度写入 SQLite
  → React 每 1.5 秒轮询状态
  → completed 后并行读取报告和引用
  → 用户查看引用详情并下载 Markdown/PDF
```

## 2. 用户可以看到的变化

- 新增完整 React + TypeScript 页面，不再依赖 Swagger 完成演示；
- 支持拖拽或点击上传 TXT、DOCX、PDF，并显示名称、类型和大小；
- 支持示例问题、5000 字限制、离线/Agent 模式切换；
- 创建任务立即返回 `queued`，页面持续显示节点与进度；
- 展示案件类型、置信度、四个节点的动作摘要和耗时；
- 报告使用安全 Markdown 组件渲染，不执行用户 HTML；
- 点击引用可查看数据库原文、来源、各检索分数和审核理由；
- 支持下载 `.md` 和带中文字体的 `.pdf` 报告；
- 后端离线时页面会明确提示，提交按钮不会继续发送无效请求；
- 提供 Docker Compose 配置，可在安装 Docker 后启动前后端。

## 3. 新增或修改的关键文件

### 后端

- `app/main.py`：后台任务、CORS、请求日志、安全上传和报告导出路由；
- `app/tasks.py`：使用独立数据库 Session 执行后台 Agent 任务；
- `app/workflows/legal_report_graph.py`：逐节点持久化状态、进度和轨迹；
- `app/services/upload_security.py`：文件大小、扩展名、MIME、文件名和解析超时校验；
- `app/services/report_export.py`：把 Markdown 转换为中文 PDF；
- `app/migrations.py`：为已有 SQLite 数据库补充 `started_at` 字段；
- `app/models.py`、`app/schemas.py`：增加任务时间信息；
- `tests/test_third_week.py`：第三周接口、安全和导出测试。

### 前端

- `frontend/src/App.tsx`：输入、上传、轮询、轨迹、报告和引用交互；
- `frontend/src/api.ts`：统一 API 调用和错误转换；
- `frontend/src/types.ts`：与后端响应对应的 TypeScript 类型；
- `frontend/src/styles.css`：响应式产品视觉与可访问性样式；
- `frontend/vite.config.ts`：本地开发代理；
- `frontend/package.json`、`pnpm-lock.yaml`：可复现依赖与构建命令。

### 部署与文档

- `Dockerfile`：后端生产镜像；
- `frontend/Dockerfile`、`frontend/nginx.conf`：前端构建和反向代理；
- `docker-compose.yml`：前后端、健康检查和 SQLite volume；
- `README.md`、`PRODUCT_SPEC.md`、`PROJECT_GOALS.md`、`SELF_TEST.md`：同步第三周状态与操作；
- `docs/openapi.json`、`docs/API_REFERENCE.md`、`docs/API_GUIDE_DETAILED.md`：导出接口改为已实现，更新异步语义。

## 4. 核心实现原理

### 4.1 为什么创建接口只返回 queued

`POST /api/v1/runs` 的职责变成“创建任务资源”，而不是“等待所有分析完成”。路由先把问题、文件文本和模式写入 `agent_runs`，提交事务取得 `run_id`，再把 `execute_agent_run_by_id` 注册为 FastAPI BackgroundTask。

响应使用 HTTP 202：

```json
{
  "run_id": 42,
  "status": "queued",
  "status_url": "/api/v1/runs/42",
  "report_url": "/api/v1/runs/42/report"
}
```

后台函数不能复用请求中的 SQLAlchemy Session，因为请求结束后该 Session 会关闭。因此 `app/tasks.py` 根据 `run_id` 创建独立 Session，再读取任务并执行工作流。

### 4.2 节点进度如何保存

LangGraph 每个节点开始和结束时更新 `AgentRun`：

| 状态 | 典型进度 | 节点 |
|---|---:|---|
| `queued` | 0 | 等待后台执行 |
| `analyzing` | 15–30 | `analyze_case` |
| `retrieving` | 40–55 | `retrieve_laws` |
| `reviewing` | 65–75 | `review_citations` |
| `writing` | 85–95 | `write_report` |
| `completed` | 100 | 工作流结束 |

每个节点把公开动作摘要和耗时写入 `node_traces`。这里只展示“做了什么”和“花了多久”，不展示模型隐藏思维链。

### 4.3 前端为什么轮询而不是 WebSocket

当前任务量小、状态更新频率低，1.5 秒 HTTP 轮询更容易实现、测试和部署。组件在任务完成、失败或卸载时清理 `setInterval`，避免内存泄漏和无效请求。

WebSocket 或 SSE 更适合高频实时事件，但会增加连接管理、断线恢复和代理配置。当前阶段轮询的复杂度与收益更合理。

### 4.4 Markdown 为什么使用 ReactMarkdown

报告内容来自模型或模板，必须按不可信输入处理。`react-markdown` 默认不会直接执行原始 HTML，比把字符串交给 `dangerouslySetInnerHTML` 更安全。正式产品仍应增加内容安全策略和链接协议白名单。

### 4.5 PDF 如何支持中文

后端使用 ReportLab 的 `STSong-Light` CID 字体构建 PDF。它避免依赖开发机的 Windows 字体路径，使 Linux 容器也能生成中文。转换器识别 Markdown 标题、引用和列表，其他文本按段落写入。

## 5. 一次请求和数据的完整流转

```text
用户拖入 case.pdf
  → 前端检查扩展名、大小和空文件
  → FormData 提交 question/mode/file
  → 后端最多读取 MAX_UPLOAD_BYTES + 1
  → 校验扩展名与 MIME 对应关系
  → 在线程中解析文档，并设置超时
  → 保存 AgentRun(status=queued)
  → 响应 202 + run_id
  → 后台线程使用新 Session 执行 LangGraph
  → 状态接口读取 SQLite 中的实时状态
  → 前端轮询到 completed
  → 并行读取 report 与 citations
  → ReactMarkdown 渲染正文
  → 用户点击 citation 查看可追溯原文
```

导出请求不会重新运行模型，而是读取数据库中已经保存的 `report_markdown`。这样能保证页面展示和下载文件使用同一份结果，也避免重复费用。

## 6. 异常与安全处理

### 上传安全

- 前后端都限制最大 10 MB，前端校验只改善体验，后端校验才是安全边界；
- 允许 `.txt`、`.docx`、`.pdf`，同时检查浏览器上报的 MIME；
- 只读取 `MAX_UPLOAD_BYTES + 1`，不会先把任意大文件完整放进内存；
- 使用安全展示文件名，去除目录和特殊字符；
- 当前不把上传文件保存到服务器，降低路径穿越和残留风险；
- 空文件、损坏文件和解析超时分别返回可理解错误。

### 日志安全

每次 HTTP 请求获得或复用 `X-Request-ID`，日志记录 method、path、status code 和 duration。日志不记录 Authorization、API Key、文件全文或问题全文。

### 后台任务限制

FastAPI BackgroundTasks 是进程内方案。它解决 HTTP 长时间阻塞，但不能保证服务崩溃后的任务恢复，也不能跨多个实例统一调度。生产环境应迁移到 Celery/RQ + Redis 等持久队列，并增加幂等键和任务租约。

## 7. 自动测试和实际结果

后端执行：

```powershell
python scripts\run_self_test.py
```

实际结果：

```text
Ran 26 tests
OK
```

第三周新增测试覆盖：

- 创建响应为 `queued`，后台完成后状态为 `completed`；
- 开始和完成时间写入；
- Markdown 导出文件名、Content-Type 和正文；
- PDF 以 `%PDF` 文件头返回且包含有效内容；
- 非法导出格式返回 422；
- 扩展名/MIME 伪装返回 415；
- 文件名目录部分与危险字符被清理；
- `X-Request-ID` 在响应中返回。

前端执行 TypeScript 检查和 Vite 生产构建，实际结果为 188 个模块转换成功，生成 HTML、CSS 和 JavaScript 生产文件。

OpenAPI JSON 解析通过：版本 `0.3.0`，15 个契约中 10 个 implemented、5 个 planned。Docker Compose YAML 结构解析通过，包含 backend、frontend 和 legal-data volume。

## 8. 已知限制和下一步

- 当前电脑没有安装 Docker，所以 Dockerfile/Compose 尚未执行真实镜像构建；
- BackgroundTasks 不持久，第四周或生产化时可迁移任务队列；
- 前端没有用户账号，任何能访问服务的人都能通过 ID 查询任务；
- PDF 转换器只处理当前报告使用的基础 Markdown，不支持复杂表格和图片；
- 扫描版 PDF 仍然需要 OCR；
- 法规库仍为 10 条教学样例，不是权威全量数据库。

## 9. 面试可能追问

问题：“FastAPI BackgroundTasks 算真正的异步任务队列吗？”

回答要点：它能让响应先返回，再在线程池中执行同步函数，适合单机 MVP；但任务与 Web 进程同生命周期，没有持久化队列、确认机制和跨实例调度。生产环境应使用 Celery/RQ 等，并把任务状态保留在数据库。

问题：“为什么前端和后端都校验文件？”

回答要点：前端校验提供及时反馈，不能作为安全边界，因为调用者可以绕过浏览器直接请求 API。后端必须独立校验大小、扩展名、MIME、内容可解析性和超时。

问题：“为什么不直接把 PDF 存服务器？”

回答要点：当前报告可由已持久化 Markdown 确定性生成，按需生成减少重复文件、清理任务和磁盘占用。大规模场景可生成后存对象存储，并用内容哈希避免重复。

问题：“轮询、SSE 和 WebSocket 怎么选？”

回答要点：低频单向状态更新使用轮询最简单可靠；SSE 适合服务器单向事件流；WebSocket 适合高频双向交互。当前 1.5 秒轮询满足演示体验且部署成本最低。

## 10. 本次简历描述是否需要更新

需要。可以在已有项目条目中补充：

> 使用 React、TypeScript 与 Vite 构建法律 Agent 交互界面，将同步 LangGraph 请求改造成基于 FastAPI BackgroundTasks 的任务资源，支持节点进度轮询、可追溯引用、Markdown/PDF 导出、10 MB 文件安全校验和结构化请求日志；编写前后端 Dockerfile 与 Compose 配置，后端 26 项自动测试和前端生产构建通过。

注意：在 Docker 实际构建验收完成前，不要在简历中声称“Docker 部署已验证”。

---

# 2026-07-22：pnpm 11 构建脚本白名单兼容

## 1. 本次解决的问题

用户安装 pnpm 11 后，运行前端时出现 `ERR_PNPM_IGNORED_BUILDS`。原因不是 React 代码失败，而是 pnpm 11 默认严格拒绝未经审核的依赖安装脚本，并且已经移除 pnpm 10 使用的 `onlyBuiltDependencies` 配置。

## 2. 用户可以看到的变化

项目的 `pnpm-workspace.yaml` 改用 pnpm 11 的 `allowBuilds`，明确只允许 `esbuild` 执行安装脚本。重新运行 `pnpm install` 后即可启动 Vite。

## 3. 新增或修改的文件

- `frontend/pnpm-workspace.yaml`：将旧白名单迁移为 `allowBuilds`；
- `README.md`：补充 pnpm 11 安装说明；
- `docs/LEARNING_JOURNAL.md`：追加本次兼容记录。

## 4. 核心实现原理

Vite 使用 esbuild 做开发期转换和依赖预构建。esbuild 的 npm 包需要在安装阶段选择当前操作系统对应的可执行文件，因此存在 install script。pnpm 11 的 `strictDepBuilds` 默认为 true，未在 `allowBuilds` 中明确审核的脚本会导致安装返回非零退出码。

项目没有开启 `dangerouslyAllowAllBuilds`，因为这会让现在和未来所有依赖都能执行脚本。当前采用最小权限白名单：

```yaml
allowBuilds:
  esbuild: true
```

## 5. 数据流转

```text
pnpm install
  → 读取 pnpm-workspace.yaml
  → 检查 esbuild 是否允许执行脚本
  → 执行 esbuild install.js
  → 安装 Windows x64 二进制
  → pnpm run dev 启动 Vite
```

## 6. 异常与安全处理

- 只允许项目实际需要的 esbuild；
- 不关闭所有依赖脚本检查；
- 不使用 `dangerouslyAllowAllBuilds=true`；
- 新依赖如果出现安装脚本，必须单独审核后才能加入白名单。

## 7. 验证方式

在 `frontend` 目录执行：

```powershell
pnpm install --registry=https://registry.npmmirror.com
pnpm run build
pnpm run dev
```

安装不应再出现 `ERR_PNPM_IGNORED_BUILDS`。

## 8. 已知限制和下一步

该配置针对 pnpm 11。锁文件继续保证依赖版本可复现；升级 pnpm 大版本时仍需检查官方迁移说明。

## 9. 面试可能追问

问题：“为什么不直接允许所有依赖执行安装脚本？”

回答要点：install/postinstall 在安装依赖时直接执行本机代码，是供应链攻击面。最小白名单能保留 esbuild 的必要功能，同时避免未来新增依赖自动获得脚本执行权限。

## 10. 本次简历描述是否需要更新

不需要。这属于前端依赖供应链安全和工具版本兼容细节，可在工程化问题中展开说明。

---

# 2026-07-22：棕金色文字对比度优化

## 1. 本次解决的问题

原页面把同一种浅金色同时用于深绿色背景和白色卡片背景。浅金色在深色背景上清晰，但放在白色或米白背景上对比度不足，栏目标题和部分提示文字不易阅读。

## 2. 用户可以看到的变化

- 深绿色首屏继续使用亮金色，保持品牌视觉；
- 白色和米白卡片上的栏目标题改成深棕色；
- 未核验引用标签使用更深的棕色；
- 免责声明文字加深并略微增大；
- 棕金色装饰线和圆点同步加深。

## 3. 新增或修改的文件

- `frontend/src/styles.css`：拆分深色背景与浅色背景的金色变量；
- `docs/LEARNING_JOURNAL.md`：追加本次可访问性记录。

## 4. 核心实现原理

颜色不能只按“品牌统一”复用，还必须根据背景分别设计。深色背景使用 `--gold-light`，浅色背景使用深棕色 `#704b10`，避免浅金色文字与白色背景亮度过于接近。

## 5. 页面样式流转

```text
深绿色首屏 → .eyebrow → --gold-light
白色功能卡片 → .kicker → #704b10
未核验标签 → 深棕文字 + 浅棕背景
免责声明 → 深棕灰文字 + 米白背景
```

## 6. 异常与安全处理

本次只调整 CSS 颜色，没有修改页面数据、接口、权限或用户输入处理。保留键盘焦点样式和 `prefers-reduced-motion` 设置。

## 7. 验证方式

执行 `pnpm run build`，确认 TypeScript 与 Vite 生产构建通过。刷新开发页面后重点检查白色卡片上的“案件输入”“执行过程”“分析完成”和免责声明。

## 8. 已知限制和下一步

当前没有引入自动化无障碍扫描；第四周可增加 axe 或 Lighthouse 检查，并把文字对比度纳入前端验收。

## 9. 面试可能追问

问题：“为什么同一个品牌金色要定义亮色和深色两种？”

回答要点：品牌色的视觉语义可以一致，但可读性取决于前景与背景的相对亮度。深浅背景应使用不同色阶，避免为了形式统一牺牲可访问性。

## 10. 本次简历描述是否需要更新

不需要。它属于前端可访问性和视觉质量优化，可在页面设计取舍中说明。

# 2026-07-22：首屏背景层级修复

## 1. 现象

首页标题“让每一条法律分析”、说明文字、顶部品牌名和知识库状态原本使用白色字体，但页面实际显示成了米白色背景，导致白字与背景几乎没有对比度。

## 2. 根因

首屏深绿色渐变原来绘制在 `.app-shell::before` 伪元素上，同时给伪元素设置了负数 `z-index`。在浏览器的层叠上下文中，这个伪元素可能被放到页面根背景之后，因此深绿色背景没有显示；白色字体本身并不是问题。

## 3. 修复内容

1. 把深绿色渐变和金色光晕直接设置为 `.app-shell` 的多层背景，不再依赖负层级伪元素。
2. 使用 `isolation: isolate` 创建独立层叠上下文，避免装饰层逃到页面背景之后。
3. 将背景区域高度调整为 760px，使首屏说明文字和功能特点都位于深色背景上。
4. 明确让顶部栏、主体和页脚位于装饰字之上，保证文字与按钮可交互、可阅读。

## 4. 求职面试知识点

当元素“存在但看不见”时，不应只检查颜色，还要检查 CSS 层叠上下文。`position`、`z-index`、`transform`、`opacity` 和 `isolation` 都可能创建或改变层叠上下文。负数 `z-index` 尤其容易让伪元素落到父元素背景或页面根背景后面。对于页面主背景，直接使用容器的 `background` 通常比负层级伪元素更稳定；伪元素更适合承载水印等非核心装饰。

## 5. 自测步骤

1. 启动前端：`pnpm run dev`。
2. 打开首页并执行一次强制刷新（Windows：`Ctrl + F5`）。
3. 确认页面顶部到首屏功能特点区域显示深绿色渐变背景。
4. 确认品牌名、主标题第一行、说明文字、知识库状态和三个功能特点均能清晰阅读。
5. 确认工作台区域仍为浅色背景，上传、示例案件和分析按钮的布局没有变化。

---

# 2026-07-23：第四周——评测、工程质量与求职发布

## 1. 本次解决的问题

前三周已经形成可运行产品，但“效果好不好”主要依赖主观体验；测试还会读取本机 `.env`，在 Agent 用例中意外调用真实 DeepSeek；仓库也缺少 CI、技术决策和可直接使用的求职材料。第四周把项目从功能演示推进为有数据、有质量门禁、有公开说明的求职作品。

## 2. 修改或新增的关键文件

- `eval/dataset.jsonl`：24 条合同/劳动争议均衡脱敏样例；
- `eval/metrics.py`、`eval/run_eval.py`：抽取、检索和系统评测；
- `eval/results/latest.json`、`latest.md`：机器与人工可读结果；
- `tests/test_fourth_week.py`：评测数据、安全输入和数据库锁测试；
- `scripts/run_self_test.py`：测试前强制离线并清除模型 Key；
- `app/tasks.py`：SQLite 锁有限退避重试和失败落库；
- `app/schemas.py`、`app/main.py`：返回实际执行引擎与模型；
- `frontend/src/App.tsx`、`types.ts`、`styles.css`：显示 LLM、规则或降级标签；
- `pyproject.toml`、`requirements-dev.txt`：Ruff 与 mypy；
- `.github/workflows/ci.yml`：后端与前端 CI；
- `docs/decisions/`：6 份 ADR；
- `docs/DEMO_SCRIPT.md`、`docs/JOB_MATERIALS.md`：录制、简历和面试材料；
- `README.md`、`PRODUCT_SPEC.md`、`PROJECT_GOALS.md`、`SELF_TEST.md`：第四周发布说明。

## 3. 核心实现原理

评测数据为 JSONL，每条记录固定 case ID、脱敏案情、问题、期望案件类型、事实/焦点关键词和相关 article ID。检索指标只依赖排名与标注：Recall@5 衡量相关条文找回比例；MRR 关注首条相关结果的位置；Hit@K 判断前 K 条是否至少命中一次；Precision@5 衡量返回结果中相关条文比例。

评测器在内存 SQLite 中建表、导入同一份法规数据并固定 Top-K=5，避免污染业务数据库。默认运行关键词、哈希语义和哈希混合三组；在线 Embedding 必须显式传入 `--include-online`，否则标记 `skipped`，避免意外费用。

Ruff 负责格式和静态问题，mypy 检查核心 Python 类型，GitHub Actions 在无密钥 Ubuntu 环境重复执行质量门禁、测试、评测和前端构建。

## 4. 请求与数据如何流转

```text
dataset.jsonl
  → 校验 case_id 与相关 article_id
  → 规则抽取 → 类型准确率/关键词覆盖率
  → 三种检索排名 → Recall@5/MRR/Hit@K/延迟
  → 离线 LangGraph → 成功率/平均与 P95 耗时
  → latest.json + latest.md
```

页面提交任务后，状态接口新增 `execution_engine` 和 `model`。后端根据最终持久化结果返回 `rules`、`llm` 或 `fallback`，前端直接展示标签。检索相似度不再被当作是否使用 Agent 的证据。

## 5. 评测发现与改进

首次运行时，案件类型规则准确率为 75%。错误主要来自“供应商、交付、承运、入职、经济补偿”等表达没有出现原始词表。扩充合同和劳动领域词后，同一数据集达到 100%；关键事实关键词覆盖率为 93.75%，争议焦点覆盖率仍有限，说明规则抽取无法替代更大规模人工评测和模型方案。

检索结果：关键词 Recall@5/MRR 为 1.0000/0.8000，哈希语义为 0.8403/0.7118，哈希混合为 0.8264/0.7361。当前只有 10 条教学法规，词面高度匹配，关键词优于弱哈希向量是合理结果。项目保留全部对照，不只展示最好的一组，也不把在线组写成已经完成。

## 6. 安全与异常处理

- 自测脚本在应用导入前强制离线、使用测试数据库并删除进程中的模型 Key；
- 损坏 PDF 返回 422，超大文件、MIME 伪装和恶意文件名继续受控；
- SQL/提示注入文本仅作为普通案件字符串处理，不进入命令或 SQL 拼接，也不会读取环境变量；
- 重复提交生成不同任务 ID，保留各自审计记录；
- SQLite 短暂锁使用 0.1/0.2 秒有限重试，超过上限后任务标记失败，不无限等待。

## 7. 测试与实际结果

本地实际结果：

- Ruff lint：通过；
- Ruff format check：通过；
- mypy：20 个核心源文件无问题；
- 后端：32 项测试通过，且没有真实模型 HTTP 请求；
- 离线工作流成功率：100%；
- 前端生产构建：188 个模块转换成功；
- GitHub Actions：工作流已创建，推送后以线上结果为准。

## 8. 已知限制

- 24 条数据规模小，且由单一项目作者构造；第二位标注者复核仍需人工完成；
- 关键词覆盖率不是严格语义评分；
- 当前没有独立 Embedding API，在线混合检索组未运行；
- 开发机没有 Docker，容器仍未实际构建；
- 演示脚本已经完成，但视频必须由项目作者录制并检查隐私。

## 9. 面试可能追问

问题：“为什么混合检索反而不如关键词？”

回答要点：数据只有 10 条且问题与法条词面高度匹配，哈希二元词向量不是强语义模型；混合权重会稀释关键词信号。对照实验的目的不是证明向量必胜，而是识别数据规模、模型和权重的适用条件。扩大法规库、接入真实 Embedding 后需要在同一评测集重新调权。

问题：“100% 案件类型准确率是否可信？”

回答要点：它只适用于 24 条作者构造的合同/劳动二分类数据，不能外推生产。文档同时保留首次 75% 基线、改进过程和单标注者偏差，后续需要盲测集与双人标注。

问题：“如何保证 CI 不产生模型费用？”

回答要点：测试入口在导入应用前覆盖 `OFFLINE_MODE=true`、使用 hash provider 并删除 Key；CI 不保存模型 Secret；网络相关逻辑使用 Fake/Mock 验证输出修复与超时降级。

## 10. 简历描述

可以使用 `docs/JOB_MATERIALS.md` 中的量化描述，但必须保留“24 条脱敏教学样例”范围。在线 Embedding、Docker 和演示视频在实际验收前不能写成已完成。

---

# 2026-07-23：GitHub Actions 首次云端验收

第四周提交 `d8d6ab8` 推送到 GitHub 后触发 `CI` 工作流，运行 ID 为 `29946002021`。`backend` Job 完成依赖安装、Ruff 格式检查、Ruff 静态检查、mypy、32 项后端测试和离线评测；`frontend` Job完成 pnpm 锁文件安装、TypeScript 检查和 Vite 构建。两个 Job 均返回 `success`。

这次验收证明项目不依赖开发机的 `.venv`、SQLite 运行库、Node modules 或真实模型 Key。CI 环境显式使用离线模式，因此不会产生 DeepSeek 或 Embedding 费用。后续每次推送 `main` 或创建 Pull Request 都会重新执行相同门禁。

面试追问：“本地测试通过为什么还需要 CI？”回答要点：本地可能隐式依赖缓存、环境变量或已安装软件；CI 在全新环境按仓库声明重建依赖，能够发现缺失文件、锁文件不一致、平台差异和测试偷偷读取本机密钥等问题。

---

# 2026-07-23：法规知识库新增接口与增量数据扩充

## 1. 本次解决的问题

项目文档原来规划了 `POST /api/v1/knowledge/articles`，但 FastAPI 中没有真实路由，调用只会返回 404。法规初始化还有一个隐藏问题：只要 `legal_articles` 中存在任意记录，程序就完全跳过 `sample_laws.jsonl`，因此向 JSONL 追加内容并重启不会更新已有数据库。用户若删除数据库重建，又会丢失案件、Agent 任务和报告。

本次把单条法规新增接口真正实现，并将种子导入改成幂等增量同步。样例法规由 10 条扩充到 36 条，同时保留原有前 10 条的顺序，避免评测数据中已有的 article ID 被重新编号。

## 2. 修改或新增的关键文件

- `app/schemas.py`：新增 `LegalArticleCreate` 请求模型和空白字段校验；
- `app/main.py`：新增知识库写接口、重复检测和即时向量建立；
- `app/services/seed.py`：从“非空即跳过”改为按法律名称与条号增量补充；
- `data/sample_laws.jsonl`：新增 26 条教学参考，共 36 条；
- `tests/test_api.py`：覆盖创建、重复冲突、空白校验、搜索和详情回查；
- `tests/test_second_week.py`：验证只恢复缺失种子且重复运行不新增；
- `docs/openapi.json`、`API_REFERENCE.md`、`API_GUIDE_DETAILED.md`：将接口由 planned 改为 implemented；
- `README.md`、`PRODUCT_SPEC.md`、`PROJECT_GOALS.md`、`SELF_TEST.md`：同步产品能力、目标、调用方式和验收方法；
- `eval/results/latest.json`、`latest.md`：扩大法规库后的重新评测结果。

## 3. 核心实现原理

请求模型对 `law_name`、`article_number`、`content` 和 `source` 设置长度限制，并使用 Pydantic `field_validator` 去除首尾空白、拒绝纯空格。接口在同一数据库会话中按“法律名称 + 条号”查询；找到已有记录时返回 409，避免普通重复提交。

创建新记录时先计算旧版兼容字段 `embedding`，再调用 `ensure_article_embeddings` 为 `hash/chinese-bigram-sha256-v1` 建立独立索引记录。该索引带内容哈希，正文不变时不会重复计算，所以新法条创建后可以立即参与混合检索。

种子导入先读取数据库现有的 `(law_name, article_number)` 集合，再逐行读取 JSONL，只插入不存在的组合。每插入一条就把键加入内存集合，因而 JSONL 自身即使意外重复也不会在同一次导入中写入两次。没有新增记录时不提交事务，重复启动结果为 0。

## 4. 请求和数据如何流转

```text
POST /api/v1/knowledge/articles
  → Pydantic 字段清洗和长度校验
  → 查询 law_name + article_number
  → 已存在：409
  → 不存在：写入 legal_articles
  → 生成 article_embeddings
  → 201 返回 article_id
  → 可立即通过 /api/v1/articles/search 检索
```

```text
应用启动
  → 读取 sample_laws.jsonl（36 条）
  → 与数据库现有法律名称 + 条号比较
  → 只插入缺少的条文
  → 为缺少或正文已变化的条文补索引
  → 原有 case_runs / agent_runs / 报告保持不变
```

## 5. 参考数据范围和质量边界

新增数据覆盖民法典合同责任、劳动合同订立与解除、劳动争议举证及时效、消费者知情权和退货赔偿。法律有效性和来源页面使用国家法律法规数据库及中国人大网核验。为避免把教学数据冒充生产级全文，多数新增内容明确标记为“条文要旨”，`source` 同时保存权威页面和“使用前核验原文”提示。

正式法律知识库还需要独立保存版本、生效日期、失效日期、来源 URL、抓取时间和原文哈希；当前把这些说明合并在 `source` 字符串中，只适合求职演示。

## 6. 测试与实际结果

- 正式本地库增量写入 26 条，`legal_articles=36`；
- 离线索引补建 26 条，`article_embeddings=36`；
- 分类数量：民法典 9、劳动合同法 14、劳动争议调解仲裁法 7、消费者权益保护法 6；
- Ruff format：38 个文件格式正确；
- Ruff lint：通过；
- mypy：20 个核心源文件无问题；
- OpenAPI JSON：语法校验通过；
- 自动测试：35 项全部通过；
- 测试环境继续强制离线，没有调用真实 LLM 或 Embedding API。

## 7. 扩大数据后的评测变化

同一套 24 条评测数据重新运行后：关键词 Recall@5/MRR 为 0.7639/0.6736，哈希语义为 0.6458/0.4875，哈希混合为 0.6806/0.5708。相比只有 10 条法规时，三个方案的指标都下降。

下降不是功能回归的直接证明，而是候选文档从 10 条增至 36 条后排序难度上升，也暴露出原评测相关条文标注只围绕旧的 10 条数据构建。后续应由第二位标注者复核每个案例可能相关的新条文，再讨论分词、领域过滤、Embedding 和混合权重，不应为了保留高分删除合理候选法规。

## 8. 已知限制

- 写接口当前没有账号、管理员鉴权和操作审计，只能在本地或受信任网络使用；
- 应用层判重无法完全解决多个并发请求同时创建相同条文的竞态，生产库应增加数据库唯一约束；
- 尚未实现 JSONL/CSV 批量上传、逐行错误报告和导入任务状态接口；
- 新增教学内容以条文要旨为主，不等同于完整权威法规库；
- 哈希二元词向量只用于离线演示，扩充数据后语义能力不足更加明显。

## 9. 面试可能追问

问题：“为什么不让用户直接改 JSONL？”

回答要点：JSONL 适合版本化的初始化数据，但运行期修改需要校验、判重、事务、即时索引和明确错误码。API 能提供这些业务边界，种子增量同步则负责让仓库内置数据安全进入已有环境，两者职责不同。

问题：“为什么新增法规后不用重启？”

回答要点：接口在写入 `legal_articles` 的同一流程中调用索引维护函数，按 provider/model 和内容哈希补建向量。检索下一次查询数据库时就能读取新记录。

问题：“数据更多以后评测分数下降，怎么解释？”

回答要点：候选集合增大后排序本来就更难，旧标注也可能漏掉新加入的合理相关条文。应先复核标注，再分析各检索分量和错误案例；诚实保留下降结果比在小数据上追求虚高指标更能体现工程判断。

---

# 2026-07-23：真实 Embedding Provider 选择、分批索引与可观测降级

## 1. 本次解决的问题

项目虽然已经实现 `OpenAICompatibleEmbeddingProvider`，但法规搜索、同步案件分析和启动索引都传入 `force_offline=True`，所以无论 `.env` 如何配置，主要 API 都只会使用哈希向量。Agent 工作流只在 `mode=agent` 时可能选择在线 provider，导致同一项目不同入口行为不一致。

另一个隐藏问题是原索引函数会把全部待处理法规一次发送给供应商。当前知识库有 36 条，而部分真实 Embedding 服务限制单次最多 10 条，首次建索引会直接失败。原 `cosine_similarity` 也只计算点积，依赖哈希向量预先归一化；第三方向量如果不是单位向量，所谓“余弦分数”会失真。

## 2. 修改或新增的关键文件

- `app/services/retrieval_service.py`：统一按配置检索并处理哈希降级；
- `app/services/embedding_provider.py`：限制 provider 枚举、补齐配置和异常校验；
- `app/services/embedding_index.py`：按照批量大小分批建立索引并校验跨批维度；
- `app/services/embeddings.py`：把点积修正为真正的余弦相似度；
- `app/main.py`：法规搜索和同步案件分析改用统一选择逻辑，搜索返回实际 provider/model 响应头；
- `app/workflows/legal_report_graph.py`：离线任务固定哈希，Agent 任务读取在线配置并在轨迹中记录实际 provider；
- `scripts/check_embedding.py`：用一条短文本验证真实服务，不打印密钥；
- `.env.example`、`docs/CONFIGURATION.md`：增加 `EMBEDDING_BATCH_SIZE` 和真实服务接入步骤；
- `tests/test_api.py`、`test_second_week.py`、`test_services.py`：新增响应头、选择、分批、失败降级和余弦归一化测试；
- `README.md`、`PRODUCT_SPEC.md`、`PROJECT_GOALS.md`、`SELF_TEST.md`、OpenAPI：同步版本 0.4.2 和验收说明。

## 3. Provider 选择规则

```text
OFFLINE_MODE=true
  → hash，不访问网络

OFFLINE_MODE=false + EMBEDDING_PROVIDER=hash
  → Chat 可以在线，检索仍是 hash

OFFLINE_MODE=false + EMBEDDING_PROVIDER=openai-compatible
  → 校验独立 Key/Base URL/Model
  → 调用 /embeddings
  → 成功：使用真实向量
  → 失败：rollback 当前会话 → hash 重试
```

法规搜索和同步案件分析没有显式“离线/在线”参数，因此按全局配置选择。Agent 的 `mode=offline` 是用户对单次任务的明确承诺，必须强制哈希；`mode=agent` 才允许使用在线 provider。

## 4. 为什么 Chat 与 Embedding 必须分开

Chat 模型接收 messages 并生成文字，Embedding 模型接收文本并输出固定维度数值数组。两者端点、模型、计费、批量限制和 Key 可能完全不同。服务声称“OpenAI 兼容”通常也只代表兼容某一组接口，不能推导它一定实现 `/embeddings`。

当前 DeepSeek 官方文档展示 Chat/Completions 模型，没有本项目可以调用的 Embedding 模型。因此保留 `LLM_*` 给 DeepSeek Chat，同时使用独立 `EMBEDDING_*` 连接百炼等明确提供 OpenAI 兼容 `/embeddings` 的服务。

## 5. 分批索引和多模型共存

`ensure_article_embeddings` 先按 provider/model 和正文哈希找出待更新法规，再按 `EMBEDDING_BATCH_SIZE` 切片调用。所有批次返回成功且维度一致后才写入数据库，避免前两批成功、第三批失败时留下半套索引。

表上的唯一键为 `(article_id, provider, model)`，所以哈希 384 维和在线 1024 维可以同时保存。检索只加载本次 provider/model 对应的向量，不会混算不同维度。正文没有变化时再次索引返回 `updated=0`，减少费用。

## 6. 真正的余弦相似度

修正后的公式是：

```text
cosine(a, b) = dot(a, b) / (norm(a) * norm(b))
```

任一向量为零向量时返回 0；维度不一致时仍抛出错误。测试使用 `[2, 0]` 和 `[3, 0]` 验证结果为 1，证明计算不再依赖供应商提前归一化。

## 7. 可观测性

法规搜索响应新增：

```text
X-Embedding-Provider
X-Embedding-Model
```

这两个响应头已经加入 CORS `expose_headers`，前端也可以读取。Agent 轨迹继续记录 `provider=...`。在线配置或调用失败时，日志分别记录 `embedding_provider_configuration_fallback` 或 `embedding_provider_request_fallback`，但不记录 API Key。

## 8. 测试结果与未完成的外部验收

离线自动测试增加到 39 项，覆盖：

- 环境变量能选择 OpenAI 兼容 provider；
- 36 条法规按照最多 10 条一批处理；
- Fake 在线服务失败后回滚并返回哈希结果；
- 搜索响应头显示实际 hash provider/model；
- 未归一化外部向量仍得到正确余弦相似度。

Ruff、mypy 和全部离线测试通过。测试入口继续清除真实 Key，因此没有产生第三方调用或费用。由于用户尚未提供独立 Embedding Key，本次没有声称 `text-embedding-v4` 已在本机调用成功；真实联网验收保留在 `PROJECT_GOALS.md` 的外部验收清单中。

## 9. 面试可能追问

问题：“为什么在线 Embedding 失败不直接让整个请求失败？”

回答要点：法律检索是核心可用性链路，项目有明确的离线基线。在线失败后回滚未完成事务并使用已有哈希索引，可以保持服务可用；同时通过响应头、节点轨迹和日志明确降级，避免静默伪装成在线结果。

问题：“为什么不同模型的向量不能直接比较？”

回答要点：不同模型的维度和向量空间不同，即使维度相同，坐标语义也不同。索引必须按 provider/model 隔离，查询向量和文档向量必须由同一模型生成。

问题：“为什么要先 check 再 reindex？”

回答要点：连接测试只发送一个短文本，能够低成本发现 Key、地域、Base URL 和模型名错误；确认后再批量处理全部法规，避免配置错误造成整批失败或不必要费用。

# 2026-07-26：案件类型空字符串校验与安全降级

## 1. 问题现象

Agent 运行轨迹显示“案件要素提取完成，来源=llm，类型=”，说明模型接口已经真实调用成功，但返回的案件类型是空字符串。页面只是忠实展示后端持久化结果，问题不在前端样式，也不代表 `.env` 或 API Key 没有生效。

旧版 `CaseFacts` 的 `case_type` 写成：

```python
case_type: str = "未识别"
```

这里的默认值只在模型完全不返回 `case_type` 字段时生效。模型若明确返回 `{"case_type": ""}` 或只包含空格，Pydantic 会把它视为合法字符串，LLM 客户端也就不会触发结构化输出修复或规则降级。

## 2. 修改或新增的关键文件

- `app/schemas.py`：为 `CaseFacts.case_type` 增加去除首尾空格和非空校验；
- `app/services/case_agent.py`：提示词明确要求案件类型非空，无法判断时返回“未识别”；
- `tests/test_second_week.py`：增加连续两次空类型的端到端回归测试；
- `app/main.py`、`pyproject.toml`、`docs/openapi.json`：版本更新为 0.4.3，并在接口契约中声明最小长度；
- `README.md`、`PRODUCT_SPEC.md`、`PROJECT_GOALS.md`、`SELF_TEST.md`、`docs/API_GUIDE_DETAILED.md`：同步功能、测试数量和验收说明。

## 3. 实现方式

`CaseFacts` 在接收数据时先执行 `strip()`。如果处理后仍为空，校验器抛出 `ValueError("案件类型不能为空")`。这不是为了让整个任务失败，而是把业务上不可用的数据转换为结构化输出错误。

项目原有的 `OpenAICompatibleLLM.invoke_structured` 会捕获 Pydantic 校验错误，把错误信息加入修复提示并再调用模型一次。最多尝试两次，避免无限重试。第二次仍无效时抛出错误码 `LLM_INVALID_OUTPUT`，`analyze_case_agent` 捕获该错误并调用规则分析器。

## 4. 修复后的数据流

```text
模型返回 {"case_type": "   "}
  → CaseFacts 去除空格
  → 非空校验失败
  → LLM 客户端追加校验错误并修复一次
  ├─ 第二次返回有效类型 → source=llm
  └─ 第二次仍为空
       → LLM_INVALID_OUTPUT
       → analyze_case_agent 捕获
       → 规则识别
       → source=rules_fallback
       → 页面显示实际案件类型
```

这条链路同时保留了模型自我修复能力和离线兜底能力，也让前端的“来源”字段与真实执行过程一致。

## 5. 自动测试与实际结果

新增用例让 Fake LLM 连续两次返回 `{"case_type":"   "}`，并验证：

- 模型客户端一共调用两次，证明只修复一次；
- 最终来源为 `rules_fallback`；
- “拖欠工资、未签劳动合同”的测试文本被规则识别为“劳动争议”；
- 回退原因包含 `LLM_INVALID_OUTPUT`。

实际执行结果：

- Ruff format：通过，34 个文件无需调整；
- Ruff check：通过；
- mypy：18 个源文件无类型错误；
- 离线自动测试：40 项全部通过，用时约 1.6 秒；
- 测试入口清除了真实模型密钥，没有产生第三方请求或费用。

## 6. 已知限制

1. 修复只影响之后新建或重试的 Agent 任务，数据库中已经完成的旧任务不会自动改写；需要重新提交或使用重试接口生成新任务。
2. 模型返回“未识别”是一个非空的有效值，目前不会自动回退。这样可以区分“模型明确表示无法判断”和“模型违反输出契约”。如果后续希望进一步补全，可增加“LLM 未识别时使用规则候选”的融合策略。
3. 案件类型非空不等于类型一定正确，准确率仍需通过评测集和人工复核判断。

## 7. 面试可能追问

问题：“为什么不在前端遇到空值时直接显示‘未识别’？”

回答要点：前端补默认文案只能掩盖脏数据，数据库、报告和其他 API 仍会得到空值。把校验放在结构化业务模型层，可以让所有入口共享同一约束，并触发现有的修复和回退机制。

问题：“为什么允许模型再试一次？”

回答要点：结构化输出错误经常可以通过把校验信息反馈给模型修复；但无限重试会增加费用和延迟，所以项目限定一次修复，仍失败就使用确定性的规则基线。

问题：“为什么来源最终写成 `rules_fallback` 而不是 `llm`？”

回答要点：模型虽然被调用过，但最终可用案件类型来自规则。记录实际产出来源有利于调试、效果评测和向用户说明降级情况，不能把曾经调用过模型等同于最终结果由模型生成。

# 2026-07-26：知识库管理前端与 TXT 条文导入

## 1. 解决的问题

后端已经有 `POST /api/v1/knowledge/articles`，能够完成单条法规新增、重复校验、数据库写入和向量索引，但普通使用者只能通过 Swagger、Apifox 或代码调用。这个交互方式不适合作品演示，也不便于学习“前端表单如何连接已有 API”。

本次新增独立的“知识库管理”页面。使用者可以填写法律名称、条号、权威来源和正文，也可以选择本地 TXT 自动填充正文。保存成功后页面显示数据库生成的 `article_id`，顶部法规数量同步增加，新条文无需重启即可参与后续检索。

## 2. 修改或新增的关键文件

- `frontend/src/KnowledgePage.tsx`：法规录入页面、客户端校验、TXT 读取、提交状态和成功反馈；
- `frontend/src/App.tsx`：增加案件分析与知识库管理导航，使用 URL Hash 切换页面；
- `frontend/src/api.ts`：封装 `createKnowledgeArticle` 请求；
- `frontend/src/types.ts`：增加法规创建请求与法规详情 TypeScript 类型；
- `frontend/src/styles.css`：增加桌面端、平板端和移动端响应式样式；
- `frontend/package.json`：前端版本更新为 0.4.4；
- `README.md`、`PRODUCT_SPEC.md`、`PROJECT_GOALS.md`、`SELF_TEST.md`：同步功能范围、目标和手工验收；
- `app/main.py`、`pyproject.toml`、`docs/openapi.json`：项目版本统一更新为 0.4.4。

## 3. 核心实现原理

### 3.1 不引入路由库的双页面导航

当前前端只有两个页面，没有必要为了简单切换额外引入 React Router。页面使用 `#analysis` 和 `#knowledge`：

```text
浏览器 Hash 改变
  → hashchange 事件
  → App 更新 page 状态
  → 渲染案件分析页或 KnowledgePage
```

这样直接打开 `http://127.0.0.1:5173/#knowledge` 可以进入管理页，刷新浏览器也不会丢失当前位置，同时没有增加生产依赖。

### 3.2 前后端共享字段约束

前端字段限制与 Pydantic `LegalArticleCreate` 保持一致：

- 法律名称：2–200 字符；
- 条号：1–64 字符；
- 正文：2–20000 字符；
- 来源：2–500 字符。

前端校验用于快速反馈，后端校验才是最终安全边界。使用者可以绕过浏览器直接调用 API，因此不能只依赖 HTML 或 TypeScript 检查。

### 3.3 TXT 是本地读取，不是二进制上传

选择 TXT 后，浏览器通过 `File.text()` 读取内容并填入受控 `textarea`。后端收到的仍然是统一 JSON：

```json
{
  "law_name": "中华人民共和国民法典",
  "article_number": "第五百七十七条",
  "content": "当事人一方不履行合同义务……",
  "source": "国家法律法规数据库 https://flk.npc.gov.cn/"
}
```

这种设计避免为同一业务再增加 multipart 接口。页面限制 TXT 不超过 1 MB，读取后仍执行 20000 字的单条正文限制。TXT 只用于输入便利，不绕过后端 Schema。

## 4. 完整请求与数据流

```text
用户手工填写或选择 TXT
  → 浏览器读取并显示正文
  → 前端 trim 和长度校验
  → POST /api/v1/knowledge/articles
  → Pydantic 再次校验
  → 按 law_name + article_number 查询重复
  ├─ 已存在 → HTTP 409 → 页面显示重复提示
  └─ 不存在
       → 写入 legal_articles
       → 使用当前 provider 建立法规向量
       → 返回 HTTP 201 + LegalArticleDetail
       → 页面显示 ARTICLE #ID
       → 顶部法规数量 +1
       → 新条文立即进入混合检索候选
```

页面提供两个连续录入动作：“继续添加本法条文”会保留法律名称和来源，只清空条号与正文；“录入其他法律”会清空全部字段。

## 5. 交互和安全设计

页面右侧不是装饰性文案，而是录入质量检查：

1. 使用法规正式全称；
2. 一条数据库记录只对应一个明确条号；
3. 保留国家法律法规数据库、中国人大网等可回查来源；
4. 确认法规公布、施行、修订和效力状态。

当前写接口没有管理员认证。页面明确显示“本地演示管理页，不能直接暴露公网”，避免漂亮的管理界面让人误以为已经具备生产权限控制。

## 6. 测试和实际结果

本次执行结果：

- Ruff format check：40 个文件格式正确；
- Ruff check：全部通过；
- mypy：21 个源文件无类型错误；
- 后端离线测试：40 项全部通过，用时约 1.5 秒；
- OpenAPI JSON：能够正常解析；
- TypeScript project build：通过；
- Vite 生产构建：189 个模块成功转换，构建约 3 秒；
- Chrome 无头渲染：以 1440×1100 分辨率打开 `#knowledge`，导航、Hero、表单和录入提示布局正常；
- 临时预览进程和渲染截图已在检查后清理，没有加入仓库。

现有后端接口测试已经覆盖：201 创建、409 重复冲突、422 空白字段拒绝、创建后立即搜索和详情回查。前端目前没有引入额外测试框架，因此交互部分使用 TypeScript 构建、真实浏览器渲染和 `SELF_TEST.md` 手工用例验收。

## 7. 已知限制

1. 知识库写接口尚无登录、管理员权限、CSRF 防护和操作审计，只能用于本地或受信网络演示。
2. 当前只支持单条录入；TXT 文件内容被视为一条正文，不会自动识别并拆分多个条号。
3. 没有法规列表、编辑、删除和下架功能；录错数据需要后续管理接口处理。
4. 数据模型尚未单独保存公布日期、生效日期、失效日期、效力状态和来源 URL。
5. 前端成功后对法规数量执行本地 `+1`；其他客户端同时写入时，需要刷新页面才能得到服务器最新总数。

## 8. 面试可能追问

问题：“为什么 TXT 不直接上传给后端？”

回答要点：后端业务资源是结构化法规，不是文件。前端读取 TXT 只是帮助填写正文，最终仍复用同一个 JSON API，从而保证手工输入和文件输入走完全相同的校验、判重、存储和索引链路。

问题：“前端已经限制长度，为什么后端还要校验？”

回答要点：浏览器校验可以被关闭或绕过，API 还可能被 Apifox、脚本和其他服务调用。Pydantic 是可信边界，前端校验只负责改善用户体验。

问题：“为什么现在不直接实现批量导入？”

回答要点：批量导入需要处理事务边界、部分成功、逐行错误、重复策略、费用控制和索引失败恢复。先把单条接口和界面做稳定，可以复用相同校验规则设计异步批量任务，而不是在前端循环调用后伪装成可靠批处理。

问题：“这个管理页能直接放到公网吗？”

回答要点：不能。当前缺少身份认证、角色授权、CSRF 防护、写入审计和限流。求职项目应明确安全边界；界面完成不等于生产级后台已经完成。

# 2026-07-26：知识库 TXT 导入示例

## 1. 完成功能与解决的问题

知识库管理页虽然支持 TXT 导入，但项目原来没有一份可以直接选择的示例文件，学习者仍然需要自己判断 TXT 中应该包含正文还是同时包含名称、条号等元数据。本次增加一份 UTF-8 示例，明确 TXT 只保存单条法规正文，其他结构化字段仍在页面表单中填写。

## 2. 关键文件

- `examples/labor_contract_law_article_9.txt`：可直接导入的《中华人民共和国劳动合同法》第九条正文；
- `SELF_TEST.md`：补充配套法律名称、条号、权威来源地址和操作方式。

## 3. 实现原理与数据流

```text
选择 examples/labor_contract_law_article_9.txt
  → 浏览器 File.text() 读取 UTF-8 正文
  → 正文填入 textarea
  → 用户填写法律名称、条号和来源
  → 前端组装 LegalArticleCreate JSON
  → 后端校验、判重、保存并建立索引
```

示例正文依据国家市场监督管理总局发布的《中华人民共和国劳动合同法》页面核对。TXT 不放 JSON、标题或说明文字，是因为导入组件会把文件全部内容作为 `content`。

## 4. 测试与实际结果

- 文件为纯 UTF-8 文本，正文非空且远小于 1 MB 和 20000 字限制；
- 法律名称与条号组合当前不在 36 条内置样例中，首次手工验收可以成功新增；
- 没有自动调用写接口，因此没有修改用户的正式 SQLite 数据库；
- 上传、保存、重复冲突和即时检索的验收步骤已写入 `SELF_TEST.md`。

## 5. 已知限制

同一数据库首次导入成功后，再次使用相同法律名称和“第九条”会按设计返回 409；这证明判重生效，不代表 TXT 文件损坏。示例只用于演示数据录入，正式用途仍应在录入时重新检查法规现行有效状态和权威原文。

## 6. 面试可能追问

问题：“为什么示例 TXT 不包含法律名称和条号？”

回答要点：当前 TXT 是正文输入辅助，不是批量交换格式。如果把元数据也混入 TXT，后端会把标题和说明误当成法条正文。单条录入使用表单承载结构化字段；未来批量导入应使用有明确 Schema 的 JSONL 或 CSV，并提供逐行错误报告。

# 2026-07-26：四行 TXT 批量导入与 200 条跨领域法规样例

## 1. 解决的问题

单条录入适合修正和少量维护，但一次增加几十到几百条时效率很低。简单地让前端循环调用单条接口还会带来三个问题：

1. 无法统一限制文件数量和总大小；
2. 中途失败后很难知道哪些已成功、哪些需要重试；
3. 前端解析结果可能被绕过，后端仍然需要可信解析和校验。

本次设计了明确的四行 TXT 协议、同步批量接口和逐文件结果，并提供 200 个可直接多选的示例文件。

## 2. 修改或新增的关键文件

- `app/services/knowledge_import.py`：四行 TXT 解析、UTF-8 校验、文件与批次限制常量；
- `app/schemas.py`：`KnowledgeBatchItem` 与 `KnowledgeBatchResponse`；
- `app/main.py`：`POST /api/v1/knowledge/articles/batch`；
- `frontend/src/KnowledgePage.tsx`：批量模式、多文件预检查、滚动预览和结果统计；
- `frontend/src/api.ts`、`frontend/src/types.ts`：multipart 请求与响应类型；
- `frontend/src/styles.css`：批量协议、文件列表和三类结果的响应式样式；
- `scripts/generate_batch_law_samples.py`：从记录的官方页面提取、验证并生成样例；
- `examples/batch_laws/`：200 个 UTF-8 TXT；
- `examples/batch_laws_manifest.json`：法律领域、来源 URL 与文件清单；
- `examples/BATCH_LAWS_README.md`：生成和使用说明；
- `tests/test_api.py`、`tests/test_services.py`：解析、编码、混合结果和 200 条唯一性测试；
- OpenAPI、接口参考、产品说明、项目目标、自测和 README：同步版本 0.5.0。

## 3. 文件协议

每个文件至少四行：

```text
第一行：法律名称
第二行：条号
第三行：来源
第四行起：正文
```

解析器不会把正文限定为一行。第四行及之后会用换行符重新连接，所以包含多款、多项或多个自然段的条文不会丢失结构。

示例：

```text
中华人民共和国劳动合同法
第九条
https://www.samr.gov.cn/……
用人单位招用劳动者，不得扣押劳动者的居民身份证和其他证件，
不得要求劳动者提供担保或者以其他名义向劳动者收取财物。
```

支持 UTF-8 和带 BOM 的 UTF-8；Windows `CRLF`、旧式 `CR` 和 Unix `LF` 会先统一为 `LF`。末尾空行会去除，字段首尾空白再交给 Pydantic 规范化。

## 4. 限制和安全边界

- 每批最多 200 个文件；
- 单个文件最多 128 KB；
- 整批读取内容最多 8 MB；
- 扩展名必须是 `.txt`；
- 单个文件为空、不是 UTF-8、少于四行或字段越界时标记为 `invalid`；
- 法律名称和条号与数据库已有记录重复，或在同一批内重复时标记为 `duplicate`；
- 不允许覆盖已有原文。

前端限制用于快速反馈，后端会重新读取原始文件并执行相同业务约束，因此不能通过修改浏览器状态绕过校验。

## 5. 请求和数据流

```text
用户多选 TXT
  → 浏览器 File.text() 预解析
  → 展示名称、条号、正文长度或错误
  → multipart/form-data，字段名 files
  → FastAPI 限制文件数量和总大小
  → knowledge_import 逐文件 UTF-8/四行/Pydantic 校验
  → 一次查询数据库已有 (law_name, article_number)
  → 批内集合再次判重
  ├─ invalid：不写数据库，保留错误
  ├─ duplicate：不覆盖，标记跳过
  └─ created：加入当前事务
       → flush 获得 article_id
       → 统一生成哈希 Embedding
       → 提交事务
       → 返回 ARTICLE #ID
  → 前端显示新增、重复、错误三个计数
  → 顶部知识库数量增加 created_count
```

响应使用 HTTP 200 表示“整批处理完成”。文件级失败不转换成整个请求的 409 或 422；调用方必须读取 `items[].status`。只有超过整批限制、缺少 multipart 字段或系统级数据库错误才使用请求级错误状态。

## 6. 为什么先实现同步批量

200 个小型 TXT 的解析和本地哈希向量计算在当前 SQLite 演示环境中可以快速完成，同步响应更简单，也能立即把逐文件结果展示给用户。

`POST /api/v1/knowledge/imports` 仍保留为未来规划：当支持大型 JSONL/CSV、在线 Embedding、跨进程执行和断点恢复时，应创建持久化导入任务并轮询进度，不能把长任务硬塞进当前同步接口。

## 7. 200 条样例的范围和生成方式

生成脚本记录 10 个可核验的国家市场监督管理总局公开页面，每部提取前 20 条：

| 领域 | 法律 | 数量 |
|---|---|---:|
| 劳动用工 | 中华人民共和国劳动合同法 | 20 |
| 消费者权益 | 中华人民共和国消费者权益保护法 | 20 |
| 资源与环境 | 中华人民共和国循环经济促进法 | 20 |
| 广告合规 | 中华人民共和国广告法 | 20 |
| 公平竞争 | 中华人民共和国反垄断法 | 20 |
| 价格监管 | 中华人民共和国价格法 | 20 |
| 计量监管 | 中华人民共和国计量法 | 20 |
| 药品监管 | 中华人民共和国药品管理法 | 20 |
| 电子商务 | 中华人民共和国电子商务法 | 20 |
| 食品安全 | 中华人民共和国食品安全法 | 20 |

脚本用标准库 `HTMLParser` 去除脚本和样式，根据行首“第……条”切分正文。若某部法律缺少第一至第二十条、总数不是 200，或者任何输出无法通过项目自己的 TXT 解析器，生成过程会失败而不是静默输出残缺数据。

`batch_laws_manifest.json` 保存生成日期、四行格式、领域、法律名称、来源 URL 和对应文件名。网页原文可能更新，因此重新生成是显式联网操作，不会在应用启动或自动测试时偷偷访问外部网站。

## 8. 自动测试和实际结果

新增 4 项测试：

1. 多行正文解析后保留换行；
2. 非 UTF-8 字节被拒绝；
3. 同一批包含合法、批内重复和不足四行文件时，响应分别为 `created / duplicate / invalid`；
4. `examples/batch_laws` 恰好有 200 个文件，全部能解析且法律名称与条号组合唯一。

实际结果：

- Ruff format check：42 个文件格式正确；
- Ruff check：全部通过；
- mypy：22 个源文件无类型错误；
- 离线自动测试：44 项全部通过，用时约 1.8 秒；
- TypeScript 和 Vite 生产构建：189 个模块成功转换，约 3.1 秒；
- OpenAPI JSON：正常解析，可重新导入 Apifox；
- 数据生成：200 个 TXT、10 个来源组，总大小约 92 KB；
- Chrome 以 1440×1200 实际渲染批量页面，协议、切换按钮、上传区域和安全提示布局正常；
- 临时预览进程和截图已清理；
- 自动测试使用测试数据库，生成示例本身没有写入用户的正式 SQLite 数据库。

## 9. 已知限制

1. 当前接口是同步处理，适合最多 200 个小文件，不适合数万条法规或耗时在线向量化。
2. 知识库没有管理员认证、权限和审计，不能直接部署到公网。
3. `legal_articles` 还没有数据库级唯一约束。应用层能处理普通重复，但多进程同时写相同名称和条号仍可能发生竞态。
4. 200 条来自 10 部法律的前 20 条，覆盖范围比原来的合同/劳动样例更广，但不是全量法规库，也不代表各领域重要条文的均衡抽样。
5. 36 条内置教学样例与新 200 条可能存在名称和条号交集，首次批量上传出现少量 `duplicate` 是正确行为。
6. 官方网页结构或法规版本以后可能变化。生成脚本会检查结构完整性，但正式法律服务还需要效力状态、版本更新和人工复核流程。
7. 当前没有“撤销本次导入”功能，上传前应先查看浏览器预览。

## 10. 面试可能追问

问题：“为什么一个错误文件不会回滚整批？”

回答要点：文件级格式错误在写入前已经隔离，用户更需要得到逐文件结果并保留其他有效数据。数据库级或索引级系统错误仍会使本次新增事务失败，避免出现法规写入但索引没有完成的半成品。

问题：“为什么不让前端循环调用 200 次单条接口？”

回答要点：循环调用缺少统一总量限制，网络开销大，中断后的成功范围难追踪，也无法在服务端做一次数据库判重查询和统一索引。批量资源应该有明确的批次协议和结果模型。

问题：“HTTP 200 中为什么允许有 invalid？”

回答要点：200 表示批量处理过程完成，`invalid` 是文件级业务结果。若把每个坏文件都变成整个请求的 422，调用方会失去其他文件的处理结果。响应中的三个计数和逐项状态才是业务成功判断依据。

问题：“怎样保证 200 条不是模型编造的？”

回答要点：生成脚本不调用 LLM。它从清单中记录的公开官方页面提取条文，保留每条来源 URL，并对条号连续性、总数、四行格式和唯一键做机器校验；同时文档诚实说明网页更新和法规效力仍需人工复核。

问题：“什么时候应该升级成异步导入任务？”

回答要点：当数据量超过同步请求可控范围、需要在线 Embedding、跨进程执行、断点续传、取消、重试或导入审计时，应持久化 import job，由 worker 执行并提供进度查询。

# 2026-07-26：Agent“未识别、hash、离线回退”联合故障修复

## 1. 用户看到的问题

用户用智能 Agent 提问“食物中毒商家需要负责吗”，第 35 次运行出现三个看似相关、实际独立的问题：

1. 案件要素提取显示 `来源=llm，类型=未识别`；
2. 第一次法规检索耗时约 42 秒，但轨迹显示 `provider=hash`；
3. 报告节点显示 `LLM_INVALID_OUTPUT`，最终使用离线模板。

如果只修改前端显示，会掩盖真实执行路径。本次先读取 `agent_runs.id=35` 的持久化轨迹，再检查脱敏后的 `.env` 配置和向量表 provider 分布。

## 2. 根因分析

### 2.1 “未识别”不是 LLM 没有运行

模型确实被调用并返回了合法 JSON，但它把短问题判断为信息不足，明确返回 `case_type=未识别`。原逻辑只拦截空字符串，不会对“未识别”继续处理；提示词也没有提供食品安全类别和短问题示例。

### 2.2 hash 是一次瞬时在线请求失败后的静默回退

配置检查确认：

- `OFFLINE_MODE=false`；
- `EMBEDDING_PROVIDER=openai-compatible`；
- Embedding Key、Base URL 和 `text-embedding-v4` 均已读取；
- 运行前只有 36 条真实向量，新导入法规仍需要补建。

第 35 次运行的第一次检索先为新法规补建真实向量，随后查询向量请求发生 Windows 连接超时。旧版 `retrieve_articles_configured` 捕获一次错误后立即使用 hash，而且 `RetrievalResult` 不携带原因，所以页面只能看到 `provider=hash`。工作流的第二次补充检索已经使用 `openai-compatible` 成功，这说明配置本身有效。

运行后数据库中 233 条法规已经同时拥有 233 条 hash 和 233 条 `openai-compatible` 向量，进一步证明第一次请求已经完成了大部分索引工作，问题是瞬时网络错误而不是 Key 缺失。

### 2.3 报告失败是 JSON 字段类型不稳定

`ReportDraft` 要求：

```json
{
  "suggestions": ["建议一"],
  "evidence_gaps": ["证据一"]
}
```

模型却把两个字段都返回为普通字符串。Pydantic 正确拒绝了错误类型，但旧版二次修复提示没有附带具体 Schema，模型再次返回字符串，最终触发 `LLM_INVALID_OUTPUT`。

## 3. 修改文件

- `app/services/case_analyzer.py`：新增食品安全、消费者权益和侵权责任分类词表；
- `app/services/case_agent.py`：增加具体分类提示，并在 LLM 返回“未识别”时融合本地分类结果；
- `app/schemas.py`：对常见的“字符串代替字符串数组”输出做受控归一化；
- `app/services/report_writer.py`：明确要求两个报告字段必须是 JSON 数组；
- `app/llm/client.py`：二次结构化修复提示加入校验错误和目标 JSON Schema；
- `app/services/mixed_retriever.py`：检索结果新增 `fallback_reason`；
- `app/services/retrieval_service.py`：在线请求重试一次，连续失败才回退 hash；
- `app/workflows/legal_report_graph.py`：把 Embedding 回退原因写入节点轨迹；
- `tests/test_services.py`、`tests/test_second_week.py`：增加四类回归测试；
- 产品说明、项目目标、配置、接口和自测文档：同步 0.5.1 行为。

## 4. 新的数据流

```text
用户问题
  → LLM 结构化案件要素
  → case_type 是具体类型
      → 直接使用 LLM 结果
  → case_type 是“未识别”
      → 保留 LLM 的缺失信息和追问
      → 本地分类器补全案件类型、关键事实和争议焦点
      → source=llm_enriched

法规检索
  → 选择配置的 openai-compatible provider
  → 第一次调用成功：返回在线结果
  → 第一次调用失败：回滚当前事务并重试一次
  → 第二次成功：仍返回在线结果
  → 连续两次失败：使用 hash，并把具体原因写入轨迹

报告生成
  → 提示词要求数组
  → 模型仍返回字符串时，Schema 前置校验将其变成字符串数组
  → 其他 Schema 错误进入带错误详情和 JSON Schema 的一次修复
  → 仍失败才使用模板报告
```

## 5. 为什么不是彻底删除 hash 回退

Agent 的“智能”不等于遇到网络故障就让整个任务失败。更合理的工程策略是：

1. 在线 provider 优先；
2. 对瞬时错误做有界重试；
3. 连续失败后保留可用的离线结果；
4. 明确告诉用户最终用了什么以及为什么。

旧版的问题不是存在 hash，而是一次错误就回退且原因不可见。修复后，回退仍能保证可用性，但不会冒充在线检索。

## 6. 测试与真实回归

新增或加强的自动测试包括：

1. “食物中毒商家需要负责吗”规则分类为食品安全与消费者权益纠纷；
2. LLM 返回“未识别”时融合本地分类，同时保留模型的缺失信息；
3. 报告数组字段为字符串时规范成列表；
4. 在线 Embedding 第一次失败、第二次成功时不使用 hash；
5. 连续两次失败时使用 hash，并返回可见的 `fallback_reason`。

使用本地真实配置进行了一次不写数据库的回归：

```text
llm_model=deepseek-v4-flash
case_source=llm
case_type=食品安全与消费者权益纠纷
retrieval_provider=openai-compatible
retrieval_model=text-embedding-v4
verified_citations=3
report_title=食物中毒索赔法律分析报告
report_fallback=None
```

命中的候选包括《食品安全法》第四条、《消费者权益保护法》第十八条和第十九条等。真实回归只输出 provider、模型和结果摘要，没有输出 Key。

## 7. 已知限制

1. 本地分类器是 LLM 的确定性兜底，不是完整案由体系；复杂案件可能同时涉及合同、侵权、行政责任和刑事责任。
2. 字符串转数组只处理字符串、换行和中英文分号等常见错误，不会猜测复杂嵌套对象。
3. 在线 Embedding 目前是同步请求。首次补建大量向量仍可能耗时，下一阶段更适合改成持久化后台索引任务并展示进度。
4. 连续两次失败后仍会使用 hash，这是明确的可用性策略；页面轨迹会显示原因，但当前没有“禁止任何回退”的严格模式。
5. 法律分析仍是技术演示，食品安全责任需要结合就餐凭证、诊断证明、因果关系和实际损失，并以现行有效法律为准。

## 8. 面试可能追问

问题：“为什么 LLM 返回未识别后还要规则补全，这不就是规则系统吗？”

回答要点：不是替换 LLM，而是融合。模型仍负责当事人、事实、信息缺口和追问，本地分类器只补全一个低风险的路由字段，并通过 `source=llm_enriched` 如实暴露执行方式。

问题：“为什么 Embedding 重试放在检索服务而不是工作流重试节点？”

回答要点：Embedding 网络重试属于 provider 调用层的瞬时故障处理；工作流重试用于第一次检索没有可信引用时扩展查询。两个重试解决的问题不同，不能混为一次业务重试。

问题：“为什么允许把字符串自动转成数组？”

回答要点：模型语义内容有效，只是违反了常见的容器类型约定。受控转换不会创造新事实，能减少无意义的整份报告回退；未知对象和其他类型仍由 Pydantic 拒绝。

问题：“怎样证明页面显示的在线 provider 不是写死的？”

回答要点：轨迹来自 `RetrievalResult.provider`，它由实际执行成功的 provider 返回。只有在线调用成功才会显示 `openai-compatible`；两次失败后结果对象会变成 hash，并同时携带失败原因。

# 2026-07-26：随机案件问题示例接口与前端“换一批”

## 1. 解决的问题

首页原来把三个案件问题直接写在 `App.tsx` 中。每次打开页面都看到相同内容，无法覆盖食品安全、消费者权益、电子商务等更多场景；其他调用方也不能通过 API 获取示例。

本次新增随机案件问题资源，使前端、Apifox 和其他客户端都能请求一批可直接提交给 Agent 的问题。

## 2. 关键文件

- `app/services/question_examples.py`：问题模板、变量池、分类列表和随机组合算法；
- `app/schemas.py`：`QuestionExample` 与 `QuestionExamplesResponse`；
- `app/main.py`：`GET /api/v1/examples/questions/random`；
- `frontend/src/types.ts`、`frontend/src/api.ts`：前端响应类型和请求方法；
- `frontend/src/App.tsx`：动态示例状态、初次加载和“换一批”；
- `frontend/src/styles.css`：刷新按钮样式；
- `tests/test_services.py`、`tests/test_api.py`：唯一性、分类和错误参数测试；
- `docs/openapi.json`、接口文档、产品说明、项目目标和自测文档：同步 0.6.0 契约。

## 3. 接口契约

```http
GET /api/v1/examples/questions/random?count=3&category=食品安全
```

`count` 默认 3，范围是 1～10。`category` 可省略；传入时必须属于 `available_categories`。

响应同时返回：

- `count`：实际生成数量；
- `requested_category`：本次筛选分类；
- `available_categories`：客户端可以使用的全部分类；
- `examples`：稳定 ID、分类和完整问题。

未知分类使用 422，而不是静默返回其他分类，避免调用方以为筛选已生效。

## 4. 核心实现原理

每个 `QuestionTemplate` 包含：

```text
category   案件分类
pattern    带命名占位符的问题句式
variables  每个占位符的候选值
```

例如食品安全模板可以随机选择餐馆、外卖店、超市等地点，再选择海鲜、熟食、预包装食品等对象以及中毒、过敏、就医等结果。组合数量远大于写死的三个问题。

服务用 `SystemRandom` 选择模板和变量，以集合去重。`example_id` 是“分类 + 最终问题”的 SHA-256 前 12 位，因此同一个问题的 ID 稳定，不需要数据库自增 ID。

自动测试可以注入带固定种子的 `random.Random`，从而兼顾生产随机性和测试可重复性。

## 5. 为什么不调用 LLM

这个接口的职责是准备演示输入，不是分析案件。调用 LLM 会带来额外延迟、费用、限流和不可重复性，而且模型失败会让首页最基础的体验入口不可用。

模板方案仍然能覆盖多领域，并且所有问题都经过人工设计。用户真正提交问题后，案件要素抽取、检索、审核和报告节点才按所选模式运行。

## 6. 请求与数据流

```text
打开首页
  → 前端 GET /examples/questions/random?count=3
  → 服务选择模板和变量
  → 去重并计算 example_id
  → 前端显示“示例 N · 分类”

用户点击“换一批”
  → 再次请求随机接口
  → 替换按钮，不修改当前文本框内容

用户点击某个示例
  → question 写入文本框
  → 用户点击“开始案件分析”
  → POST /runs 创建真正的 Agent 任务
```

前端保留三个本地兜底示例。首次加载接口失败时不会清空页面；只有用户主动点击“换一批”失败时才显示连接错误。

## 7. 测试

新增三项测试：

1. 固定随机种子生成 10 个食品安全问题，验证 ID、问题唯一且分类一致；
2. API 使用 `count=5&category=食品安全`，验证响应结构、数量和筛选；
3. 传入不存在的分类，验证返回 422 和可选分类提示。

完整离线测试总数更新为 51 项。随机示例测试不访问网络、不调用 LLM、不写业务数据库。

## 8. 已知限制

1. 两次独立请求可能随机到部分相同问题；接口只保证单次响应内部不重复。
2. 分类和模板目前仍在代码中维护，适合求职项目与演示；如果需要运营人员在线管理，应迁移到数据库或配置中心。
3. 随机问题是通用教学输入，不保证当前法规库对每个组合都能命中充分依据。
4. `example_id` 不是安全令牌，也不是持久业务资源 ID，只用于前端列表 key 和问题去重。
5. 当前接口没有用户偏好、难度等级、事实完整度或指定法律领域等高级筛选。

## 9. 面试可能追问

问题：“为什么使用 GET 而不是 POST？”

回答要点：它不修改服务器状态，也不需要复杂请求体；数量和分类是简单查询条件。随机性意味着响应不适合长期缓存，生产环境可以增加 `Cache-Control: no-store`，但不改变 GET 的资源读取语义。

问题：“随机接口怎么测试？”

回答要点：业务函数接受可注入的随机数生成器。生产默认使用 `SystemRandom`，测试传入固定种子的 `Random`，既能验证确定性结果，又不会把生产实现改成固定序列。

问题：“为什么 ID 使用内容哈希而不是 UUID？”

回答要点：内容哈希让同一分类和问题得到稳定 ID，不需要数据库，也方便客户端识别重复。这里只截取 12 位用于展示和列表 key，不把它用于强安全或全局唯一业务约束。

问题：“以后新增案件类型是否还要改前端？”

回答要点：不需要。接口返回 `available_categories`，示例对象也自带分类；前端直接展示服务端数据。当前只需要在后端模板配置中新增分类，进一步产品化时可以把模板迁移到管理端数据库。

# 2026-07-26：可选择的详细案件背景生成

## 1. 解决的问题

第一版随机接口生成的是一句话问题，例如“食物中毒商家需要承担什么责任”。这种输入适合验证接口连通性，却缺少时间、人物、事件经过、证据和诉求，导致 Agent 的案件摘要容易出现：

```text
当事人：材料未明确
关键事实：材料不足
诉求：材料未明确
```

本次在同一个随机接口中增加 `brief/detailed` 两种详细程度，让用户可以主动选择快速问题或完整教学案情。

## 2. 修改文件

- `app/services/question_examples.py`：模板增加 `detail_level`，新增九类详细案情模板；
- `app/schemas.py`：示例和响应增加详细程度字段；
- `app/main.py`：查询参数增加 `detail_level`；
- `frontend/src/types.ts`、`frontend/src/api.ts`：同步接口类型和参数；
- `frontend/src/App.tsx`：增加“简短问题 / 详细案情”选择；
- `frontend/src/styles.css`：增加模式选择样式；
- `tests/test_services.py`、`tests/test_api.py`：验证详细背景、长度、字段和错误参数；
- OpenAPI、接口参考、产品、目标、自测与 README：同步 0.7.0。

## 3. 接口设计

```http
GET /api/v1/examples/questions/random
    ?count=3
    &category=食品安全
    &detail_level=detailed
```

`detail_level` 使用受约束字符串：

- `brief`：一句话问题，也是默认值；
- `detailed`：多句完整案情；
- 其他值：HTTP 422。

保留 `brief` 默认值意味着旧版前端和已经保存的 Apifox 请求不需要修改。

## 4. 详细问题包含什么

每条详细模板尽量包含七类信息：

1. 时间：合同签订、入职、消费或事故日期；
2. 主体：消费者、劳动者、企业、经营者等虚构身份；
3. 法律关系：劳动、买卖、服务、网络交易或安全保障；
4. 事件经过：付款、履行、食用、受伤或沟通过程；
5. 损害结果：医疗费、误工、货款、质量问题等；
6. 已有证据：合同、订单、病历、照片、聊天和付款记录；
7. 明确诉求：退款、赔偿、补偿、继续履行或投诉路径。

这些字段没有单独写成 JSON，是因为接口最终目标是生成可直接粘贴进问题文本框的自然语言材料。Agent 随后再从自然语言中抽取结构化事实。

## 5. 数据流

```text
用户选择“详细案情”
  → 前端请求 detail_level=detailed
  → 服务只筛选 detailed 模板
  → 随机选择日期、人物、金额、事件和证据
  → 拼接多句案情
  → 返回 requested_detail_level + example.detail_level
  → 用户点击示例
  → 完整案情进入 question 文本框
  → 提交 /runs
  → LLM/规则抽取当事人、关键事实、诉求和信息缺口
```

“换一批”会携带当前模式，不会在用户选择详细后又请求默认的简短问题。

## 6. 为什么详细案情仍然使用模板

如果每次点击都调用 LLM 生成背景，会增加费用和等待时间，还可能生成违法、敏感或自相矛盾的事实。模板中的结构经过人工设计，变量只是虚构姓名、日期、金额、渠道和行为，可以稳定覆盖求职演示所需的抽取字段。

LLM 的能力应当体现在分析详细案情，而不是消耗在首页准备测试数据上。

## 7. 测试结果

新增一项服务层测试，并扩展两项接口测试：

1. 固定随机种子生成食品安全详细案情；
2. 验证长度超过 180 个字符；
3. 验证包含“保留”“想了解”“商家”等背景和证据要素；
4. 验证顶层与示例的 `detail_level=detailed`；
5. 验证五条详细案情均通过分类筛选且不重复；
6. 验证非法 `detail_level` 返回 422。

完整自动测试更新为 52 项。详细示例生成仍完全离线，不访问模型服务，也不写数据库。

## 8. 已知限制

1. 详细模板是教学案例，不是随机生成的真实案件，姓名、金额和日期均为虚构组合。
2. 模板保证常见事实字段齐全，但没有模拟所有证据矛盾、管辖、时效、主体资格等复杂问题。
3. 同一分类内长期大量调用仍可能遇到相似句式；当前只保证单次响应不重复。
4. 详细问题更长，会增加 LLM 输入 Token，但目前长度远低于系统的 5000 字问题限制。
5. 前端目前只选择详细程度，分类筛选已经由 API 支持，但尚未做成首页下拉框。

## 9. 面试可能追问

问题：“为什么不是增加一个新的 `/detailed` 接口？”

回答要点：简短与详细是同一种资源的表现参数，不是两个不同业务资源。放在同一接口可以共享数量、分类、去重和错误契约，也避免前端维护两个 URL。

问题：“详细案情为什么返回一段文本而不是结构化对象？”

回答要点：该接口用于准备 Agent 的自然语言输入，目标正是测试下游事实抽取。如果先返回结构化事实再拼接，反而绕过了需要演示的抽取能力。

问题：“怎么保证详细问题真的更详细？”

回答要点：详细模板从结构上包含七类信息，测试还验证长度阈值和关键背景词。更严格的版本可以把模板元数据也结构化，并在生成时逐项验证。

问题：“以后要增加极简、中等、专家级怎么办？”

回答要点：当前 Literal 适合两个稳定等级。等级增多后可以把它提升为配置化 profile，每个 profile 定义目标长度、必备事实槽位和适用模板，而不是继续堆布尔参数。

## 9. 求职重点标记

> **项目核心挑战：多层 AI 故障的定位、分层容错与降级透明性。**

这次问题已经被选为项目求职材料中的重点技术挑战。准备面试时，不要只背“加了重试”，应按以下顺序讲：

1. 同一次运行出现三种表象，为什么必须先通过轨迹拆分根因；
2. 为什么 LLM 合法输出“未识别”与接口调用失败是两回事；
3. 为什么保留 hash 回退，但必须有界重试并公开原因；
4. 为什么字符串转数组是受控契约修复，而不是篡改模型结论；
5. 如何用离线 Fake 测试和真实服务回归形成双层证据。

可直接背诵的 60 秒版本记录在 `docs/JOB_MATERIALS.md` 的“重点项目挑战”章节。

# 2026-07-26：Agent 将任意排版法规 TXT 整理为标准协议

## 1. 解决的问题

现有批量导入要求每份法规 TXT 严格遵守四行协议：

```text
第一行：法律名称
第二行：条号
第三行：来源
第四行起：正文
```

真实用户拿到的 TXT 往往包含标题符号、字段标签、空行、备注，字段顺序也不固定。让用户手工重排可以保证准确，但使用成本较高；直接让 LLM 解析后自动入库又会带来模型误识别、补写正文和错误来源污染知识库的风险。

本次新增一个“Agent 整理草稿”流程：模型负责从非标准文本中提取字段并生成标准四行文本，用户负责核对和确认入库。这样把擅长语义理解的 LLM 与确定性的数据库写入流程分开。

## 2. 修改或新增的关键文件

- `app/services/knowledge_normalizer.py`：文件解码、结构化 LLM Schema、提示词、原文定位检查和四行文本生成；
- `app/main.py`：新增 `POST /api/v1/knowledge/articles/normalize`；
- `app/schemas.py`：新增 `KnowledgeNormalizationResponse`；
- `frontend/src/api.ts`、`frontend/src/types.ts`：增加前端接口调用和响应类型；
- `frontend/src/KnowledgePage.tsx`：增加“Agent 整理”页签、预览、下载和填入单条表单；
- `frontend/src/styles.css`：增加整理结果、核对警告和移动端样式；
- `examples/unstructured_law_example.txt`：故意不遵守四行协议的测试文件；
- `tests/test_services.py`、`tests/test_api.py`：增加服务和 API 自动测试；
- `docs/openapi.json`、接口文档、产品文档、目标文档、自测文档和 README：同步 0.8.0。

## 3. 核心实现原理

### 3.1 受约束的结构化输出

模型不能返回一段自由文本，而必须符合 `KnowledgeNormalizationDraft`：

```text
law_name: string | null
article_number: string | null
source: string | null
content: string | null
confidence: 0..1
warnings: string[]
multiple_articles_detected: boolean
```

底层 LLM 客户端请求 OpenAI 兼容的 JSON 模式，再由 Pydantic 校验类型和长度。如果第一次输出不是合法 JSON 或字段类型错误，客户端只进行一次带 Schema 的修复；第二次仍失败则返回 502，避免无限重试。

### 3.2 不允许模型补写

System Prompt 明确规定：

1. 只能提取原文明确提供的信息；
2. 缺失名称、条号或来源时返回 `null`；
3. 正文只能去掉标签、页眉、页脚和无关说明，不得概括、改写或补写；
4. 多条法规只能生成第一条草稿，并标记必须人工拆分；
5. 只返回 JSON，不输出解释或 Markdown。

提示词不是唯一安全边界。服务端还会检查模型返回的名称、条号和来源能否在原文中逐字定位，并在去除空白后检查正文是否能在原文中连续定位。不能定位的字段会写入 `warnings`，并使 `ready_for_import=false`。

### 3.3 草稿与正式数据分离

整理接口不接收数据库 Session，也不调用法规创建或 Embedding 服务，所以它不会：

- 写入 `legal_articles`；
- 写入 `article_embeddings`；
- 改变 `/health` 返回的法规数量；
- 覆盖已经存在的法规。

用户只能下载标准 TXT，或者把草稿填入单条录入表单。真正保存时仍经过字段校验、“法律名称 + 条号”重复检查和向量索引。

### 3.4 文件和缺失字段处理

后端只接受一个 `.txt`，要求 UTF-8（允许 BOM），单文件不超过 128 KB、整理文本不超过 30000 字符。文件名先取 basename，下载名再删除危险字符。

字段缺失时，响应保留 `null`/空正文，并在 `standardized_text` 中写入：

```text
[待补充法律名称]
[待补充条号]
[待补充来源]
[待补充正文]
```

这样下载文件不会默默把缺失字段变成模型猜测，同时前端可以明确提示管理员补充。

## 4. 请求和数据如何流转

```text
用户选择任意排版 UTF-8 TXT
  → React 校验扩展名、空文件、128 KB
  → multipart/form-data POST /knowledge/articles/normalize
  → FastAPI 再次校验 MIME、扩展名、大小和 UTF-8
  → 将文件名和原始文本发送给 Chat LLM
  → Pydantic 校验结构化 JSON
  → 服务端检查字段能否回到原文定位
  → 生成标准四行 TXT + 缺失字段 + 警告
  → 前端展示模型、置信度、字段和预览
  ├─ 下载 UTF-8 BOM TXT
  └─ 填入单条录入表单
       → 人工核对
       → 用户主动保存
       → 数据库判重并建立检索向量
```

这里有两个不同的“确认”：

- `ready_for_import=true`：自动检查没有发现缺字段、多条内容或无法定位字段；
- 人工核对完成：管理员真的对照原文件和权威来源确认。只有后者才应该触发正式保存。

## 5. 接口契约

请求：

```http
POST /api/v1/knowledge/articles/normalize
Content-Type: multipart/form-data
file=<一个 TXT>
```

关键响应：

```json
{
  "law_name": "中华人民共和国食品安全法",
  "article_number": "第四条",
  "source": "国家法律法规数据库",
  "content": "食品生产经营者对其生产经营食品的安全负责。",
  "confidence": 0.95,
  "missing_fields": [],
  "warnings": [],
  "multiple_articles_detected": false,
  "ready_for_import": true,
  "requires_human_review": true,
  "standardized_text": "中华人民共和国食品安全法\n第四条\n国家法律法规数据库\n食品生产经营者对其生产经营食品的安全负责。",
  "model": "实际模型名"
}
```

错误语义：

- 413：文件超过大小限制；
- 415：不是 TXT；
- 422：空文件、非 UTF-8 或文本不合规；
- 502：外部模型请求或结构化输出失败；
- 503：离线模式或没有可用的 Chat LLM 配置。

## 6. 如何测试和实际结果

自动测试使用 Fake LLM，因此不会读取 `.env` 中的真实 Key，也不会产生费用：

1. 非标准标题、标签和空行可以转换成标准四行文本；
2. 文件名路径被清理，只保留安全 basename；
3. 缺失名称、来源和存在多条内容时 `ready_for_import=false`；
4. 未配置在线 LLM 时返回 503；
5. PDF MIME 返回 415；
6. 成功响应公开实际模型名并固定要求人工复核。

运行结果：

```text
python scripts\run_self_test.py
Ran 56 tests
OK

cd frontend
pnpm run build
✓ built
```

Ruff 静态检查通过。项目全量 mypy 仍有 16 个历史类型错误，集中在旧版 `main.py` 和第二至四周测试；本次新增的 normalizer、API 和测试文件没有新增 mypy 错误。

## 7. 已知限制

1. 当前一份文件只支持一条法规；多条只能提示拆分，还不能自动输出多个标准文件。
2. 只支持 UTF-8 TXT，不支持 Word、PDF、图片 OCR 或 GBK。
3. 依赖在线 Chat LLM，会产生 Token 费用和网络延迟；离线模式不能使用此功能。
4. `confidence` 是模型自评，只能辅助界面展示，不能作为法律真实性证明。
5. 原文定位检查可以发现明显改写，但不能证明法规现行有效，也不能验证来源网站权威性。
6. 如果原文使用“第4条”而模型标准化成“第四条”，逐字检查会要求人工核对；这是偏保守的安全策略。
7. 当前没有管理员账号、审批流和写入审计，因此知识库管理页面仍只适合本地或受信任环境。
8. 单条同步 LLM 请求可能需要数秒；大量文件应改成带并发和费用限制的异步任务。

## 8. 面试可能追问与回答要点

问题：“为什么 Agent 整理完成后不直接入库？”

回答要点：结构化 JSON 只保证格式正确，不保证事实正确。法律知识库错误会继续影响检索、引用和报告，所以模型输出必须停留在草稿层；人工确认后再走确定性的判重、持久化和索引流程。

问题：“既然有 Prompt，为什么还要检查字段是否出现在原文？”

回答要点：Prompt 是软约束，模型仍可能标准化、概括或幻觉。服务端原文定位是独立的确定性校验。它不能证明全部正确，但能阻止一批明显不可追溯结果被标为可导入。

问题：“`ready_for_import` 和 `requires_human_review` 是否矛盾？”

回答要点：不矛盾。前者表示程序级前置条件通过，后者表示业务级核验责任仍未完成。类似文件通过格式校验，不代表合同内容已经法务审批。

问题：“为什么不使用正则解析任意格式？”

回答要点：固定标签可以用正则，但真实文本的标签、顺序、空行和自然语言说明变化很大。LLM 适合做语义映射；文件限制、Schema、原文定位、缺失标记和人工确认继续由确定性代码负责。

问题：“如何防止用户在 TXT 中写提示词攻击模型？”

回答要点：原始文本作为数据放进 JSON user payload，System Prompt 明确只做字段抽取；输出必须通过固定 Pydantic Schema；服务端还做原文定位，且接口没有数据库写权限。即使文本诱导模型，最坏结果仍停留在需要核对的草稿，不会直接执行命令或污染知识库。

问题：“下一步如何支持批量和多条法规？”

回答要点：先用后台任务把每个文件拆成独立作业，限制总文件数、Token 预算和并发；对于一文多条，模型先返回候选数组和原文范围，服务端按范围切片，再让管理员逐条核对，不能直接把大模型生成的数组全量入库。

## 9. 真实模型补充回归

完成离线 Fake 测试后，又使用本机现有 `.env` 对 `examples/unstructured_law_example.txt` 做了一次不写数据库的真实调用。仅记录非敏感结果：

```text
model=deepseek-v4-flash
law_name=中华人民共和国食品安全法
article_number=第四条
source=国家法律法规数据库
ready_for_import=True
missing_fields=[]
warnings=[]
```

这次回归证明当前 OpenAI 兼容 Chat 配置可以完成新 Schema 的结构化输出。测试函数只调用 normalizer 服务，没有创建数据库 Session，也没有写入法规或向量记录。

# 2026-07-26：批量 TXT 导入规则在前端完整展示

## 1. 解决的问题

批量导入页面原来只用四个小卡片显示“第一行名称、第二行条号、第三行来源、第四行正文”。用户仍然不知道字段长度、文件大小、编码、判重方式和错误文件是否会影响整批，因此需要回到文档查找规则。

本次把批量导入所需的信息直接放在操作入口之前，让用户在选择文件前就能检查格式。

## 2. 修改文件

- `frontend/src/KnowledgePage.tsx`：新增可展开的完整规则区、标准文件示例和结果状态说明；
- `frontend/src/styles.css`：新增规则卡片、代码示例、状态说明和移动端布局；
- `PROJECT_GOALS.md`：追加本次完成清单；
- `SELF_TEST.md`：追加前端手工验收步骤；
- `docs/LEARNING_JOURNAL.md`：追加本学习记录。

## 3. 核心实现

规则区使用原生 HTML `details/summary`：

- 默认带 `open`，第一次进入批量页签即可看到；
- 用户可以收起，避免选择大量文件后页面过长；
- 不需要额外 JavaScript 状态；
- 键盘和浏览器原生无障碍行为比自制折叠按钮更稳定。

展示内容分为四层：

1. 四行协议和每个字段的长度；
2. 文件编码、数量、大小和一文件一条规则；
3. 前端预检查、后端复核与判重语义；
4. 标准文本示例和三种处理状态。

## 4. 数据流是否变化

本次只增加说明界面，不改变批量上传流程：

```text
用户阅读规则
  → 选择多个 TXT
  → 浏览器 parseBatchPreview 预检查
  → POST /api/v1/knowledge/articles/batch
  → 后端重新解析、长度校验、判重
  → 逐文件返回 created / duplicate / invalid
```

前端提示不是安全边界。用户可以绕过浏览器直接调用 API，所以后端校验仍然保留并作为最终结果。

## 5. 测试结果

- TypeScript 类型检查通过；
- Vite 生产构建通过；
- 规则区在 620px 以下改为单列布局；
- 后端接口和 Schema 没有变化，完整离线测试仍为 56 项。

## 6. 已知限制

1. 当前规则是前端静态文案；如果后端以后修改大小或字段长度限制，需要同步更新。
2. 页面提供示例但没有“一键下载空白模板”按钮。
3. 浏览器预检查使用 `File.text()`，乱码或特殊编码仍以后端 UTF-8 解码结果为准。
4. 当前没有自动化浏览器截图测试，视觉效果需要按 `SELF_TEST.md` 手工检查。

## 7. 面试可能追问

问题：“为什么前端展示规则后，后端还要重复校验？”

回答要点：前端校验改善体验，但客户端不可信，API 可以被 Apifox、脚本或修改后的页面直接调用。文件安全、字段合法性、数量限制和判重必须由后端再次执行。

问题：“为什么使用 details，而不是 React useState？”

回答要点：这里只需要一个没有业务副作用的折叠区，原生组件代码更少，自带键盘操作和展开语义。只有需要记录展开状态、动画编排或跨组件联动时才值得引入 React 状态。

问题：“规则常量如何避免前后端不一致？”

回答要点：当前求职项目通过文档和构建检查维护。生产化可以增加一个只读元数据接口，返回支持格式、字段长度和文件限制，由前端动态渲染；后端仍保留真正校验。

# 2026-07-26：制定多轮追问、人工审批与生产化 Agent 路线图

## 1. 解决的问题

项目已经完成四周主线和若干增量功能，但未来需求散落在产品、自测和对话中，缺少一份可以直接按周执行的统一方案。尤其是当前 `CaseFacts` 已经返回 `missing_information` 和 `questions_for_user`，实际工作流却不会暂停等待回答；报告也没有正式的草稿和批准状态。

本次没有直接修改业务代码，而是先完成未来架构和实施边界，防止后续开发只增加聊天页面，却没有持久状态、恢复、幂等和审批。

## 2. 新增和修改文件

- `docs/FUTURE_OPTIMIZATION_PLAN.md`：新增第 5～12 周详细优化计划；
- `PROJECT_GOALS.md`：追加未来计划索引和待办状态；
- `README.md`：增加未来路线入口；
- `docs/LEARNING_JOURNAL.md`：追加本记录。

## 3. 计划的核心主线

```text
案件分析
  → 判断关键事实是否缺失
  → LangGraph interrupt 暂停
  → 用户回答或上传补充材料
  → checkpoint 恢复
  → 法规检索与引用审核
  → 报告草稿
  → 人工批准 / 修改 / 驳回
  → 最终报告
```

计划同时定义：

1. `waiting_for_user`、`waiting_for_approval` 等状态；
2. thread、message、interrupt、report version 数据模型；
3. pending-action、clarification、approval 等接口草案；
4. Idempotency-Key、state version 和唯一约束；
5. 追问轮数、问题数量和超时边界；
6. 前端追问卡片、会话时间线和版本差异；
7. 重启恢复、重复提交、并发审批和越权测试；
8. 法规效力、OpenTelemetry、持久队列、RBAC、安全和 MCP 后续阶段。

## 4. 为什么先做计划而不是直接写代码

多轮 Agent 涉及工作流、数据库、接口、前端和任务执行方式。直接在当前一次性 `AgentRun` 上增加一个“回答”字段，无法处理：

- 回答对应哪轮问题；
- 服务重启后从哪里继续；
- 两个浏览器重复提交；
- 节点恢复产生重复副作用；
- 报告哪个版本被批准；
- 谁批准、何时批准、修改了什么。

先固定状态机、数据归属和幂等边界，可以减少后续返工。

## 5. 当前结论

下一步最小切片不是实现所有规划，而是：

```text
缺少合同交货日期
  → Agent 进入 waiting_for_user
  → pending-action 返回一个问题
  → 用户提交日期
  → 原工作流恢复并生成报告草稿
```

这个切片成功后，再扩展多问题、多轮、附件和报告审批。

## 6. 验收结果

- 新计划文档已经覆盖目标、状态机、数据表、API、前端、测试、风险、周计划和面试问题；
- 所有新章节使用待办状态，没有把规划功能误写成已经实现；
- README 和项目目标已经提供可发现入口；
- 本次只修改 Markdown，没有改变 API、数据库或运行逻辑，因此不增加自动测试数量。

## 7. 已知限制

1. 计划中的表名和接口在实施时仍需要通过 ADR 最终确认。
2. LangGraph、OpenTelemetry 和 MCP 版本可能变化，正式开发前要再次核对官方文档。
3. 周期是求职项目估算，不是固定交付承诺。
4. PostgreSQL、Redis 和队列会提高启动门槛，必须继续保留离线演示路径。

## 8. 面试可能追问

问题：“为什么路线图第一项是 HITL，而不是多 Agent？”

回答要点：当前主要风险不是角色数量不足，而是信息缺失后无法继续交互、模型结果未经批准。HITL、checkpoint、幂等和审批更接近真实生产问题，也能在现有 LangGraph 基础上形成完整闭环。

问题：“为什么要同时保存 interrupt 和业务审批记录？”

回答要点：checkpoint 负责工作流恢复，业务表负责查询、权限、超时、并发和审计；两者职责不同，不能只依赖框架内部状态承担全部产品需求。

问题：“如何控制规划范围？”

回答要点：先完成一个合同日期追问的纵向切片，包含数据库、API、前端和恢复测试；验证设计后再横向扩展，而不是一次加入所有类型和基础设施。
# 2026-07-26：将未来路线图改为每周独立交付

## 1. 本次解决的问题

初版第 5～12 周路线虽然按技术模块拆分，但第五周“多轮追问”和第六周“人工审批”容易被理解为只有连续做完两周才形成一个可用功能。这种安排不利于求职项目展示：如果开发在任意一周结束，仓库中可能只留下数据表、状态或接口草案，却没有用户可以完整体验的新能力。

本次将计划改为“每周一个纵向切片”。每周都必须从用户入口出发，覆盖输入、业务处理、结果展示、异常处理、自动测试和文档；项目即使停在该周，也应比上一周多一个完整可用、可单独演示的功能。

## 2. 修改文件

- `docs/FUTURE_OPTIMIZATION_PLAN.md`：增加每周独立交付规则，重写第 5～12 周的独立新增功能、演示路径、任务和完成标准；
- `PROJECT_GOALS.md`：明确八周的独立功能，并特别写明第五周和第六周的边界；
- `README.md`：在项目入口说明路线采用“每周一个独立可用功能”的纵向切片；
- `docs/LEARNING_JOURNAL.md`：追加本次路线图修订记录。

## 3. 每周独立交付结果

| 周次 | 本周新增的完整功能 | 本周结束时可独立演示的结果 |
|---|---|---|
| 第 5 周 | 可暂停、可恢复的多轮追问 | Agent 追问缺失事实，用户回答后恢复原任务并生成当前最终报告 |
| 第 6 周 | 报告草稿与人工审批 | 审核人可以批准、要求修改或驳回，最终下载只读取批准版本 |
| 第 7 周 | 按案件日期检索有效法规 | 相同问题选择不同日期时返回当时有效的法规版本 |
| 第 8 周 | Agent 运行监控与费用面板 | 页面展示节点耗时、模型、Token、费用、重试和降级原因 |
| 第 9 周 | 重启不丢任务的持久队列 | Worker 重启后继续同一任务，浏览器通过 SSE 接收进度 |
| 第 10 周 | 登录、角色权限与审计中心 | 不同角色拥有不同操作权限，关键操作可以在审计页查询 |
| 第 11 周 | Agent 安全评测中心 | 一键运行攻击样例并输出安全报告，高危失败阻止发布 |
| 第 12 周 | MCP Server 外部接入 | 外部 MCP 客户端可以检索法规、回查原文和发起案件分析 |

用户反馈闭环、PostgreSQL/pgvector、官方法规同步、多租户和对象存储不再与第十二周捆绑，后续继续按“一周一个完整功能”单独规划。

## 4. 第五周与第六周的边界

第五周必须完成下面的完整闭环：

```text
缺少关键事实
  → Agent 暂停并提出问题
  → 用户提交回答
  → 从持久化 checkpoint 恢复
  → 继续检索、引用审核和报告生成
  → 生成当前版本可下载的 Markdown/PDF 最终报告
```

第五周不能把回答接口、恢复逻辑、前端追问卡片或恢复后的报告生成留到第六周。第六周的职责是在已经能生成完整报告的系统上新增“草稿—审批—发布”能力，即使使用一个不触发追问的案件，也能独立演示审批功能。

## 5. 计划拆分原则

允许后一周复用前一周已经稳定的能力，但不允许把本周未完成的闭环改名后交给下一周。例如：

- 可以：第五周完成追问并生成报告，第六周在报告上增加审批；
- 不可以：第五周只保存问题，第六周才实现回答和恢复；
- 可以：第八周监控现有同步任务，第九周再把任务迁移到持久队列；
- 不可以：第八周只埋点但没有任何可查看的监控接口或页面；
- 可以：第十周实现通用 RBAC，第十一周的安全评测复用这些权限；
- 不可以：第十周只有用户表，第十一周才出现可登录和可验证的权限功能。

这种拆分方式叫“纵向切片”：每周同时改动必要的前端、API、服务、数据和测试，以换取一个真实用户能够完成的场景，而不是只完成某一个技术层。

## 6. 验收方式

每周开始前先写出一条三分钟以内的独立演示路径，周末按照同一路径验收：

1. 必须存在用户可以访问的页面、命令或 API 入口；
2. 必须产生用户能理解的业务结果，而不只是数据库中多一张表；
3. 必须覆盖正常、错误、重复提交以及适用时的并发或重启场景；
4. 必须更新 OpenAPI、产品、目标、自测和学习文档；
5. 必须能在不开发下一周功能的情况下完成本周演示；
6. 必须诚实展示回退、限制和未完成内容，不能把基础设施配置写成已交付功能。

## 7. 本次验证结果

- 第 5～12 周均已写明“本周独立新增功能”；
- 八周均拥有独立演示路径和本周完成标准；
- 第五周明确输出当前最终报告和 Markdown/PDF 下载；
- 第六周明确只增加审批闭环，不负责补齐第五周追问；
- 第七至十二周均写明不依赖下一周的完成边界；
- 本次只修改 Markdown 计划文档，没有修改 API、数据库 Schema 或运行代码，因此没有新增或重跑自动测试；项目现有离线测试仍为 56 项。

## 8. 已知限制

1. 周计划是求职项目的工作量估算，实际开发时如果某周任务超量，应缩小同一功能的范围，不能把闭环拆到下一周；
2. LangGraph、OpenTelemetry、Redis Worker 和 MCP 的具体库版本可能变化，正式实施前需要重新核对官方文档并记录 ADR；
3. “可以独立运行”不代表所有周之间完全没有技术复用，而是每一周不能依赖未来尚未完成的功能才能验收；
4. 第六周加入审批后，产品中的“最终报告”语义会从第五周的当前报告升级为“已批准报告”，升级时需要保留兼容说明。

## 9. 面试可能追问

问题：“为什么按纵向切片，而不是先把所有数据库和后端做完再开发前端？”

回答要点：纵向切片能在每周形成可以验证的用户价值，尽早暴露跨层接口、状态和异常设计问题，也方便持续录制演示和更新简历。按技术层横向开发可能在数周内都没有完整场景，风险会集中到最后联调。

问题：“第五周为什么不直接把人工审批也一起做完？”

回答要点：多轮追问本身已经包含暂停、持久化恢复、幂等提交和前端交互，是一个完整且有面试价值的功能。第五周恢复后可以直接生成现有最终报告，所以它不依赖审批；第六周则把审批、版本和并发控制作为新的独立增量，范围清晰、验收路径也不同。

问题：“后一周复用前一周，为什么还叫独立？”

回答要点：独立指交付闭环独立，而不是代码完全隔离。软件功能会逐步叠加，但每周必须新增一个可单独说明、可单独测试、无需未来功能才能完成的用户场景。
# 2026-07-26：第五周多轮追问、持久化暂停与恢复

## 1. 解决的问题

此前 `CaseFacts` 已经包含 `missing_information` 和 `questions_for_user`，但它们只是报告中的提示字段。LangGraph 在 `analyze_case` 后仍会无条件进入法规检索和报告写作，因此即使合同交付问题没有写交货日期，系统也会带着缺失事实直接给出报告。

第五周把“发现信息不足”从一个展示字段升级为真正的工作流状态：

```text
analyze_case
  → 判断存在关键缺口
  → interrupt 持久化暂停
  → waiting_for_user
  → 用户提交回答
  → Command(resume)
  → 同一个 run_id 继续执行
  → retrieve_laws
  → review_citations
  → write_report
  → completed
```

恢复后直接生成当前最终报告并支持 Markdown/PDF 下载，因此第五周是独立完整功能，不依赖第六周人工审批。

## 2. 修改和新增的关键文件

- `app/workflows/legal_report_graph.py`：增加分析后条件路由、`clarify_user`、`interrupt`、`Command(resume=...)`、SQLite checkpointer 和中断结果持久化；
- `app/models.py`：为 `AgentRun` 增加轮次、状态版本和 checkpoint thread ID；新增 `AgentClarification`；
- `app/migrations.py`：为已有 SQLite 数据库增量增加第五周字段和唯一索引；
- `app/schemas.py`：新增待办、问题、回答、提交响应 Schema，并扩展任务状态响应；
- `app/main.py`：新增待办查询和回答提交接口，加入幂等和乐观锁校验；
- `app/services/case_analyzer.py`：离线识别合同交货日期或履行期限缺口；
- `app/services/case_agent.py`：要求在线模型不要重复追问已经回答或明确“不清楚”的事实；
- `app/config.py`、`.env.example`：增加最大追问轮数和每轮问题数；
- `requirements.txt`、`pyproject.toml`：加入 `langgraph-checkpoint-sqlite`；
- `frontend/src/App.tsx`、`api.ts`、`types.ts`、`styles.css`：增加追问卡片、回答、恢复状态、刷新找回和轨迹节点；
- `tests/test_fifth_week.py`：新增 6 项第五周专项测试；
- `docs/openapi.json`、接口文档、产品、目标、自测、配置、求职材料和 README：同步 0.9.0。

## 3. 为什么同时需要 LangGraph checkpoint 和业务追问表

LangGraph checkpoint 保存的是“程序如何继续”：

- 当前图状态；
- 下一步要执行的节点；
- interrupt ID 和 thread；
- 已经完成的节点结果。

`agent_clarifications` 保存的是“产品如何查询和管理待办”：

- 第几轮；
- 向用户展示哪些问题；
- 用户回答了什么；
- 哪个状态版本发出和回答；
- 使用了哪个幂等键；
- 创建和回答时间。

只保存业务问题，服务重启后不知道图从哪里继续；只保存框架 checkpoint，前端、审计和并发控制又需要理解框架内部表。两者职责不同，通过 `run_id` 和 `checkpoint_thread_id` 关联。

当前 SQLite 演示项目使用官方 `langgraph-checkpoint-sqlite` 的同步 `SqliteSaver`。它适合本地演示和小型项目；生产环境多进程部署应改用 PostgreSQL checkpointer。LangGraph 官方文档强调，interrupt 需要持久 checkpointer 和稳定 `thread_id`，恢复时使用同一个 thread 调用 `Command(resume=...)`。

## 4. 状态和版本如何变化

一次正常追问的状态变化：

| 时点 | status | state_version | 说明 |
|---|---|---:|---|
| 创建 | `queued` | 0 | 后台任务尚未开始 |
| 抽取 | `analyzing` | 0 | 检查缺失信息 |
| 暂停 | `waiting_for_user` | 1 | checkpoint 和问题均已保存 |
| 回答受理 | `resuming` | 2 | 回答已写库，恢复任务已提交 |
| 完成 | `completed` | 3 | 报告和引用已保存 |

回答请求必须提交待办接口返回的 `state_version`。数据库使用条件更新：

```text
WHERE run_id = ?
  AND status = 'waiting_for_user'
  AND state_version = expected_state_version
```

只有影响一行才允许继续。两个浏览器同时提交时，第一个把状态改为 `resuming` 并把版本加一，第二个条件更新失败并收到 409。

## 5. 幂等处理

乐观锁解决并发提交，幂等键解决“服务其实已经处理成功，但客户端没有收到响应，于是重试”的问题。

每轮回答要求 `Idempotency-Key`。`agent_clarifications` 对 `(run_id, idempotency_key)` 建立唯一约束。相同键再次提交时返回 `replayed=true`，不会：

- 再次合并回答；
- 再次调用 `Command(resume)`；
- 重复生成引用；
- 重复生成报告。

前端使用 `clarification-{run_id}-{action_id}` 作为稳定键。网络重试必须复用原值，不能每次生成新 UUID。

## 6. 追问如何有界结束

配置默认值：

```env
MAX_CLARIFICATION_ROUNDS=3
MAX_QUESTIONS_PER_ROUND=5
```

每次恢复后重新执行案件要素抽取。如果还有新的关键缺口并且未达到三轮，则再次暂停；达到三轮后即使仍有缺口，也继续检索和写报告，并把缺口保留在 `missing_information/evidence_gaps`。

这样既避免信息不足时武断作答，也避免模型不断提出相似问题导致任务永远无法完成。用户允许回答“暂不清楚”，系统不能强迫用户编造事实。

## 7. 前端数据流

```text
POST /runs
  → 保存 run_id 到 sessionStorage
  → 每 1.5 秒 GET /runs/{id}
  → status=waiting_for_user
  → GET /runs/{id}/pending-action
  → 渲染追问卡片
  → 用户逐题回答
  → POST /runs/{id}/clarifications
  → status=resuming
  → 继续轮询同一个 run_id
  → completed
  → 并行读取 report 和 citations
```

页面刷新后 React 从 `sessionStorage` 读取 run ID，再从后端重新获取状态和问题。`sessionStorage` 只负责找回 ID，真正的问题和 checkpoint 都在服务器 SQLite 中。

## 8. 测试和实际结果

第五周新增 6 项自动测试：

1. 暂停、回答、恢复、报告和 Markdown/PDF 下载；
2. 关闭并重新创建 FastAPI `TestClient` 上下文后继续恢复；
3. 过期 `state_version` 返回 409；
4. 漏答和未知问题 ID 返回 422；
5. 相同幂等键重复提交不重复恢复；
6. 模型连续返回缺口时最多追问三轮。

完整验证：

```text
Ruff lint：通过
mypy app：通过
离线自动测试：62 / 62 通过
TypeScript：通过
Vite production build：通过
OpenAPI JSON 语法：通过
```

自动测试通过 `scripts/run_self_test.py` 强制使用离线模式、哈希 Embedding 和测试数据库，不读取本机密钥，不产生真实模型费用。

## 9. 已知限制

1. 等待用户回答的 checkpoint 可以跨应用重启恢复，但正在检索或写报告时进程崩溃，任务不会自动被新 Worker 领取；这是第九周持久队列的范围；
2. SQLite `SqliteSaver` 适合本地演示，不适合多进程高并发生产部署；
3. 当前离线缺口规则重点实现合同交付日期场景；Agent 模式可以产生更丰富问题，但仍受模型质量影响；
4. 前端用 `sessionStorage` 保存一个当前 run ID，没有任务历史列表；关闭浏览器会话后需要通过已知 run ID 查询；
5. 当前问题只支持文本回答，不支持在追问卡片中追加附件；
6. 状态迁移使用轻量运行时迁移，生产环境应改用 Alembic；
7. checkpoint 表属于框架内部数据，不提供手工编辑功能。

## 10. 面试可能追问

问题：“为什么不能只把问题存进数据库，回答后重新跑整个 Agent？”

回答要点：从头执行会重复模型调用、检索和副作用，也无法准确表达暂停点。checkpoint 保存精确图状态，`Command(resume)` 从 interrupt 继续；业务表则负责查询、权限、幂等和审计。

问题：“为什么既有 Idempotency-Key 又有 state_version？”

回答要点：幂等键处理同一个客户端请求的网络重试；状态版本处理两个不同请求竞争同一状态。二者解决的故障模型不同，不能互相替代。

问题：“interrupt 节点为什么不能在暂停前做不可重复副作用？”

回答要点：恢复时 interrupt 所在节点会从节点开头重新执行。暂停前的写操作必须幂等，或者移动到 interrupt 返回之后。本项目的 `clarify_user` 在调用 interrupt 前只构造 JSON 问题，业务待办在图返回中断结果后统一落库。

问题：“为什么最多三轮？”

回答要点：需要在信息完整度、用户耐心、模型费用和任务可终止性之间取平衡。三轮是演示默认值，不是法律结论；通过配置可调整，并有自动测试保证达到上限后仍会结束。

问题：“如何证明重启后真的可以恢复？”

回答要点：测试先让任务进入 `waiting_for_user`，关闭第一个 FastAPI 测试上下文，再创建新上下文；新上下文从 SQLite 读取业务待办，重新打开 `SqliteSaver`，用相同 `checkpoint_thread_id` 和 `Command(resume)` 完成原 run，最后报告和导出均成功。

## 11. 2026-07-26 浏览器补充验收

使用实际前端页面完成了一次端到端验收：

1. 在离线模式提交“供应商收款后未交货、未写明交货期限”的案件；
2. 原运行 `RUN #73` 在 35% 进度进入 `waiting_for_user`；
3. 页面显示“第 1 / 3 轮追问”，询问合同约定的交货日期或履行期限；
4. 后端停止后，数据库中的追问记录和 LangGraph checkpoint 均未丢失；
5. 重新启动后端，在同一页面提交“收到全部货款后 7 日内交货，现已过去 30 日”；
6. 系统从同一个 `RUN #73` 恢复，轨迹显示“已合并第 1 轮用户回答”；
7. 运行最终达到 100%，生成报告、审核引用及 Markdown/PDF 下载入口。

这次验收同时证明了前端追问卡片、跨进程持久化、恢复执行和最终交付不是彼此独立的演示代码，而是一条完整可运行链路。

# 2026-07-31：Agent 开发实习面经与项目化回答手册

## 1. 解决的问题

项目原有 `JOB_MATERIALS.md` 已经提供简历描述和若干高频题，但没有说明问题来自哪些公开面经，也没有覆盖 2026 年 Agent 实习面试中频繁出现的 Planning、ReAct、MCP、Skill、Memory、Embedding 选型、SSE 断线恢复和生产化边界。

本次工作检索牛客公开可访问的 Agent 开发、AI 应用开发和小红书 AI Agent 岗位面经，将重复出现的问题与律镜项目逐项映射。目标不是生成通用八股，而是让每个回答都能区分：

- 项目已经实现、可以展示代码和测试的能力；
- 只理解原理、尚未实现的能力；
- 当前实验结果不支持、不能在面试中夸大的结论。

## 2. 修改或新增的关键文件

- `docs/AGENT_INTERVIEW_GUIDE.md`：新增完整面经来源、高频主题、24 道项目化问答、追问链、一页速记和技术校准资料；
- `README.md`：在资料导航中增加面试手册入口；
- `docs/LEARNING_JOURNAL.md`：追加本次调研和写作记录。

本次没有修改 Python、TypeScript、接口、数据库 Schema 或运行配置。

## 3. 核心整理原则

### 3.1 结论、证据、限制三段式

每个回答优先给出 30 秒结论，再引用项目中的状态机、接口、配置、测试或评测数据，最后主动说明限制。这样可以避免只背定义，也避免为了显得高级而声称做过 MCP、Multi-Agent 或生产级队列。

### 3.2 面经与技术事实分开

面经用于判断“面试官可能问什么”，不直接当作技术规范。ReAct、RAG、LangGraph checkpoint、MCP 和 Agent 安全分别使用论文、官方框架文档、协议规范和 OWASP 资料校准。

### 3.3 失败数据也要进入回答

当前 24 条教学评测集中：

- keyword Recall@5 为 0.7639；
- hash semantic Recall@5 为 0.6458；
- hash mixed Recall@5 为 0.6806；
- online mixed 尚未执行固定评测。

因此手册明确禁止声称“混合检索一定优于关键词”。更好的面试表达是承认哈希向量质量不足，再提出在线 Embedding 对照、权重搜索、Rerank 和 hard negative 评测方案。

## 4. 信息如何流转

```text
公开面经
  → 提取问题
  → 按项目、Agent、Tool/Memory、RAG、可靠性分类
  → 多篇重复主题标记优先级
  → 核对项目代码、配置、评测和已知限制
  → 编写 30 秒回答
  → 增加项目证据、追问和不能夸大的边界
  → 使用论文/官方文档校准术语
  → 汇总为面试手册和一页速记
```

## 5. 如何检查和实际结果

本次是纯文档交付，没有运行代码测试。完成了以下检查：

1. 核对 8 个公开面经/问题合集的标题、问题和可访问链接；
2. 核对 LangGraph 图节点、条件边、interrupt、checkpoint 和恢复代码；
3. 核对混合检索公式、Top-K、权重和 Embedding provider 行为；
4. 核对 24 条评测集与 `latest.md` 中的实际指标；
5. 核对当前自动测试数量为 62；
6. 核对项目数据库当前包含 241 条教学法规；
7. 检查新文档中的相对链接、Markdown 标题和 README 导航。

最终生成 24 道项目化问题，覆盖调研样本中主要的 Agent、RAG 和工程化追问。

## 6. 已知限制

1. 小红书站内笔记公开索引不稳定，本次主要使用牛客公开正文，其中包含小红书公司 Agent 岗位面经；
2. 面经由用户自行记录，可能存在记忆偏差，不能视为公司官方题库；
3. “高频”来自有限样本的归纳，不是统计学意义上的全网频率；
4. 面试题和框架版本会继续变化，投递前应重新检查目标公司的近期面经；
5. 手册覆盖 Agent 应用工程，不深入讲解 PPO、DPO、GRPO 等模型训练算法，因为本项目没有训练实践；
6. 项目数字会随着法规、测试和评测更新而变化，修改项目后需要同步速记页。

## 7. 面试中可能被追问的问题及回答要点

问题：“你为什么把没有实现的 MCP、Multi-Agent 也写进手册？”

回答要点：面试会根据岗位要求追问这些概念。正确做法不是假装做过，而是先说明项目当前边界，再给出何时需要、如何设计和需要补充哪些安全机制。理解取舍比堆叠框架更重要。

问题：“为什么直接展示不理想的 hash mixed 指标？”

回答要点：工程评测的价值是发现方案是否有效，而不是为简历挑数字。当前结果表明哈希向量不能代表真实语义模型，下一步需要在线 Embedding、权重搜索和 Rerank 对照；隐瞒结果反而无法解释选型。

问题：“如何证明这些答案不是通用 AI 生成的？”

回答要点：回答包含项目特有的图节点、`waiting_for_user`、`checkpoint_thread_id`、幂等键、状态版本、241 条教学法规、24 条评测集、具体检索指标和 62 项测试，并明确列出未实现功能。面试时可以直接打开对应代码和测试。

问题：“面试时应该把 24 道题全部背下来吗？”

回答要点：不需要逐字背。先掌握 30 秒项目介绍和三条核心追问链：可恢复工作流、检索评测、引用可信性。其余题目用“结论—项目证据—限制—下一步”的结构现场组织。

# 2026-07-31：第六周——报告版本与人工审批 Agent

## 1. 本周名称、目标与解决的问题

本周功能名称是“报告草稿、版本循环与人工审批发布”，发布版本为 `1.0.0`。

第五周完成了“信息不足时暂停追问，用户回答后恢复任务”，但报告一旦生成就会直接成为最终结果。这在法律场景中有明显风险：数据库可以证明法条引用确实存在，却不能证明模型对案件事实、适用关系、风险和行动建议的整体判断已经适合发布。

第六周把生成和发布拆成两个阶段：

1. Agent 先生成报告草稿；
2. LangGraph 在报告后第二次 `interrupt`；
3. 审核人批准、要求修改或驳回；
4. 要求修改时保留旧版本并生成新版本；
5. 只有被批准的版本才允许导出 Markdown/PDF。

这是一项本周独立可使用的完整功能。完成第六周后，用户已经可以在前端完成从草稿审核到最终发布的闭环，不依赖第七周任务。

## 2. 修改或新增的关键文件

### 2.1 后端数据和接口

- `app/models.py`
  - `agent_runs` 增加 `current_report_version` 和 `approved_report_version`；
  - 新增 `report_versions`，保存不可变报告正文、事实快照、引用快照、版本状态和修改摘要；
  - 新增 `agent_approvals`，保存审批轮次、动作、意见、审核人、幂等键和状态版本。
- `app/migrations.py`
  - 为已有 SQLite 数据库增加轻量运行时迁移，旧项目启动时自动补齐两个版本字段；
  - 新表仍由 SQLAlchemy metadata 创建。
- `app/schemas.py`
  - 新增审批动作、审批待办、审批提交/返回、报告版本摘要/详情；
  - 运行状态和报告响应增加版本、审批状态、是否最终版本等字段。
- `app/main.py`
  - 新增 `POST /api/v1/runs/{run_id}/approvals`；
  - 新增报告版本列表和版本详情接口；
  - `pending-action` 同时支持追问待办和审批待办；
  - 报告接口支持读取待审批草稿；
  - 导出接口只允许读取批准版本；
  - FastAPI/OpenAPI 版本升级到 `1.0.0`。

### 2.2 Agent 工作流

- `app/workflows/legal_report_graph.py`
  - 工作流从 `write_report -> END` 改为 `write_report -> approve_report`；
  - `approve_report` 使用 LangGraph `interrupt` 持久化暂停；
  - `approve` 和 `reject` 走向终态；
  - `request_changes` 进入 `revise_report`，生成新版本后再次回到 `approve_report`；
  - 使用同一个 `checkpoint_thread_id` 和 `Command(resume)` 恢复；
  - 审批暂停时同步保存引用快照，保证草稿页面也可以查看依据。
- `app/services/report_writer.py`
  - 新增报告修订函数；
  - Agent 模式要求模型返回完整修订 Markdown；
  - 离线模式不会猜测新事实，只追加明确的修改说明和人工核对提醒。

### 2.3 前端

- `frontend/src/types.ts`
  - 增加 `waiting_for_approval`、`revising`、`rejected` 状态；
  - 增加审批和报告版本类型。
- `frontend/src/api.ts`
  - 增加提交审批、查询版本列表和查询版本详情的方法。
- `frontend/src/App.tsx`
  - 显示待审批卡片、审核人、审批意见和三个动作；
  - 要求修改和驳回时强制填写意见；
  - 草稿可预览，但隐藏最终下载入口；
  - 显示 V1/V2 状态和 unified diff；
  - 批准后显示最终报告和下载入口；
  - 前端审批请求使用稳定幂等键，轮询逻辑避免因报告对象变化产生快速重复 effect。
- `frontend/src/styles.css`
  - 增加审批卡片、批准/修改/驳回按钮、草稿锁定提示、版本列表和差异视图样式。
- `frontend/package.json`
  - 版本升级到 `1.0.0`。

### 2.4 测试和文档

- `tests/test_sixth_week.py`
  - 新增 7 项第六周测试；
  - 覆盖批准、修改、驳回、并发、幂等、禁止未批准导出和跨重启恢复。
- `tests/test_api.py`、`tests/test_second_week.py`、`tests/test_third_week.py`、`tests/test_fifth_week.py`
  - 旧测试升级为新发布语义：报告生成后先待审批，批准后才是最终交付。
- `pyproject.toml`
  - 项目版本升级到 `1.0.0`。
- `README.md`、`PRODUCT_SPEC.md`、`PROJECT_GOALS.md`、`SELF_TEST.md`
  - 更新产品能力、周计划、运行流程、自测步骤和完成结果。
- `docs/API_REFERENCE.md`、`docs/API_GUIDE_DETAILED.md`、`docs/openapi.json`
  - 增加审批与版本接口；
  - OpenAPI 升级到 3.1.0，当前共 23 个接口，其中 19 个已实现、4 个规划中，可直接导入 Apifox。
- `docs/CONFIGURATION.md`、`docs/DEMO_SCRIPT.md`、`docs/JOB_MATERIALS.md`
  - 更新数据表、配置边界、三分钟演示和求职表达。
- `docs/FUTURE_OPTIMIZATION_PLAN.md`
  - 将第六周标记为已完成，并把后续工作顺延为独立周功能。
- `docs/AGENT_INTERVIEW_GUIDE.md`
  - 版本、测试数和项目介绍升级到 1.0.0 / 69 项测试；
  - 增加第二个人工 interrupt、版本保留和批准后发布亮点。
- `docs/decisions/0007-require-approval-before-report-release.md`
  - 记录“报告必须批准后才能发布”的背景、取舍、后果和限制。

## 3. 核心原理与为什么这样设计

### 3.1 “法条真实”不等于“结论可发布”

引用审核解决的是法条 ID、名称、条号和正文是否与数据库一致。人工审批解决的是更高一层的问题：案件事实是否理解正确、法条是否适用于这个事实、风险是否表达完整、建议是否可执行。两个审核对象不同，不能互相替代。

### 3.2 报告版本采用追加而不是覆盖

V1 被退回后仍保留为 `superseded`，V2 作为新行写入。这样可以回答：

- 哪一版被退回；
- 审核人提出了什么意见；
- 新版与旧版具体有什么差异；
- 最终批准的是哪一版。

如果只覆盖 `agent_runs.report_markdown`，上述审计信息都会丢失。

### 3.3 框架 checkpoint 与业务审批表职责不同

LangGraph checkpoint 保存“程序执行到哪个节点、恢复时需要什么状态”，适合 `Command(resume)`。`report_versions` 和 `agent_approvals` 保存“用户界面需要查询和审计的业务事实”。前端不直接读取框架内部 checkpoint 表。

### 3.4 Idempotency-Key 与 state_version 不能互相替代

- `Idempotency-Key` 处理同一个请求因超时而重试；
- `state_version` 处理两个不同页面或审核人竞争同一个待办。

审批接口先校验待办和预期状态版本，再用数据库条件更新抢占状态。只有更新成功的请求可以恢复 Agent；失败者返回 409。相同幂等键重放则返回原结果，不重复创建审批记录或报告版本。

### 3.5 发布限制必须在后端

前端隐藏下载按钮只能改善交互，用户仍可能直接调用导出 URL。因此导出接口会查询 `approved_report_version` 和对应 `ReportVersion.status=approved`。没有批准版本时返回 HTTP 409。安全和业务约束不能只依赖按钮是否可见。

## 4. 信息与状态如何流转

```text
提交案件
  -> analyze_case
  -> 信息不足？
       是 -> clarify_user interrupt
              -> waiting_for_user
              -> 回答接口（幂等键 + state_version）
              -> Command(resume)
              -> 重新抽取
       否 -> retrieve_laws
  -> review_citations
  -> write_report
  -> 创建 ReportVersion V1(draft)
  -> approve_report interrupt
  -> waiting_for_approval
       approve
         -> V1 approved
         -> completed
         -> approved_report_version=1
         -> 开放导出
       request_changes
         -> V1 superseded
         -> revise_report
         -> 创建 V2(draft)
         -> approve_report interrupt
       reject
         -> 当前版本 rejected
         -> 任务 rejected
         -> 禁止导出
```

审批恢复时始终使用同一个 `checkpoint_thread_id`。报告版本正文、事实快照和引用快照是业务审计数据；图状态只负责把 Agent 从正确节点继续执行。

## 5. 自动测试、静态检查和实际结果

本次最终执行：

```powershell
python scripts\run_self_test.py
python -m ruff format --check app eval scripts tests
python -m ruff check app eval scripts tests
python -m mypy app
cd frontend
pnpm run build
```

结果：

- 69 / 69 项离线测试通过；
- 第六周新增 7 项测试；
- Ruff format、Ruff lint、mypy 通过；
- TypeScript 检查和 Vite 生产构建通过；
- OpenAPI JSON 可以正常解析；
- 自动测试使用 Fake LLM，不读取真实模型密钥，不产生模型费用。

第六周 7 项测试分别证明：

1. 草稿可查看，但 Markdown/PDF 导出均被后端拒绝；
2. 批准后发布的正文与被批准版本完全一致；
3. 要求修改生成 V2，V1 保留为 `superseded`，diff 非空，V2 可继续批准；
4. 驳回保留草稿和审计数据，但禁止发布；
5. 两个并发审批只有一个通过乐观锁；
6. 相同幂等键重放不会重复生成审批或版本；
7. 等待审批时关闭并重新创建 FastAPI 测试上下文，仍能读取待办并继续。

## 6. 浏览器端到端验收

使用独立临时数据库和离线模式实际操作了 `RUN #1`：

1. 提交合同案件；
2. 先进入第五周追问，回答后恢复；
3. V1 进入待审批，页面显示草稿锁定，没有最终下载；
4. 填写修改意见并点击“要求修改”；
5. 生成 V2，V1 标记“已被新版本替代”；
6. 点击 V2 显示相对 V1 的 unified diff；
7. 批准 V2；
8. 页面显示“已批准最终报告 · V2”，Markdown/PDF 链接同时出现。

这个验收证明两个 interrupt 和修改循环可以在同一真实前端任务内连续运行。

## 7. 已知限制与后续方向

1. 当前审核人只是普通文本，没有账户登录、签名、RBAC 和权限校验；
2. SQLite 适合单机演示，不适合生产高并发审批；
3. 后台恢复任务仍由 FastAPI 进程内执行，进程在执行中崩溃时需要持久任务队列重领；
4. Agent 模式修订依赖模型结构化输出，失败时会透明使用保守离线修订；
5. 离线修订只记录意见，不会假装已经理解并补写法律事实；
6. 当前 diff 是文本统一差异，还没有段落级批注、局部批准或多人会签；
7. 旧版 `completed` 且没有 `report_versions` 的历史任务保留兼容导出，仅用于平滑升级；
8. 产品仍是技术教学演示，不构成法律意见。

## 8. 面试可能追问与回答要点

### 问题一：为什么引用已经审核过，还需要人工审批？

回答要点：引用审核只证明“这条法条确实存在且原文一致”，不能证明它适用于当前事实，也不能证明整份风险判断和建议正确。法律场景需要把证据真实性、法律适用和最终发布分成不同控制层。

### 问题二：为什么用两张新表，不直接覆盖报告？

回答要点：报告版本和审批决定是不同实体。版本表保存不可变正文与快照，审批表保存谁、何时、为什么作出什么决定。追加数据可以做 diff、回溯和审计；覆盖一列会丢失历史。

### 问题三：为什么既有幂等键，又有乐观锁？

回答要点：幂等键处理同一网络请求重试，乐观锁处理不同请求竞争。一个页面超时重试与两个审核页面同时点击是不同故障模型，所以需要两层保护。

### 问题四：如何证明“只有批准后才能下载”不是前端效果？

回答要点：测试直接请求导出接口。`waiting_for_approval` 和 `rejected` 都返回 409；批准后同一路径返回 200，且正文与批准版本一致。约束在后端数据库查询和状态校验中执行。

### 问题五：为什么审批也使用 LangGraph interrupt，而不是普通状态字段？

回答要点：普通字段可以表示“待审批”，但不能自然恢复到图中的下一节点。interrupt 同时保存精确执行位置和状态，`Command(resume)` 可以根据批准、修改或驳回继续走不同边；业务表则负责查询、权限和审计。

### 问题六：要求修改会不会形成死循环？

回答要点：当前由人工决定是否继续退回，版本号每次递增并完整留痕。生产环境还应增加最大修改轮次、超时升级和撤回策略；本地教学版目前没有强制修改轮次上限，这一点需要诚实说明。

---

# 2026-07-31｜第七周：按案件日期检索法规版本

## 1. 本周解决的问题

前六周已经能够检索法条、生成报告并完成人工审批，但法规知识仍近似于“每个条文只有一个永远有效的版本”。真实法律场景中，同一个问题在不同日期可能适用不同法律：

- 2020 年发生的合同解除争议可能适用当时有效的《合同法》；
- 2021 年 1 月 1 日以后发生的同类争议应检索已经生效的《民法典》；
- 已废止不等于过去从未有效，历史案件不能简单删除旧法；
- 只保存 `article_id` 无法证明报告引用的是法规的哪个版本；
- 如果先做 Top-K 召回再过滤无效版本，无效条文会提前占据候选名额，真正适用的条文可能根本进不了 Top-K。

因此第七周独立交付一条完整闭环：用户输入案件发生日期，系统在召回前筛选当日有效的法规版本，引用审核同时核验条文和版本，报告与前端展示精确版本证据。

## 2. 主要修改文件

后端和数据层：

- `app/models.py`：新增 `laws`、`law_versions`，并为条文、案件、Agent、检索日志和引用增加日期或版本关联；
- `app/migrations.py`：为已有 SQLite 数据库增量补列和索引，不要求用户删除旧库；
- `app/services/law_versioning.py`：初始化法规实体与版本、绑定既有条文、准备《合同法》到《民法典》的历史切换演示数据；
- `app/services/mixed_retriever.py`：在关键词和向量计算前执行版本有效期过滤；
- `app/services/retrieval_service.py`：统一在线 Embedding、哈希回退和最终适用日期；
- `app/services/citation_reviewer.py`：审核 `article_id` 与 `law_version_id` 是否仍是数据库中的真实绑定；
- `app/services/report_writer.py`：把法规检索时点、版本标签、当前效力状态和适用区间写入 Markdown；
- `app/workflows/legal_report_graph.py`：让日期贯穿 LangGraph 状态、节点轨迹、引用快照和报告版本；
- `app/main.py`、`app/schemas.py`：为搜索、同步案件和 Agent 接口增加 `as_of_date`，响应增加版本字段和 `X-Law-As-Of-Date`；
- `tests/test_seventh_week.py`：新增 6 项第七周专项测试。

前端：

- `frontend/src/App.tsx`：新增可选案件发生日期，展示运行时点、版本、效力标签和引用详情；
- `frontend/src/api.ts`、`frontend/src/types.ts`：传递日期并接收版本字段；
- `frontend/src/styles.css`：补充日期控件、版本状态和详情抽屉样式；
- `frontend/package.json`：版本升级到 `1.1.0`。

文档：

- 更新 `README.md`、`PRODUCT_SPEC.md`、`PROJECT_GOALS.md`、`SELF_TEST.md` 和 `db.md`；
- 更新接口文档、配置文档、演示脚本、求职材料、面试指南和未来优化计划；
- 新增 `docs/decisions/0008-filter-law-versions-before-retrieval.md`；
- 重新生成并补充 `docs/openapi.json`。

## 3. 核心设计原理

### 3.1 法规与法规版本分开

`laws` 表表示法规的稳定身份，例如《中华人民共和国民法典》；`law_versions` 表表示某次发布或修订版本。条文通过 `law_version_id` 关联精确版本。

这样可以避免把法规名称、发布日期、效力状态和全部历史文本塞在同一张条文表里，也能表达一个法规多次修订的关系。

### 3.2 使用半开日期区间

版本适用条件定义为：

```text
effective_from <= as_of_date
并且
effective_to 为空，或者 as_of_date < effective_to
```

也就是 `[effective_from, effective_to)`。生效日包含，失效日不包含。《合同法》演示版本的区间是 `1999-10-01` 至 `2021-01-01`，所以 2020-12-31 仍能命中，2021-01-01 当天立即切换到《民法典》。

`status=repealed` 表示这个版本现在已经废止，不代表它在历史时点无效。是否适用于案件由日期区间判断，当前生命周期状态用于解释和展示。

### 3.3 在召回前过滤

正确顺序是：

```text
案件日期
  -> SQL 筛选当日有效版本
  -> 对剩余条文计算关键词分数
  -> 对剩余条文计算向量相似度
  -> 混合排序并取 Top-K
```

如果把过滤放到 Top-K 后面，错误版本已经占用了召回名额，删除后也无法自动补回被挤出的正确条文。ADR 0008 专门记录了这个决定。

### 3.4 Citation 必须包含版本证据

引用不只保存 `article_id`，还保存：

- `law_id`；
- `law_version_id`；
- `version_label`；
- `effect_status`；
- `effective_from`；
- `effective_to`。

引用审核回查数据库时同时比较条文和版本绑定。报告版本保存引用快照，即使知识库未来更新，也能解释旧报告当时依据的具体版本。

### 3.5 不填日期保持兼容

旧客户端可以不传 `as_of_date`。系统在真正检索时使用服务器当前日期，并通过响应字段和 `X-Law-As-Of-Date` 告诉调用方实际采用的日期。

输入值为空与实际采用日期是两个概念：数据库可以保留“用户没有指定日期”的事实，检索结果仍然必须具有明确时点。

## 4. 完整数据流

```text
前端选择案件发生日期
  -> POST /api/v1/runs 或 POST /api/v1/cases
  -> Pydantic 校验 YYYY-MM-DD
  -> 日期写入 agent_runs / case_runs
  -> LangGraph 状态携带 as_of_date
  -> mixed_retriever 在 SQL 层过滤 law_versions
  -> 对有效候选做关键词 + Embedding 混合检索
  -> retrieval_logs 保存 law_version_id
  -> citation_reviewer 回查条文与版本
  -> agent_run_citations 保存精确版本
  -> report_writer 写入日期、版本、状态、区间
  -> report_versions 保存不可变报告与引用快照
  -> 前端运行轨迹、报告和详情抽屉展示证据
  -> 人工审批后导出的 Markdown/PDF 保留相同版本信息
```

同步搜索接口 `POST /api/v1/articles/search` 也复用相同检索服务，因此 Apifox、同步案件和 Agent 不会出现三套不同的日期规则。

## 5. 测试与实际结果

最终执行：

```powershell
python scripts\run_self_test.py
python -m ruff format --check app eval scripts tests
python -m ruff check app eval scripts tests
python -m mypy app
cd frontend
pnpm run build
```

结果：

- 75 / 75 项离线自动测试通过；
- 第七周新增 6 项测试，覆盖版本替代关系、历史查询、边界日切换、不填日期、API 校验和 Agent 版本持久化；
- Ruff format 检查通过，48 个文件格式正确；
- Ruff lint 通过；
- mypy 通过，32 个源文件没有类型错误；
- TypeScript 检查和 Vite 生产构建通过，189 个前端模块完成构建；
- OpenAPI JSON 可解析，版本为 `1.1.0`，包含 19 个已实现操作和 4 个计划操作；
- 搜索接口文档包含 `X-Embedding-Provider`、`X-Embedding-Model` 和 `X-Law-As-Of-Date` 响应头。

浏览器端到端验收使用独立临时数据库和离线后端完成，没有写入用户日常数据库：

1. 相同合同问题选择 `2020-12-31`，结果命中《合同法》第九十四条；
2. 页面显示“已废止 · 历史时点适用”“1999年施行版本”和 `1999-10-01` 至 `2021-01-01`；
3. 相同问题改为 `2021-01-01`，结果切换到《民法典》第五百六十三条；
4. 页面显示“现行有效”和从 `2021-01-01` 开始的版本区间；
5. 2021-01-01 的结果中不再出现 1999 年《合同法》版本；
6. 浏览器控制台没有本项目 JavaScript 错误；
7. 验收完成后已经停止临时前后端并删除临时数据库。

## 6. 已知限制

1. 目前没有对接权威法规数据源自动同步，版本关系主要来自项目数据和增量初始化逻辑；
2. 普通知识库导入默认绑定“知识库现行版本”，历史版本仍缺少管理员专用新增、修订和废止接口；
3. 当前用 SQLite 在应用层完成混合打分，法规规模很大时应迁移到 PostgreSQL/pgvector 或专用搜索引擎；
4. `status` 是当前生命周期状态，历史时点有效性依赖日期区间；生产系统需要数据治理来避免重叠区间和错误替代关系；
5. 项目只准备了一个清晰的《合同法》到《民法典》边界演示，不代表已覆盖全部中国法律历史版本；
6. 用户填写的是业务案件日期，不是法院受理日、判决日或法律行为中其他日期，复杂案件可能需要多时间点建模；
7. 教学条文和历史文本仍须在正式使用前到权威来源复核，本项目不构成法律意见。

## 7. 面试可能追问与回答要点

### 问题一：为什么失效日要用不包含的半开区间？

回答要点：半开区间可以让旧版本的 `effective_to` 与新版本的 `effective_from` 使用同一天，不会在边界日同时命中两个版本，也不会产生一天空档。它与多数时间区间、分页区间的工程习惯一致。

### 问题二：`repealed` 的历史版本为什么还能被检索？

回答要点：`repealed` 表示它现在的生命周期已经结束，历史案件是否适用要看案件日期是否落在版本区间内。把“当前状态”和“历史时点有效性”分开，才能正确回答过去发生的案件。

### 问题三：为什么不能先向量检索再删除无效法规？

回答要点：Top-K 是有容量限制的。无效版本会占据候选位置，过滤后正确条文可能没有机会补进来，造成召回损失。必须先在数据库候选集上做业务约束，再计算相似度和排序。

### 问题四：为什么引用要同时存 article ID 和 law version ID？

回答要点：article ID 证明引用了哪一条，law version ID 证明引用的是哪一个时点的文本。二者一起才能做真实性审核、历史报告复现和法规更新后的审计。

### 问题五：为什么不填日期还要在响应里返回实际日期？

回答要点：默认当前日期是兼容策略，但不能让默认行为不可见。返回实际日期可以让调用方记录、展示和复现同一次检索，避免以后法规更新后无法解释旧结果。

### 问题六：如果同一天有两个有效版本怎么办？

回答要点：当前教学版依赖数据初始化保证区间不重叠。生产环境应在写入法规版本时增加区间冲突检查、数据库排他约束或事务锁，并把冲突送人工审核，不能在检索阶段随机选择一个版本。

### 问题七：如何证明这个功能不只是前端改了标签？

回答要点：API 测试直接比较 2020-12-31 与 2021-01-01 的条文集合、响应头和版本字段；数据库引用表保存不同 law version ID；浏览器实测显示报告正文和引用详情同步切换。过滤逻辑位于后端 SQL 候选查询，前端只展示后端证据。

---

# 2026-08-01｜项目学习顺序与 14 天执行计划

## 1. 解决的问题

项目已经积累了 README、产品说明、七周目标、自测手册、接口文档、学习日志、数据库说明、ADR 和面试材料。每份文档各自完整，但初次学习时容易遇到三个问题：

1. 不知道应该先读哪一份；
2. 一开始就进入长篇代码或接口细节，无法建立整体认知；
3. 看过文档却没有实际运行、代码追踪和复述验收，面试时仍然讲不清楚。

本次新增一份统一学习入口，把文档、代码、测试和求职准备排成可执行顺序。

## 2. 修改或新增的关键文件

- 新增 `docs/STUDY_PLAN.md`：提供完整文档顺序、按周代码阅读顺序、14 天计划、最短学习路线和最终检查表；
- 更新 `README.md`：在“更多资料”中把学习计划放到第一入口；
- 在本学习日志末尾追加本次记录。

本次没有修改接口、数据库、配置、业务代码或测试代码。

## 3. 核心设计原理

学习路线采用“产品认知 → 实际运行 → 按周纵向切片 → 专题深入 → 面试表达”的渐进结构：

```text
README 和产品说明
  → 配置与自测
  → 第一至第七周功能
  → API、数据库和 ADR
  → 求职材料、面试手册和演示脚本
```

每周功能都采用相同学习闭环：

```text
先读目标和学习日志
  → 找 API 或前端入口
  → 顺着 service/workflow 追踪
  → 查看 model 和 schema
  → 阅读对应测试
  → 手工运行
  → 回答验收问题
```

这种顺序避免只背结论，也避免在没有业务背景时逐行阅读代码。

## 4. 学习信息如何流转

学习者先通过 README 和产品说明建立项目地图，再通过配置文档、自测手册把项目跑起来。之后按照第一至第七周逐步理解后端基线、RAG、LangGraph、前端异步任务、评测、多轮追问、人工审批和法规版本。

每个功能最终都要从以下链路完成一次追踪：

```text
前端事件
  → frontend/src/api.ts
  → app/main.py
  → app/schemas.py
  → service/workflow
  → app/models.py
  → API 响应
  → tests/ 对应测试
```

完成实现学习后，再用数据库文档和 ADR 理解数据与技术取舍，最后把理解压缩成简历描述、面试回答和 3 分钟演示。

## 5. 验证方法与实际结果

本次是纯文档任务，没有必要重复运行 75 项业务自动测试。实际执行了以下文档检查：

- 扫描 `docs/STUDY_PLAN.md` 中全部 Markdown 链接；
- 共识别 60 个文档链接；
- 60 个链接目标全部存在，缺失数量为 0；
- 检查学习计划中列出的主要代码、测试和工作流目录，目标全部存在；
- 执行 `git diff --check`，没有新增空白字符错误。

## 6. 已知限制

1. 14 天是建议节奏，不代表每个人必须用相同时间；
2. 学习计划会随着第八周及后续功能增加而继续追加；
3. 文档只能给出路径，真正掌握仍要求亲自运行、调试和复述；
4. 学习日志很长，应该按周阅读，不建议一次全部看完；
5. 代码行号会继续变化，所以学习计划使用文件和功能定位，不绑定固定行号；
6. 最短路线适合短期面试准备，不能替代完整代码学习。

## 7. 面试可能追问与回答要点

### 问题一：你是如何快速熟悉一个已有项目的？

回答要点：先从 README 和产品说明建立业务地图，再真实启动并跑通主流程；之后选择一条用户请求，从路由沿着 Schema、Service、Workflow、Model 和 Test 追踪，而不是无目标逐文件阅读。最后通过 ADR 理解技术取舍，并用自己的话复述。

### 问题二：为什么学习时要先跑离线模式？

回答要点：离线模式能先验证本地依赖、数据库、接口、工作流和前端是否正常，把模型 Key、网络和第三方服务排除在第一轮故障之外。基础链路稳定后，再单独接入 Chat 和 Embedding，问题更容易定位。

### 问题三：为什么先读测试，再继续学习下一个功能？

回答要点：测试把功能的正常输入、异常输入、状态边界和兼容要求变成可执行约束。只看实现容易记住“怎么写”，测试能帮助理解“系统承诺了什么”以及以后修改时哪些行为不能破坏。

### 问题四：你如何确认自己真正学会，而不是看懂了文档？

回答要点：至少满足四个证据：能够独立运行；能够从一个接口追踪到数据库和测试；能够不看文档画出数据流；能够说出方案的限制和替代方案。只有能操作、定位、解释和权衡，才算真正掌握。

---

# 2026-08-01：第八周 Agent 运行监控与费用面板

## 1. 解决的问题

原有 `node_traces` 能显示节点名称、耗时和动作摘要，但仍回答不了五个工程问题：

1. 创建 API 与后台 Agent 是否属于同一次运行；
2. 慢在案件抽取、Chat、Embedding、检索还是报告生成；
3. 实际使用了哪个 provider/model；
4. 使用了多少 Token、费用如何估算；
5. 在线调用失败后是否重试或降级，以及原因是什么。

如果为了调试直接记录案件全文、Prompt 或 API Key，又会把监控系统变成新的数据泄漏入口。因此第八周不仅要“多记日志”，还要同时设计 Trace 关联、指标口径、持久化结构和隐私边界。

## 2. 关键文件

| 文件 | 作用 |
|---|---|
| `app/services/observability.py` | OpenTelemetry 初始化、Span 创建、属性 allowlist、费用估算 |
| `app/workflows/legal_report_graph.py` | 为节点、Chat、Embedding、重试与 HITL 恢复埋点 |
| `app/models.py` | `agent_run_spans` 与运行聚合字段 |
| `app/migrations.py` | 为已有 SQLite 增量增加字段、索引和新表 |
| `app/services/monitoring.py` | Span 持久化、单次链路、平均/P95 与概览聚合 |
| `app/llm/client.py` | 读取服务商 usage，累计 Chat Token 和重试 |
| `app/services/embedding_provider.py` | 累计 Embedding 请求与输入 Token |
| `app/main.py` | HTTP Trace 关联、请求日志、状态字段和两个监控接口 |
| `frontend/src/MonitoringPage.tsx` | 概览、节点延迟、最近运行和 Trace 瀑布 |
| `tests/test_eighth_week.py` | 第八周 7 项功能、费用、隐私和兼容测试 |
| `docs/decisions/0009-store-allowlisted-agent-spans.md` | 本地持久化脱敏 Span 的技术决策 |

## 3. 核心原理

### 3.1 Trace 与 Span

Trace 表示一次端到端操作，Span 表示其中一个有开始、结束和父子关系的步骤。创建任务时复用 FastAPI 当前请求的 Trace ID；后台 `agent.invoke` 使用相同 Trace ID，内部节点和模型调用自然成为子 Span。

```text
HTTP POST /runs
  └─ agent.invoke
      ├─ agent.analyze_case
      │   └─ gen_ai.chat
      ├─ agent.retrieval
      │   └─ gen_ai.embeddings
      ├─ agent.review_citations
      │   └─ gen_ai.chat
      └─ agent.write_report
          └─ gen_ai.chat
```

离线模式没有 Chat Span 是正确结果；hash 检索仍有 Embedding Span，用 provider/model 明确说明它不是在线语义模型。

### 3.2 Token 与费用

Chat 服务商响应包含 `usage.prompt_tokens` 和 `usage.completion_tokens` 时优先使用真实计数；没有 usage 时只能使用明确的字符近似。Embedding 记录输入文本的 Token 计数。

费用公式：

```text
Chat 费用
  = 输入 Token × 输入单价 / 1,000,000
  + 输出 Token × 输出单价 / 1,000,000

Embedding 费用
  = 输入 Token × Embedding 单价 / 1,000,000
```

默认单价为 0，表示“统计用量但不编造价格”。估算费用用于容量和相对成本分析，不等于服务商账单。

### 3.3 平均值与 P95

平均值容易被大量快速请求稀释；P95 表示 95% 的样本不超过该耗时，更能暴露尾延迟。当前数据量较小时使用 nearest-rank 算法；没有样本时返回 0，而不是除零或返回虚假值。

### 3.4 遥测隐私

Span 属性不是“想记什么就记什么”，而是固定 allowlist。允许任务 ID、线程 ID、模式、节点、状态、provider/model、Token、候选数、审核数、重试和降级原因；案件问题、上传材料、Prompt、认证头、密钥和密码一律丢弃。

业务表 `agent_runs.question` 仍会保存案件问题，这是产品数据，不是遥测数据。两者的访问权限、保留时间和上传规则必须分开理解。

## 4. 数据流

```text
浏览器 POST /runs
  → FastAPI instrumentation 创建 HTTP Trace
  → middleware 把 trace_id 放入 request.state
  → agent_runs 保存同一个 trace_id
  → BackgroundTasks 执行 LangGraph
  → 每个节点/模型调用生成 SpanRecord
  → persist_span_records 幂等写入 agent_run_spans
  → 聚合根耗时、Token、费用和降级数到 agent_runs
  → GET /runs/{id}/monitoring 返回单次链路
  → GET /monitoring/overview 返回跨运行平均/P95
  → React 监控页展示概览与瀑布
```

追问、审批和修订会恢复同一个 LangGraph thread，并产生新的根 Span。`(run_id, span_id)` 唯一约束避免 checkpoint 恢复时重复写 Span，运行总耗时按多个根 Span 累加。

## 5. 测试与实际结果

新增 7 项第八周测试：

1. 创建响应、状态与 `X-Trace-ID` 关联；
2. 根 Span、节点 Span 和 Embedding Span；
3. 监控概览、节点指标和时间范围校验；
4. 案件与密钥不进入属性；
5. Chat/Embedding 费用计算；
6. 服务商 usage 采集；
7. 无 Trace 历史任务兼容。

最终质量门禁：

- Ruff format：51 个 Python 文件全部已格式化；
- Ruff check：通过；
- mypy：34 个应用文件无错误；
- pytest：82 / 82 通过；
- OpenAPI：3.1.0 JSON 可解析，21 个已实现接口、4 个规划接口；
- 前端：TypeScript 与 Vite 生产构建通过；
- 浏览器：真实提交案件、Trace 链接、概览、节点 P95、Span 瀑布和 390×844 响应式布局通过；
- 控制台：无项目 JavaScript 错误；
- 临时验收数据库与进程已清理。

浏览器离线样例显示 1 次运行、成功率 100%、降级率 0%、总耗时 111 ms、Token 0、费用 `$0.000000`，最慢节点为法规混合检索。这个数字只代表本次本机临时环境，不是性能承诺。

## 6. 已知限制

1. 当前 Span 同时写入 OpenTelemetry SDK 和本地 SQLite，但未配置 OTLP Exporter；
2. 没有 Prometheus 时间序列、告警规则、采样和生产级保留策略；
3. SQLite 适合本地演示，不适合高吞吐遥测；
4. Token 缺少服务商 usage 时只能近似；
5. 费用没有考虑缓存折扣、批量价、免费额度与账单舍入；
6. `success_rate` 当前把等待追问、等待审批和驳回视为非系统失败，生产看板应再拆业务状态；
7. 当前 Trace 页面没有登录和租户隔离，不能直接作为公网生产监控后台；
8. 第九周仍需把进程内 BackgroundTasks 迁移为持久 Worker，但不影响第八周监控独立运行。

## 7. 面试可能追问与回答要点

### 问题一：为什么不用普通日志，必须用 Trace？

日志适合记录离散事件，但一次 Agent 运行有 API、工作流节点、模型和恢复分支。Trace 用稳定 ID 和父子 Span 表达同一运行的结构、耗时和因果关系，更容易定位尾延迟和降级发生在哪一层。

### 问题二：为什么监控数据还要写 SQLite？

本项目要求零外部依赖演示，单用内存重启后无法回查，强制云 APM 又破坏独立运行。SQLite 是第八周的本地适配方案；接口与 Span 语义保留，生产环境可再接 OTLP Collector 和时间序列平台。

### 问题三：为什么离线模式 Token 和费用是 0？

因为离线规则和模板没有调用付费 Chat 模型。监控系统的价值是反映真实执行，不是为了页面好看伪造用量。hash Embedding 会明确显示 provider/model，但它不是在线计费模型。

### 问题四：费用准确吗？

它是估算值。服务商 usage 与正确模型单价都存在时最接近真实调用成本，但缓存、折扣和账单规则仍可能不同。面板用于工程优化，不用于财务对账。

### 问题五：如何防止 Trace 泄露用户案件？

默认拒绝，只允许固定属性白名单；测试主动放入案件问题和假密钥，断言序列化结果中不存在。生产还需要 RBAC、租户隔离、加密、访问审计和数据保留策略。
